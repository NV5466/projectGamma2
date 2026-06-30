"""Gamma / ElectroStat Swell Seed v0.1.3.

Integrated positive-magnitude event worker.

Behavior:
1. Align a new raw waveform to the healthy collective waveform.
2. Test several local analysis windows.
3. Estimate local affine gain, offset, correlation, and RMS ratio.
4. Require persistent statistically abnormal positive gain and RMS evidence.
5. Form bounded swell blocks with hysteresis and persistence.
6. Measure excess magnitude, duration, excess area, and transition timescales.
7. Separate known healthy-noise residuals from unexplained residual structure.
8. Use residual structure to classify clean versus distorted swell; residual
   energy does not erase otherwise-supported swell evidence.

Synthetic research prototype only; not field calibrated or standards-certified.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Mapping
import math
import numpy as np
from numpy.typing import NDArray

import gamma_sag_seed_v01 as core

Array = NDArray[np.float64]


@dataclass(frozen=True)
class SwellConfig:
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
    minimum_equivalent_window_multiples: float = 2.0
    baseline_variance_threshold: float = 0.95
    baseline_max_noise_modes: int = 12
    epsilon: float = 1e-9

    def __post_init__(self) -> None:
        if not self.candidate_windows:
            raise ValueError("candidate_windows cannot be empty")
        for width in self.candidate_windows:
            if width < 5 or width % 2 == 0:
                raise ValueError("candidate windows must be odd and >= 5")
        if self.enter_sigma <= self.exit_sigma:
            raise ValueError("enter_sigma must exceed exit_sigma")
        if min(
            self.enter_persistence_s,
            self.exit_persistence_s,
            self.minimum_event_s,
            self.minimum_equivalent_window_multiples,
        ) <= 0:
            raise ValueError("persistence, event duration, and window multiple must be positive")

    def as_core_config(self) -> core.SagConfig:
        return core.SagConfig(
            candidate_windows=self.candidate_windows,
            max_alignment_lag=self.max_alignment_lag,
            enter_sigma=self.enter_sigma,
            exit_sigma=self.exit_sigma,
            enter_persistence_s=self.enter_persistence_s,
            exit_persistence_s=self.exit_persistence_s,
            minimum_event_s=self.minimum_event_s,
            minimum_correlation_for_clean=self.minimum_correlation_for_clean,
            rms_gain_agreement_tolerance=self.rms_gain_agreement_tolerance,
            minimum_support_confidence=self.minimum_support_confidence,
            baseline_variance_threshold=self.baseline_variance_threshold,
            baseline_max_noise_modes=self.baseline_max_noise_modes,
            epsilon=self.epsilon,
        )


@dataclass(frozen=True)
class SwellWindowAnalysis:
    width: int
    beta: Array
    alpha: Array
    correlation: Array
    rms_ratio: Array
    beta_z: Array
    rms_z: Array
    joint_excess_sigma: Array
    valid_mask: Array
    raw_events: tuple[tuple[int, int, bool], ...]
    score: float
    fragmentation_count: int


@dataclass(frozen=True)
class SwellEvent:
    start_index: int
    end_index: int
    start_time: float
    end_time: float
    duration_s: float
    open_ended: bool
    refined_entry_index: int
    refined_recovery_index: int
    max_excess: float
    median_excess: float
    excess_area_s: float
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
class SwellEvidence:
    status: str
    selected_window: int
    alignment_lag_samples: int
    alignment_correlation: float
    events: tuple[SwellEvent, ...]
    window_scores: Mapping[int, float]
    beta_trace: Array
    alpha_trace: Array
    correlation_trace: Array
    rms_ratio_trace: Array
    beta_z_trace: Array
    rms_z_trace: Array
    joint_excess_sigma_trace: Array
    reconstructed_swell_waveform: Array
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


def fit_swell_baseline(
    healthy_captures: Array,
    sample_interval: float,
    config: SwellConfig = SwellConfig(),
) -> core.SagBaseline:
    return core.fit_sag_baseline(
        healthy_captures,
        sample_interval,
        config.as_core_config(),
    )


def analyze_swell_window(
    baseline: core.SagBaseline,
    aligned_signal: Array,
    width: int,
    config: SwellConfig,
) -> SwellWindowAnalysis:
    model = baseline.window_models[width]
    beta, alpha, corr, rms_ratio, valid = core.local_affine_features(
        baseline.mean_waveform,
        aligned_signal,
        width,
        config.epsilon,
    )
    valid = valid & model.valid_mask

    beta_z = (beta - model.beta_center) / (model.beta_scale + config.epsilon)
    rms_z = (rms_ratio - model.rms_center) / (model.rms_scale + config.epsilon)

    beta_excess = np.maximum(0.0, beta_z)
    rms_excess = np.maximum(0.0, rms_z)
    joint = np.minimum(beta_excess, rms_excess)
    joint = np.where(valid, joint, np.nan)

    events = core._detect_blocks(
        joint,
        valid,
        baseline.sample_interval,
        config.as_core_config(),
    )
    minimum_supported_samples = max(
        1,
        int(math.ceil(0.75 * width)),
        int(math.ceil(config.minimum_event_s / baseline.sample_interval)),
    )
    events = tuple(
        event
        for event in events
        if event[1] - event[0] + 1 >= minimum_supported_samples
    )

    score = core._window_score(
        width,
        events,
        beta,
        corr,
        joint,
        baseline.sample_interval,
    )
    return SwellWindowAnalysis(
        width=width,
        beta=beta,
        alpha=alpha,
        correlation=corr,
        rms_ratio=rms_ratio,
        beta_z=beta_z,
        rms_z=rms_z,
        joint_excess_sigma=joint,
        valid_mask=valid,
        raw_events=events,
        score=float(score),
        fragmentation_count=max(0, len(events) - 1),
    )


def _refine_transition_indices(
    beta: Array,
    start: int,
    end: int,
    width: int,
    dt: float,
) -> tuple[int, int, Array, Array]:
    smooth = core._smooth_trace(beta, width)
    derivative = np.gradient(smooth, dt)
    radius = max(width, 10)

    left_lo = max(1, start - radius)
    left_hi = min(len(beta) - 1, start + radius)
    right_lo = max(1, end - radius)
    right_hi = min(len(beta) - 1, end + radius)

    entry = (
        left_lo + int(np.argmax(derivative[left_lo:left_hi]))
        if left_hi > left_lo
        else start
    )
    recovery = (
        right_lo + int(np.argmin(derivative[right_lo:right_hi]))
        if right_hi > right_lo
        else end
    )
    return entry, recovery, smooth, derivative


def _support_confidence(
    median_joint_sigma: float,
    max_excess: float,
    median_corr: float,
    rms_gain_disagreement: float,
    open_ended: bool,
) -> float:
    """Evidence that a positive magnitude event exists.

    Unexplained residual energy is intentionally absent. It classifies
    clean versus distorted behavior after event support is established.
    """
    significance = 1.0 - math.exp(
        -max(0.0, median_joint_sigma - 1.0) / 2.5
    )
    magnitude = 1.0 - math.exp(-max(0.0, max_excess) / 0.08)
    shape_support = 0.65 + 0.35 * np.clip(
        (median_corr + 1.0) / 2.0,
        0.0,
        1.0,
    )
    agreement = math.exp(
        -max(0.0, rms_gain_disagreement) / 0.30
    )
    bounded = 0.85 if open_ended else 1.0
    return float(
        np.clip(
            significance
            * magnitude
            * shape_support
            * agreement
            * bounded,
            0.0,
            1.0,
        )
    )


def run_swell_seed(
    baseline: core.SagBaseline,
    waveform: Array,
    config: SwellConfig = SwellConfig(),
) -> SwellEvidence:
    waveform = np.asarray(waveform, dtype=float)
    if waveform.shape != baseline.mean_waveform.shape:
        raise ValueError("waveform has the wrong shape")
    if not np.isfinite(waveform).all():
        raise ValueError("waveform must be finite")

    lag, alignment_corr = core.estimate_integer_lag(
        baseline.mean_waveform,
        waveform,
        config.max_alignment_lag,
    )
    aligned = core._shift_with_edge(waveform, lag)

    analyses = [
        analyze_swell_window(baseline, aligned, width, config)
        for width in config.candidate_windows
    ]
    selected = max(analyses, key=lambda item: item.score)
    model = baseline.window_models[selected.width]

    beta = core._fill_invalid(selected.beta, fallback=1.0)
    alpha = core._fill_invalid(selected.alpha, fallback=0.0)
    correlation = core._fill_invalid(selected.correlation, fallback=0.0)
    rms_ratio = core._fill_invalid(selected.rms_ratio, fallback=1.0)

    reconstructed = alpha + beta * baseline.mean_waveform
    residual = aligned - reconstructed
    known_noise, unknown = core._residual_decomposition(
        baseline,
        residual,
    )

    events: list[SwellEvent] = []
    for start, end, open_ended in selected.raw_events:
        entry, recovery, _, derivative = _refine_transition_indices(
            beta,
            start,
            end,
            selected.width,
            baseline.sample_interval,
        )
        sl = slice(start, end + 1)
        expected_beta = core._fill_invalid(
            model.beta_center,
            fallback=1.0,
        )
        local_excess = np.maximum(
            0.0,
            beta[sl] - expected_beta[sl],
        )
        max_excess = (
            float(np.max(local_excess))
            if local_excess.size
            else 0.0
        )
        median_excess = (
            float(np.median(local_excess))
            if local_excess.size
            else 0.0
        )
        area = (
            float(
                np.trapezoid(
                    local_excess,
                    dx=baseline.sample_interval,
                )
            )
            if local_excess.size > 1
            else 0.0
        )
        eq_duration = area / max(max_excess, config.epsilon)

        entry_slope = float(derivative[entry])
        recovery_slope = float(derivative[recovery])
        entry_tau = max_excess / (
            abs(entry_slope) + config.epsilon
        )
        recovery_tau = max_excess / (
            abs(recovery_slope) + config.epsilon
        )

        median_corr = float(np.median(correlation[sl]))
        median_rms = float(np.median(rms_ratio[sl]))
        rms_gain_disagreement = float(
            np.median(np.abs(rms_ratio[sl] - beta[sl]))
        )

        standardized_unknown = unknown[sl] / (
            baseline.pointwise_std[sl] + config.epsilon
        )
        standardized_known = known_noise[sl] / (
            baseline.pointwise_std[sl] + config.epsilon
        )
        unknown_energy = float(
            np.mean(standardized_unknown**2)
        )
        known_energy = float(
            np.mean(standardized_known**2)
        )
        median_joint = float(
            np.nanmedian(selected.joint_excess_sigma[sl])
        )

        confidence = _support_confidence(
            median_joint,
            max_excess,
            median_corr,
            rms_gain_disagreement,
            open_ended,
        )

        minimum_equivalent_duration = (
            config.minimum_equivalent_window_multiples
            * selected.width
            * baseline.sample_interval
        )
        event_supported = (
            confidence >= config.minimum_support_confidence
            and median_rms > 1.0
            and max_excess > 0.0
            and eq_duration >= minimum_equivalent_duration
        )
        clean = (
            event_supported
            and median_corr
            >= config.minimum_correlation_for_clean
            and rms_gain_disagreement
            <= config.rms_gain_agreement_tolerance
            and unknown_energy <= 1.25
        )

        if clean:
            classification = "clean_swell_supported"
        elif event_supported:
            classification = "distorted_swell_supported"
        else:
            classification = "ambiguous_high_magnitude_event"

        events.append(
            SwellEvent(
                start_index=int(start),
                end_index=int(end),
                start_time=float(
                    start * baseline.sample_interval
                ),
                end_time=float(
                    end * baseline.sample_interval
                ),
                duration_s=float(
                    (end - start + 1)
                    * baseline.sample_interval
                ),
                open_ended=bool(open_ended),
                refined_entry_index=int(entry),
                refined_recovery_index=int(recovery),
                max_excess=max_excess,
                median_excess=median_excess,
                excess_area_s=area,
                equivalent_rectangular_duration_s=float(
                    eq_duration
                ),
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
    elif any(
        event.classification == "clean_swell_supported"
        for event in events
    ):
        status = "clean_swell_supported"
    elif any(
        event.classification
        == "distorted_swell_supported"
        for event in events
    ):
        status = "distorted_swell_supported"
    else:
        status = "ambiguous"

    return SwellEvidence(
        status=status,
        selected_window=selected.width,
        alignment_lag_samples=int(lag),
        alignment_correlation=float(alignment_corr),
        events=tuple(events),
        window_scores={
            analysis.width: analysis.score
            for analysis in analyses
        },
        beta_trace=beta,
        alpha_trace=alpha,
        correlation_trace=correlation,
        rms_ratio_trace=rms_ratio,
        beta_z_trace=core._fill_invalid(selected.beta_z),
        rms_z_trace=core._fill_invalid(selected.rms_z),
        joint_excess_sigma_trace=core._fill_invalid(
            selected.joint_excess_sigma
        ),
        reconstructed_swell_waveform=reconstructed,
        residual=residual,
        known_noise_residual=known_noise,
        unknown_residual=unknown,
        notes=(
            "Positive local gain and RMS are jointly required.",
            "Residual energy labels clean versus distorted swell.",
            "Equivalent excess duration must span multiple analysis windows.",
            "Amplitude-over-slope is a transition timescale.",
            "Synthetic prototype only; thresholds are not field calibrated.",
        ),
    )
