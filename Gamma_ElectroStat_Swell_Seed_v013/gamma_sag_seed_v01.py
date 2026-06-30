"""Gamma / ElectroStat Sag Seed v0.1.

Synthetic prototype of the agreed behavioral method:

1. Align a new raw waveform to the healthy collective waveform.
2. For several candidate windows, estimate local affine gain/offset,
   local correlation, and local RMS relative to healthy statistics.
3. Build a sag evidence trace from simultaneous abnormal reduction in
   local gain and local RMS.
4. Apply statistical hysteresis and temporal persistence to create
   bounded event blocks.
5. Refine transition locations, measure depth/duration/deficit area,
   estimate amplitude-over-slope timescales, and decompose the remaining
   residual into learned healthy-noise and unexplained components.

This code is a synthetic research prototype, not a power-quality standard
implementation and not a field-validated diagnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Iterable, Mapping, Sequence
import math
import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import uniform_filter1d, median_filter
from scipy.signal import savgol_filter

Array = NDArray[np.float64]


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SagConfig:
    candidate_windows: tuple[int, ...] = (41, 81, 161, 241)
    max_alignment_lag: int = 25
    enter_sigma: float = 3.0
    exit_sigma: float = 1.25
    enter_persistence_s: float = 0.020
    exit_persistence_s: float = 0.030
    minimum_event_s: float = 0.035
    minimum_correlation_for_clean: float = 0.88
    rms_gain_agreement_tolerance: float = 0.15
    minimum_support_confidence: float = 0.55
    baseline_variance_threshold: float = 0.95
    baseline_max_noise_modes: int = 12
    epsilon: float = 1e-9

    def __post_init__(self) -> None:
        if not self.candidate_windows:
            raise ValueError("candidate_windows cannot be empty")
        for width in self.candidate_windows:
            if width < 5 or width % 2 == 0:
                raise ValueError("candidate windows must be odd and >= 5")
        if self.max_alignment_lag < 0:
            raise ValueError("max_alignment_lag must be nonnegative")
        if self.enter_sigma <= self.exit_sigma:
            raise ValueError("enter_sigma must be greater than exit_sigma")
        if min(
            self.enter_persistence_s,
            self.exit_persistence_s,
            self.minimum_event_s,
        ) <= 0:
            raise ValueError("persistence and minimum event durations must be positive")


@dataclass(frozen=True)
class WindowBaseline:
    width: int
    beta_center: Array
    beta_scale: Array
    rms_center: Array
    rms_scale: Array
    correlation_center: Array
    valid_mask: Array


@dataclass(frozen=True)
class SagBaseline:
    sample_interval: float
    mean_waveform: Array
    pointwise_std: Array
    noise_basis: Array
    window_models: Mapping[int, WindowBaseline]
    aligned_healthy_captures: Array
    alignment_lags: Array


@dataclass(frozen=True)
class WindowAnalysis:
    width: int
    beta: Array
    alpha: Array
    correlation: Array
    rms_ratio: Array
    beta_z: Array
    rms_z: Array
    joint_deficit_sigma: Array
    valid_mask: Array
    raw_events: tuple[tuple[int, int, bool], ...]
    score: float
    fragmentation_count: int


@dataclass(frozen=True)
class SagEvent:
    start_index: int
    end_index: int
    start_time: float
    end_time: float
    duration_s: float
    open_ended: bool
    refined_entry_index: int
    refined_recovery_index: int
    max_depth: float
    median_depth: float
    deficit_area_s: float
    equivalent_rectangular_duration_s: float
    entry_slope_per_s: float
    recovery_slope_per_s: float
    entry_timescale_s: float
    recovery_timescale_s: float
    median_correlation: float
    median_rms_ratio: float
    rms_gain_disagreement: float
    unknown_residual_energy: float
    known_noise_energy: float
    classification: str
    confidence: float


@dataclass(frozen=True)
class SagEvidence:
    status: str
    selected_window: int
    alignment_lag_samples: int
    alignment_correlation: float
    events: tuple[SagEvent, ...]
    window_scores: Mapping[int, float]
    beta_trace: Array
    alpha_trace: Array
    correlation_trace: Array
    rms_ratio_trace: Array
    beta_z_trace: Array
    rms_z_trace: Array
    joint_deficit_sigma_trace: Array
    reconstructed_sag_waveform: Array
    residual: Array
    known_noise_residual: Array
    unknown_residual: Array
    notes: tuple[str, ...] = field(default_factory=tuple)

    def summary_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "selected_window": self.selected_window,
            "alignment_lag_samples": self.alignment_lag_samples,
            "alignment_correlation": self.alignment_correlation,
            "event_count": len(self.events),
            "events": [asdict(event) for event in self.events],
            "window_scores": dict(self.window_scores),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def _robust_center_scale(stack: Array, epsilon: float) -> tuple[Array, Array]:
    # Avoid noisy all-NaN warnings at window edges by reducing only columns
    # containing at least one finite healthy estimate.
    finite_any = np.isfinite(stack).any(axis=0)
    center = np.full(stack.shape[1], np.nan, dtype=float)
    mad = np.full(stack.shape[1], np.nan, dtype=float)
    center[finite_any] = np.nanmedian(stack[:, finite_any], axis=0)
    mad[finite_any] = np.nanmedian(
        np.abs(stack[:, finite_any] - center[finite_any]), axis=0
    )
    scale = 1.4826 * mad
    # If healthy repetitions are nearly identical at a time point, use a small
    # floor based on the typical nonzero scale rather than allowing infinite z.
    positive = scale[np.isfinite(scale) & (scale > epsilon)]
    fallback = float(np.median(positive)) if positive.size else 1e-3
    scale = np.where(np.isfinite(scale), np.maximum(scale, max(epsilon, 0.05 * fallback)), fallback)
    return center, scale


def _shift_with_edge(signal: Array, lag: int) -> Array:
    """Return aligned[n] = signal[n + lag], using edge values outside range."""
    n = signal.size
    source = np.arange(n) + int(lag)
    return np.interp(source, np.arange(n), signal, left=signal[0], right=signal[-1])


def estimate_integer_lag(template: Array, signal: Array, max_lag: int) -> tuple[int, float]:
    template = np.asarray(template, dtype=float)
    signal = np.asarray(signal, dtype=float)
    if template.shape != signal.shape:
        raise ValueError("template and signal must have the same shape")

    best_lag = 0
    best_corr = -np.inf
    for lag in range(-max_lag, max_lag + 1):
        if lag > 0:
            a = template[:-lag]
            b = signal[lag:]
        elif lag < 0:
            a = template[-lag:]
            b = signal[:lag]
        else:
            a = template
            b = signal
        ac = a - np.mean(a)
        bc = b - np.mean(b)
        denom = math.sqrt(float(np.dot(ac, ac) * np.dot(bc, bc))) + 1e-12
        corr = float(np.dot(ac, bc) / denom)
        if corr > best_corr:
            best_corr = corr
            best_lag = lag
    return best_lag, best_corr


def local_affine_features(reference: Array, signal: Array, width: int, epsilon: float = 1e-9) -> tuple[Array, Array, Array, Array, Array]:
    """Sliding local OLS x ~= alpha + beta * reference plus correlation/RMS ratio."""
    reference = np.asarray(reference, dtype=float)
    signal = np.asarray(signal, dtype=float)
    if reference.shape != signal.shape:
        raise ValueError("reference and signal must have the same shape")
    if width % 2 == 0:
        raise ValueError("width must be odd")

    mx = uniform_filter1d(reference, size=width, mode="nearest")
    my = uniform_filter1d(signal, size=width, mode="nearest")
    mxx = uniform_filter1d(reference * reference, size=width, mode="nearest")
    myy = uniform_filter1d(signal * signal, size=width, mode="nearest")
    mxy = uniform_filter1d(reference * signal, size=width, mode="nearest")

    var_x = np.maximum(mxx - mx * mx, 0.0)
    var_y = np.maximum(myy - my * my, 0.0)
    cov_xy = mxy - mx * my

    beta = cov_xy / (var_x + epsilon)
    alpha = my - beta * mx
    correlation = cov_xy / (np.sqrt(var_x * var_y) + epsilon)
    correlation = np.clip(correlation, -1.0, 1.0)

    rms_ref = np.sqrt(np.maximum(mxx, 0.0))
    rms_sig = np.sqrt(np.maximum(myy, 0.0))
    rms_ratio = rms_sig / (rms_ref + epsilon)

    half = width // 2
    excitation_floor = max(float(np.nanmedian(var_x)) * 0.03, epsilon)
    valid = var_x > excitation_floor
    valid[:half] = False
    valid[-half:] = False

    beta = np.where(valid, beta, np.nan)
    alpha = np.where(valid, alpha, np.nan)
    correlation = np.where(valid, correlation, np.nan)
    rms_ratio = np.where(valid, rms_ratio, np.nan)
    return beta, alpha, correlation, rms_ratio, valid


def _fill_invalid(trace: Array, fallback: float = 0.0) -> Array:
    trace = np.asarray(trace, dtype=float)
    valid = np.isfinite(trace)
    if not valid.any():
        return np.full_like(trace, fallback)
    idx = np.arange(trace.size)
    return np.interp(idx, idx[valid], trace[valid])


def _smooth_trace(trace: Array, width: int) -> Array:
    filled = _fill_invalid(trace)
    # Use a modest filter, independent of the analysis window, so edge slopes
    # remain visible. Savitzky-Golay preserves local slopes better than a mean.
    length = min(max(7, width // 5 | 1), 51)
    if length >= trace.size:
        length = trace.size - (1 - trace.size % 2)
    if length < 5:
        return filled
    return savgol_filter(filled, window_length=length, polyorder=2, mode="interp")


# ---------------------------------------------------------------------------
# Healthy baseline construction
# ---------------------------------------------------------------------------


def fit_sag_baseline(
    healthy_captures: Array,
    sample_interval: float,
    config: SagConfig = SagConfig(),
) -> SagBaseline:
    captures = np.asarray(healthy_captures, dtype=float)
    if captures.ndim != 2 or captures.shape[0] < 5:
        raise ValueError("healthy_captures must be 2D with at least five repetitions")
    if sample_interval <= 0:
        raise ValueError("sample_interval must be positive")
    if not np.isfinite(captures).all():
        raise ValueError("healthy captures must be finite")

    initial = np.median(captures, axis=0)
    aligned = []
    lags = []
    for capture in captures:
        lag, _ = estimate_integer_lag(initial, capture, config.max_alignment_lag)
        aligned.append(_shift_with_edge(capture, lag))
        lags.append(lag)
    aligned_stack = np.asarray(aligned)

    # One refinement pass against the robust collective.
    collective = np.median(aligned_stack, axis=0)
    refined = []
    refined_lags = []
    for capture in captures:
        lag, _ = estimate_integer_lag(collective, capture, config.max_alignment_lag)
        refined.append(_shift_with_edge(capture, lag))
        refined_lags.append(lag)
    aligned_stack = np.asarray(refined)
    mean_waveform = np.mean(aligned_stack, axis=0)
    pointwise_std = np.std(aligned_stack, axis=0, ddof=1)
    positive_std = pointwise_std[pointwise_std > config.epsilon]
    std_floor = float(np.median(positive_std)) * 0.05 if positive_std.size else 1e-3
    pointwise_std = np.maximum(pointwise_std, max(std_floor, config.epsilon))

    residuals = aligned_stack - mean_waveform
    _, singular_values, vt = np.linalg.svd(residuals, full_matrices=False)
    variance = singular_values * singular_values
    if float(variance.sum()) <= config.epsilon:
        basis = np.empty((captures.shape[1], 0))
    else:
        ratios = variance / variance.sum()
        count = int(np.searchsorted(np.cumsum(ratios), config.baseline_variance_threshold) + 1)
        count = min(count, config.baseline_max_noise_modes)
        basis = vt[:count].T

    window_models: dict[int, WindowBaseline] = {}
    for width in config.candidate_windows:
        beta_rows = []
        rms_rows = []
        corr_rows = []
        valid_rows = []
        for capture in aligned_stack:
            beta, _, corr, rms_ratio, valid = local_affine_features(
                mean_waveform, capture, width, config.epsilon
            )
            beta_rows.append(beta)
            rms_rows.append(rms_ratio)
            corr_rows.append(corr)
            valid_rows.append(valid)
        beta_stack = np.asarray(beta_rows)
        rms_stack = np.asarray(rms_rows)
        corr_stack = np.asarray(corr_rows)
        valid_stack = np.asarray(valid_rows)

        beta_center, beta_scale = _robust_center_scale(beta_stack, config.epsilon)
        rms_center, rms_scale = _robust_center_scale(rms_stack, config.epsilon)
        corr_center = np.full(corr_stack.shape[1], np.nan, dtype=float)
        corr_finite = np.isfinite(corr_stack).any(axis=0)
        corr_center[corr_finite] = np.nanmedian(corr_stack[:, corr_finite], axis=0)
        valid_mask = np.mean(valid_stack, axis=0) >= 0.8

        window_models[width] = WindowBaseline(
            width=width,
            beta_center=beta_center,
            beta_scale=beta_scale,
            rms_center=rms_center,
            rms_scale=rms_scale,
            correlation_center=corr_center,
            valid_mask=valid_mask,
        )

    return SagBaseline(
        sample_interval=float(sample_interval),
        mean_waveform=mean_waveform,
        pointwise_std=pointwise_std,
        noise_basis=basis,
        window_models=window_models,
        aligned_healthy_captures=aligned_stack,
        alignment_lags=np.asarray(refined_lags, dtype=int),
    )


# ---------------------------------------------------------------------------
# Event state machine and window selection
# ---------------------------------------------------------------------------


def _detect_blocks(
    joint_deficit_sigma: Array,
    valid_mask: Array,
    dt: float,
    config: SagConfig,
) -> tuple[tuple[int, int, bool], ...]:
    """Hysteresis + persistence state machine.

    A value above enter_sigma means both gain and RMS are at least that many
    robust standard deviations below their healthy expectations.
    """
    enter_n = max(1, int(math.ceil(config.enter_persistence_s / dt)))
    exit_n = max(1, int(math.ceil(config.exit_persistence_s / dt)))
    minimum_n = max(1, int(math.ceil(config.minimum_event_s / dt)))

    events: list[tuple[int, int, bool]] = []
    active = False
    pending_enter_start: int | None = None
    pending_exit_start: int | None = None
    event_start = 0

    for i, value in enumerate(joint_deficit_sigma):
        valid = bool(valid_mask[i] and np.isfinite(value))
        if not active:
            if valid and value >= config.enter_sigma:
                if pending_enter_start is None:
                    pending_enter_start = i
                if i - pending_enter_start + 1 >= enter_n:
                    active = True
                    event_start = pending_enter_start
                    pending_enter_start = None
                    pending_exit_start = None
            else:
                pending_enter_start = None
        else:
            recovered = (not valid) or value <= config.exit_sigma
            if recovered:
                if pending_exit_start is None:
                    pending_exit_start = i
                if i - pending_exit_start + 1 >= exit_n:
                    event_end = pending_exit_start
                    if event_end - event_start >= minimum_n:
                        events.append((event_start, event_end, False))
                    active = False
                    pending_exit_start = None
                    pending_enter_start = None
            else:
                pending_exit_start = None

    if active:
        event_end = len(joint_deficit_sigma) - 1
        if event_end - event_start >= minimum_n:
            events.append((event_start, event_end, True))
    return tuple(events)


def _window_score(
    width: int,
    events: Sequence[tuple[int, int, bool]],
    beta: Array,
    correlation: Array,
    joint_deficit_sigma: Array,
    dt: float,
) -> float:
    if not events:
        # A no-event window is not invalid, but it should not win over a window
        # with coherent evidence.
        return -2.0 - 0.001 * width

    event_strengths = []
    event_corrs = []
    event_durations = []
    roughness_terms = []
    smooth_beta = _smooth_trace(beta, width)
    derivative = np.gradient(smooth_beta, dt)

    for start, end, _ in events:
        sl = slice(start, end + 1)
        event_strengths.append(float(np.nanmedian(joint_deficit_sigma[sl])))
        event_corrs.append(float(np.nanmedian(correlation[sl])))
        event_durations.append((end - start + 1) * dt)
        roughness_terms.append(float(np.nanmedian(np.abs(np.diff(derivative[sl])))))

    strength = max(event_strengths)
    corr = max(event_corrs)
    duration = max(event_durations)
    fragmentation = max(0, len(events) - 1)
    blur_ratio = (width * dt) / max(duration, dt)
    roughness = min(float(np.nanmedian(roughness_terms)), 10.0)

    return (
        1.25 * min(strength, 10.0)
        + 2.0 * np.clip(corr, -1.0, 1.0)
        - 1.0 * fragmentation
        - 0.35 * blur_ratio
        - 0.05 * roughness
    )


def analyze_window(
    baseline: SagBaseline,
    aligned_signal: Array,
    width: int,
    config: SagConfig,
) -> WindowAnalysis:
    model = baseline.window_models[width]
    beta, alpha, corr, rms_ratio, valid = local_affine_features(
        baseline.mean_waveform, aligned_signal, width, config.epsilon
    )
    valid = valid & model.valid_mask

    beta_z = (beta - model.beta_center) / (model.beta_scale + config.epsilon)
    rms_z = (rms_ratio - model.rms_center) / (model.rms_scale + config.epsilon)

    # Both local gain and local RMS must support a reduction. Taking the
    # smaller positive deficit implements a conservative AND gate in sigma space.
    beta_deficit = np.maximum(0.0, -beta_z)
    rms_deficit = np.maximum(0.0, -rms_z)
    joint = np.minimum(beta_deficit, rms_deficit)
    joint = np.where(valid, joint, np.nan)

    events = _detect_blocks(joint, valid, baseline.sample_interval, config)
    # A feature shorter than the analysis support is usually an edge artifact:
    # the local window is mixing two non-sag states rather than observing a
    # sustained reduced-gain state. Keep only events that occupy most of one
    # selected window.
    minimum_supported_samples = max(
        1,
        int(math.ceil(0.75 * width)),
        int(math.ceil(config.minimum_event_s / baseline.sample_interval)),
    )
    events = tuple(
        event for event in events
        if event[1] - event[0] + 1 >= minimum_supported_samples
    )
    score = _window_score(width, events, beta, corr, joint, baseline.sample_interval)
    return WindowAnalysis(
        width=width,
        beta=beta,
        alpha=alpha,
        correlation=corr,
        rms_ratio=rms_ratio,
        beta_z=beta_z,
        rms_z=rms_z,
        joint_deficit_sigma=joint,
        valid_mask=valid,
        raw_events=events,
        score=float(score),
        fragmentation_count=max(0, len(events) - 1),
    )


# ---------------------------------------------------------------------------
# Event measurement and top-level worker
# ---------------------------------------------------------------------------


def _refine_transition_indices(beta: Array, start: int, end: int, width: int, dt: float) -> tuple[int, int, Array, Array]:
    smooth = _smooth_trace(beta, width)
    derivative = np.gradient(smooth, dt)
    radius = max(width, 10)

    left_lo = max(1, start - radius)
    left_hi = min(len(beta) - 1, start + radius)
    right_lo = max(1, end - radius)
    right_hi = min(len(beta) - 1, end + radius)

    entry = left_lo + int(np.argmin(derivative[left_lo:left_hi])) if left_hi > left_lo else start
    recovery = right_lo + int(np.argmax(derivative[right_lo:right_hi])) if right_hi > right_lo else end
    return entry, recovery, smooth, derivative


def _residual_decomposition(baseline: SagBaseline, residual: Array) -> tuple[Array, Array]:
    if baseline.noise_basis.shape[1] == 0:
        known = np.zeros_like(residual)
    else:
        known = baseline.noise_basis @ (baseline.noise_basis.T @ residual)
    return known, residual - known


def _event_confidence(
    median_joint_sigma: float,
    median_corr: float,
    rms_gain_disagreement: float,
    unknown_energy: float,
    open_ended: bool,
) -> float:
    significance = 1.0 - math.exp(-max(0.0, median_joint_sigma - 1.0) / 2.5)
    shape = np.clip((median_corr + 1.0) / 2.0, 0.0, 1.0)
    agreement = math.exp(-max(0.0, rms_gain_disagreement) / 0.20)
    residual_term = math.exp(-max(0.0, unknown_energy - 1.0) / 6.0)
    bounded = 0.85 if open_ended else 1.0
    return float(np.clip(significance * (0.45 + 0.55 * shape) * agreement * residual_term * bounded, 0.0, 1.0))


def run_sag_seed(
    baseline: SagBaseline,
    waveform: Array,
    config: SagConfig = SagConfig(),
) -> SagEvidence:
    waveform = np.asarray(waveform, dtype=float)
    if waveform.shape != baseline.mean_waveform.shape:
        raise ValueError("waveform has the wrong shape")
    if not np.isfinite(waveform).all():
        raise ValueError("waveform must be finite")

    lag, alignment_corr = estimate_integer_lag(
        baseline.mean_waveform, waveform, config.max_alignment_lag
    )
    aligned = _shift_with_edge(waveform, lag)

    analyses = [
        analyze_window(baseline, aligned, width, config)
        for width in config.candidate_windows
    ]
    selected = max(analyses, key=lambda item: item.score)
    model = baseline.window_models[selected.width]

    beta = _fill_invalid(selected.beta, fallback=1.0)
    alpha = _fill_invalid(selected.alpha, fallback=0.0)
    correlation = _fill_invalid(selected.correlation, fallback=0.0)
    rms_ratio = _fill_invalid(selected.rms_ratio, fallback=1.0)

    reconstructed = alpha + beta * baseline.mean_waveform
    residual = aligned - reconstructed
    known_noise, unknown = _residual_decomposition(baseline, residual)

    events: list[SagEvent] = []
    for start, end, open_ended in selected.raw_events:
        entry, recovery, smooth_beta, derivative = _refine_transition_indices(
            beta, start, end, selected.width, baseline.sample_interval
        )
        sl = slice(start, end + 1)
        expected_beta = _fill_invalid(model.beta_center, fallback=1.0)
        local_depth = np.maximum(0.0, expected_beta[sl] - beta[sl])
        max_depth = float(np.max(local_depth)) if local_depth.size else 0.0
        median_depth = float(np.median(local_depth)) if local_depth.size else 0.0
        area = float(np.trapezoid(local_depth, dx=baseline.sample_interval)) if local_depth.size > 1 else 0.0
        eq_duration = area / max(max_depth, config.epsilon)

        entry_slope = float(derivative[entry])
        recovery_slope = float(derivative[recovery])
        entry_tau = max_depth / (abs(entry_slope) + config.epsilon)
        recovery_tau = max_depth / (abs(recovery_slope) + config.epsilon)

        median_corr = float(np.median(correlation[sl]))
        median_rms = float(np.median(rms_ratio[sl]))
        median_beta = float(np.median(beta[sl]))
        rms_gain_disagreement = float(np.median(np.abs(rms_ratio[sl] - beta[sl])))

        standardized_unknown = unknown[sl] / (baseline.pointwise_std[sl] + config.epsilon)
        standardized_known = known_noise[sl] / (baseline.pointwise_std[sl] + config.epsilon)
        unknown_energy = float(np.mean(standardized_unknown**2))
        known_energy = float(np.mean(standardized_known**2))
        median_joint = float(np.nanmedian(selected.joint_deficit_sigma[sl]))

        clean = (
            median_corr >= config.minimum_correlation_for_clean
            and rms_gain_disagreement <= config.rms_gain_agreement_tolerance
            and unknown_energy <= 1.25
        )
        if clean:
            classification = "clean_sag_supported"
        elif median_corr >= 0.55 and median_rms < 1.0:
            classification = "distorted_sag_supported"
        else:
            classification = "ambiguous_low_magnitude_event"

        confidence = _event_confidence(
            median_joint,
            median_corr,
            rms_gain_disagreement,
            unknown_energy,
            open_ended,
        )
        if confidence < config.minimum_support_confidence:
            classification = "ambiguous_low_magnitude_event"

        events.append(
            SagEvent(
                start_index=int(start),
                end_index=int(end),
                start_time=float(start * baseline.sample_interval),
                end_time=float(end * baseline.sample_interval),
                duration_s=float((end - start + 1) * baseline.sample_interval),
                open_ended=bool(open_ended),
                refined_entry_index=int(entry),
                refined_recovery_index=int(recovery),
                max_depth=max_depth,
                median_depth=median_depth,
                deficit_area_s=area,
                equivalent_rectangular_duration_s=float(eq_duration),
                entry_slope_per_s=entry_slope,
                recovery_slope_per_s=recovery_slope,
                entry_timescale_s=float(entry_tau),
                recovery_timescale_s=float(recovery_tau),
                median_correlation=median_corr,
                median_rms_ratio=median_rms,
                rms_gain_disagreement=rms_gain_disagreement,
                unknown_residual_energy=unknown_energy,
                known_noise_energy=known_energy,
                classification=classification,
                confidence=confidence,
            )
        )

    if not events:
        status = "rejected"
    elif any(event.classification == "clean_sag_supported" for event in events):
        status = "clean_sag_supported"
    elif any(event.classification == "distorted_sag_supported" for event in events):
        status = "distorted_sag_supported"
    else:
        status = "ambiguous"

    notes = (
        "RMS and local-gain reduction are jointly required for event entry.",
        "Amplitude-over-slope is reported as a transition timescale, not event area.",
        "Synthetic prototype only; thresholds are not field calibrated.",
    )

    return SagEvidence(
        status=status,
        selected_window=selected.width,
        alignment_lag_samples=int(lag),
        alignment_correlation=float(alignment_corr),
        events=tuple(events),
        window_scores={analysis.width: analysis.score for analysis in analyses},
        beta_trace=beta,
        alpha_trace=alpha,
        correlation_trace=correlation,
        rms_ratio_trace=rms_ratio,
        beta_z_trace=_fill_invalid(selected.beta_z),
        rms_z_trace=_fill_invalid(selected.rms_z),
        joint_deficit_sigma_trace=_fill_invalid(selected.joint_deficit_sigma),
        reconstructed_sag_waveform=reconstructed,
        residual=residual,
        known_noise_residual=known_noise,
        unknown_residual=unknown,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Synthetic research utilities used by the demo/tests
# ---------------------------------------------------------------------------


def smooth_box_envelope(
    t: Array,
    start: float,
    end: float,
    retained_gain: float,
    ramp_s: float,
) -> Array:
    if not 0 < retained_gain <= 1.5:
        raise ValueError("retained_gain must be positive")
    if end <= start or ramp_s <= 0:
        raise ValueError("invalid event timing")
    # Logistic edges create a bounded, differentiable event.
    sharp = 6.0 / ramp_s
    enter_arg = np.clip(-sharp * (t - start), -60.0, 60.0)
    leave_arg = np.clip(-sharp * (t - end), -60.0, 60.0)
    enter = 1.0 / (1.0 + np.exp(enter_arg))
    leave = 1.0 / (1.0 + np.exp(leave_arg))
    block = np.clip(enter - leave, 0.0, 1.0)
    return 1.0 - (1.0 - retained_gain) * block


def make_reference_waveform(t: Array) -> Array:
    # An arbitrary repeatable waveform: multi-frequency electrical content,
    # slow operating envelope, and two smooth command-response features.
    carrier = (
        1.00 * np.sin(2 * np.pi * 11.0 * t + 0.15)
        + 0.30 * np.sin(2 * np.pi * 31.0 * t + 0.80)
        + 0.12 * np.sin(2 * np.pi * 63.0 * t - 0.25)
    )
    envelope = 1.0 + 0.12 * np.sin(2 * np.pi * 0.7 * t)
    step1 = 0.22 * np.tanh((t - 0.45) / 0.035)
    step2 = -0.18 * np.tanh((t - 1.45) / 0.050)
    return envelope * carrier + step1 + step2


def make_healthy_population(
    reference: Array,
    dt: float,
    count: int,
    rng: np.random.Generator,
    max_shift: int = 8,
) -> Array:
    t = np.arange(reference.size) * dt
    captures = []
    for _ in range(count):
        shift = int(rng.integers(-max_shift, max_shift + 1))
        shifted = _shift_with_edge(reference, -shift)
        gain = rng.normal(1.0, 0.025)
        offset = rng.normal(0.0, 0.025)
        low_drift = rng.normal(0.0, 0.018) * np.sin(2 * np.pi * rng.uniform(0.2, 1.1) * t + rng.uniform(0, 2 * np.pi))
        noise = rng.normal(0.0, rng.uniform(0.018, 0.045), size=reference.size)
        capture = offset + gain * shifted + low_drift + noise
        if rng.random() < 0.35:
            for _ in range(int(rng.integers(1, 4))):
                idx = int(rng.integers(10, reference.size - 10))
                capture[idx] += rng.normal(0.0, 0.25)
        captures.append(median_filter(capture, size=3))
    return np.asarray(captures)


def make_synthetic_case(
    reference: Array,
    dt: float,
    rng: np.random.Generator,
    case: str,
) -> tuple[Array, dict[str, float | str | bool]]:
    n = reference.size
    t = np.arange(n) * dt
    base_shift = int(rng.integers(-7, 8))
    shifted = _shift_with_edge(reference, -base_shift)
    gain0 = rng.normal(1.0, 0.015)
    offset0 = rng.normal(0.0, 0.015)
    signal = offset0 + gain0 * shifted
    truth: dict[str, float | str | bool] = {
        "case": case,
        "has_sag": False,
        "true_start_s": math.nan,
        "true_end_s": math.nan,
        "retained_gain": 1.0,
    }

    if case in {"clean_sag", "gradual_sag", "distorted_sag", "short_dip"}:
        start = float(rng.uniform(0.48, 0.82))
        duration = {
            "clean_sag": rng.uniform(0.30, 0.62),
            "gradual_sag": rng.uniform(0.48, 0.78),
            "distorted_sag": rng.uniform(0.28, 0.58),
            "short_dip": rng.uniform(0.008, 0.018),
        }[case]
        end = min(start + float(duration), t[-1] - 0.18)
        retained = float(rng.uniform(0.50, 0.82))
        ramp = {
            "clean_sag": rng.uniform(0.025, 0.060),
            "gradual_sag": rng.uniform(0.12, 0.22),
            "distorted_sag": rng.uniform(0.025, 0.080),
            "short_dip": rng.uniform(0.002, 0.006),
        }[case]
        env = smooth_box_envelope(t, start, end, retained, float(ramp))
        signal = offset0 + gain0 * env * shifted
        truth.update(
            {
                "has_sag": case != "short_dip",
                "true_start_s": start,
                "true_end_s": end,
                "retained_gain": retained,
            }
        )
        if case == "distorted_sag":
            event_mask = 1.0 - env
            signal += event_mask * (
                0.18 * np.sin(2 * np.pi * 77.0 * t + 0.4)
                + 0.10 * np.sign(np.sin(2 * np.pi * 11.0 * t))
            )
    elif case == "offset_step":
        start, end = 0.65, 1.15
        env = smooth_box_envelope(t, start, end, 0.0 + 1e-6, 0.04)
        block = 1.0 - env
        signal += -0.38 * block
    elif case == "phase_glitch":
        start, end = 0.62, 1.18
        block = 1.0 - smooth_box_envelope(t, start, end, 1e-6, 0.035)
        phase_shifted = np.interp(t + 0.006, t, shifted, left=shifted[0], right=shifted[-1])
        signal = offset0 + gain0 * ((1.0 - block) * shifted + block * phase_shifted)
    elif case == "swell":
        start, end = 0.58, 1.22
        env = smooth_box_envelope(t, start, end, 1.22, 0.045)
        signal = offset0 + gain0 * env * shifted
    elif case == "impulse_only":
        for _ in range(4):
            idx = int(rng.integers(200, n - 200))
            signal[idx] += rng.normal(0.0, 0.65)
    elif case == "healthy":
        pass
    else:
        raise ValueError(f"Unknown synthetic case: {case}")

    signal += rng.normal(0.0, rng.uniform(0.018, 0.040), size=n)
    return median_filter(signal, size=3), truth
