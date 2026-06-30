"""Gamma / ElectroStat Short Interruption Seed v0.1.1.

Behavioral detector for low-voltage interruptions.

The worker deliberately reuses the sag architecture:

    alignment
    -> local RMS relative to a healthy collective
    -> absolute per-unit threshold
    -> hysteresis and persistence
    -> bounded event block
    -> duration subtype

The behavioral distinction is:

    sag:          0.1 <= retained RMS < 0.9 pu
    interruption: retained RMS < 0.1 pu

Duration labels an interruption as instantaneous, momentary, temporary,
or sustained. The thresholds are configurable. This is a synthetic
research prototype and is not yet field calibrated.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Mapping, Sequence
import math
import numpy as np
from numpy.typing import NDArray

import gamma_sag_seed_v01 as core

Array = NDArray[np.float64]


@dataclass(frozen=True)
class InterruptionConfig:
    candidate_windows: tuple[int, ...] = (11, 21, 41, 81)
    max_alignment_lag: int = 25
    nominal_frequency_hz: float = 60.0

    # Absolute retained-RMS classification boundary.
    interruption_enter_pu: float = 0.10

    # Hysteresis only; not the formal classification boundary.
    interruption_exit_pu: float = 0.12

    # Statistical guard relative to learned healthy behavior.
    enter_sigma: float = 3.0
    exit_sigma: float = 1.25

    # Duration and persistence are expressed in cycles where useful.
    enter_persistence_cycles: float = 0.50
    exit_persistence_cycles: float = 0.50
    minimum_interruption_cycles: float = 0.50

    # Duration subtype boundaries.
    instantaneous_max_cycles: float = 30.0
    momentary_max_s: float = 3.0
    temporary_max_s: float = 60.0

    baseline_variance_threshold: float = 0.95
    baseline_max_noise_modes: int = 12
    minimum_support_confidence: float = 0.55
    epsilon: float = 1e-9

    def __post_init__(self) -> None:
        if not self.candidate_windows:
            raise ValueError("candidate_windows cannot be empty")
        for width in self.candidate_windows:
            if width < 5 or width % 2 == 0:
                raise ValueError("candidate windows must be odd and >= 5")
        if self.nominal_frequency_hz <= 0:
            raise ValueError("nominal_frequency_hz must be positive")
        if not (
            0.0
            < self.interruption_enter_pu
            < self.interruption_exit_pu
            < 1.0
        ):
            raise ValueError(
                "require 0 < enter_pu < exit_pu < 1"
            )
        if self.enter_sigma <= self.exit_sigma:
            raise ValueError("enter_sigma must exceed exit_sigma")
        if min(
            self.enter_persistence_cycles,
            self.exit_persistence_cycles,
            self.minimum_interruption_cycles,
            self.instantaneous_max_cycles,
            self.momentary_max_s,
            self.temporary_max_s,
        ) <= 0:
            raise ValueError("durations must be positive")
        if self.temporary_max_s <= self.momentary_max_s:
            raise ValueError(
                "temporary_max_s must exceed momentary_max_s"
            )

    @property
    def cycle_s(self) -> float:
        return 1.0 / self.nominal_frequency_hz

    @property
    def enter_persistence_s(self) -> float:
        return self.enter_persistence_cycles * self.cycle_s

    @property
    def exit_persistence_s(self) -> float:
        return self.exit_persistence_cycles * self.cycle_s

    @property
    def minimum_event_s(self) -> float:
        return self.minimum_interruption_cycles * self.cycle_s

    def as_core_config(self) -> core.SagConfig:
        # The core config is used only to build the healthy baseline.
        return core.SagConfig(
            candidate_windows=self.candidate_windows,
            max_alignment_lag=self.max_alignment_lag,
            enter_sigma=self.enter_sigma,
            exit_sigma=self.exit_sigma,
            enter_persistence_s=self.enter_persistence_s,
            exit_persistence_s=self.exit_persistence_s,
            minimum_event_s=self.minimum_event_s,
            baseline_variance_threshold=self.baseline_variance_threshold,
            baseline_max_noise_modes=self.baseline_max_noise_modes,
            minimum_support_confidence=self.minimum_support_confidence,
            epsilon=self.epsilon,
        )


@dataclass(frozen=True)
class InterruptionWindowAnalysis:
    width: int
    retained_rms_pu: Array
    rms_z: Array
    beta: Array
    alpha: Array
    correlation: Array
    valid_mask: Array
    raw_events: tuple[tuple[int, int, bool], ...]
    score: float
    fragmentation_count: int


@dataclass(frozen=True)
class InterruptionEvent:
    start_index: int
    end_index: int
    start_time: float
    end_time: float
    duration_s: float
    duration_cycles: float
    open_ended: bool
    refined_entry_index: int
    refined_recovery_index: int

    minimum_retained_rms_pu: float
    median_retained_rms_pu: float
    missing_magnitude_area_pu_s: float
    below_threshold_area_pu_s: float

    entry_slope_pu_per_s: float
    recovery_slope_pu_per_s: float
    entry_timescale_s: float
    recovery_timescale_s: float

    known_noise_energy: float
    unknown_residual_energy: float

    subtype: str
    confidence: float


@dataclass(frozen=True)
class InterruptionEvidence:
    status: str
    selected_window: int
    alignment_lag_samples: int
    alignment_correlation: float
    events: tuple[InterruptionEvent, ...]
    window_scores: Mapping[int, float]

    retained_rms_pu_trace: Array
    rms_z_trace: Array
    beta_trace: Array
    alpha_trace: Array
    correlation_trace: Array

    reconstructed_waveform: Array
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


def fit_interruption_baseline(
    healthy_captures: Array,
    sample_interval: float,
    config: InterruptionConfig = InterruptionConfig(),
) -> core.SagBaseline:
    return core.fit_sag_baseline(
        healthy_captures,
        sample_interval,
        config.as_core_config(),
    )


def _detect_blocks(
    retained_pu: Array,
    rms_z: Array,
    valid_mask: Array,
    dt: float,
    config: InterruptionConfig,
) -> tuple[tuple[int, int, bool], ...]:
    """Absolute-pu hysteresis plus learned-statistical confirmation."""

    enter_n = max(
        1,
        int(math.ceil(config.enter_persistence_s / dt)),
    )
    exit_n = max(
        1,
        int(math.ceil(config.exit_persistence_s / dt)),
    )
    minimum_n = max(
        1,
        int(math.ceil(config.minimum_event_s / dt)),
    )

    events: list[tuple[int, int, bool]] = []
    active = False
    pending_enter: int | None = None
    pending_exit: int | None = None
    event_start = 0

    for i, q in enumerate(retained_pu):
        valid = bool(
            valid_mask[i]
            and np.isfinite(q)
            and np.isfinite(rms_z[i])
        )

        if not active:
            enter_condition = (
                valid
                and q < config.interruption_enter_pu
                and rms_z[i] <= -config.enter_sigma
            )
            if enter_condition:
                if pending_enter is None:
                    pending_enter = i
                if i - pending_enter + 1 >= enter_n:
                    active = True
                    event_start = pending_enter
                    pending_enter = None
                    pending_exit = None
            else:
                pending_enter = None
        else:
            recovered = (
                (not valid)
                or q >= config.interruption_exit_pu
                or rms_z[i] >= -config.exit_sigma
            )
            if recovered:
                if pending_exit is None:
                    pending_exit = i
                if i - pending_exit + 1 >= exit_n:
                    event_end = pending_exit
                    if event_end - event_start + 1 >= minimum_n:
                        events.append(
                            (event_start, event_end, False)
                        )
                    active = False
                    pending_enter = None
                    pending_exit = None
            else:
                pending_exit = None

    if active:
        event_end = retained_pu.size - 1
        if event_end - event_start + 1 >= minimum_n:
            events.append((event_start, event_end, True))

    return tuple(events)


def _window_score(
    width: int,
    events: Sequence[tuple[int, int, bool]],
    retained_pu: Array,
    dt: float,
    config: InterruptionConfig,
) -> float:
    if not events:
        return -2.0 - 0.001 * width

    event_scores: list[float] = []
    for start, end, _ in events:
        sl = slice(start, end + 1)
        median_q = float(np.nanmedian(retained_pu[sl]))
        duration = (end - start + 1) * dt
        depth_margin = np.clip(
            (
                config.interruption_enter_pu
                - median_q
            )
            / config.interruption_enter_pu,
            0.0,
            1.0,
        )
        blur_ratio = width * dt / max(duration, dt)
        event_scores.append(
            5.0 * depth_margin
            + 0.25 * math.log1p(
                duration / config.minimum_event_s
            )
            - 0.40 * blur_ratio
        )

    fragmentation = max(0, len(events) - 1)
    return max(event_scores) - 0.75 * fragmentation


def analyze_interruption_window(
    baseline: core.SagBaseline,
    aligned_signal: Array,
    width: int,
    config: InterruptionConfig,
) -> InterruptionWindowAnalysis:
    model = baseline.window_models[width]
    beta, alpha, corr, rms_ratio, valid = (
        core.local_affine_features(
            baseline.mean_waveform,
            aligned_signal,
            width,
            config.epsilon,
        )
    )
    valid = valid & model.valid_mask

    # Normalize the local RMS ratio by the learned healthy center.
    # This is the retained local RMS in per-unit form.
    retained_pu = rms_ratio / (
        model.rms_center + config.epsilon
    )
    rms_z = (
        rms_ratio - model.rms_center
    ) / (model.rms_scale + config.epsilon)

    retained_pu = np.where(valid, retained_pu, np.nan)
    rms_z = np.where(valid, rms_z, np.nan)

    events = _detect_blocks(
        retained_pu,
        rms_z,
        valid,
        baseline.sample_interval,
        config,
    )
    score = _window_score(
        width,
        events,
        retained_pu,
        baseline.sample_interval,
        config,
    )

    return InterruptionWindowAnalysis(
        width=width,
        retained_rms_pu=retained_pu,
        rms_z=rms_z,
        beta=beta,
        alpha=alpha,
        correlation=corr,
        valid_mask=valid,
        raw_events=events,
        score=float(score),
        fragmentation_count=max(0, len(events) - 1),
    )


def _refine_transition_indices(
    retained_pu: Array,
    start: int,
    end: int,
    width: int,
    dt: float,
) -> tuple[int, int, Array, Array]:
    smooth = core._smooth_trace(retained_pu, width)
    derivative = np.gradient(smooth, dt)
    radius = max(width, 10)

    left_lo = max(1, start - radius)
    left_hi = min(len(retained_pu) - 1, start + radius)
    right_lo = max(1, end - radius)
    right_hi = min(len(retained_pu) - 1, end + radius)

    entry = (
        left_lo
        + int(np.argmin(derivative[left_lo:left_hi]))
        if left_hi > left_lo
        else start
    )
    recovery = (
        right_lo
        + int(np.argmax(derivative[right_lo:right_hi]))
        if right_hi > right_lo
        else end
    )
    return entry, recovery, smooth, derivative


def _duration_subtype(
    duration_s: float,
    config: InterruptionConfig,
) -> str:
    cycles = duration_s * config.nominal_frequency_hz

    if cycles < config.minimum_interruption_cycles:
        return "subcycle_collapse"
    if cycles <= config.instantaneous_max_cycles:
        return "instantaneous_interruption"
    if duration_s <= config.momentary_max_s:
        return "momentary_interruption"
    if duration_s <= config.temporary_max_s:
        return "temporary_interruption"
    return "sustained_interruption"


def _event_confidence(
    median_pu: float,
    duration_s: float,
    open_ended: bool,
    config: InterruptionConfig,
) -> float:
    depth = np.clip(
        (
            config.interruption_enter_pu - median_pu
        )
        / config.interruption_enter_pu,
        0.0,
        1.0,
    )
    duration_support = 1.0 - math.exp(
        -duration_s / max(config.minimum_event_s, 1e-12)
    )
    bounded = 0.85 if open_ended else 1.0
    return float(
        np.clip(
            depth
            * (0.55 + 0.45 * duration_support)
            * bounded,
            0.0,
            1.0,
        )
    )


def run_interruption_seed(
    baseline: core.SagBaseline,
    waveform: Array,
    config: InterruptionConfig = InterruptionConfig(),
) -> InterruptionEvidence:
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
        analyze_interruption_window(
            baseline,
            aligned,
            width,
            config,
        )
        for width in config.candidate_windows
    ]
    selected = max(analyses, key=lambda item: item.score)

    retained_pu = core._fill_invalid(
        selected.retained_rms_pu,
        fallback=1.0,
    )
    rms_z = core._fill_invalid(
        selected.rms_z,
        fallback=0.0,
    )
    beta = core._fill_invalid(
        selected.beta,
        fallback=1.0,
    )
    alpha = core._fill_invalid(
        selected.alpha,
        fallback=0.0,
    )
    correlation = core._fill_invalid(
        selected.correlation,
        fallback=0.0,
    )

    reconstructed = (
        alpha + beta * baseline.mean_waveform
    )
    residual = aligned - reconstructed
    known_noise, unknown = core._residual_decomposition(
        baseline,
        residual,
    )

    events: list[InterruptionEvent] = []
    for start, end, open_ended in selected.raw_events:
        (
            entry,
            recovery,
            smooth_q,
            derivative,
        ) = _refine_transition_indices(
            retained_pu,
            start,
            end,
            selected.width,
            baseline.sample_interval,
        )

        sl = slice(start, end + 1)
        local_q = retained_pu[sl]
        min_q = float(np.min(local_q))
        median_q = float(np.median(local_q))

        missing_area = (
            float(
                np.trapezoid(
                    np.maximum(0.0, 1.0 - local_q),
                    dx=baseline.sample_interval,
                )
            )
            if local_q.size > 1
            else 0.0
        )
        below_threshold_area = (
            float(
                np.trapezoid(
                    np.maximum(
                        0.0,
                        config.interruption_enter_pu
                        - local_q,
                    ),
                    dx=baseline.sample_interval,
                )
            )
            if local_q.size > 1
            else 0.0
        )

        entry_slope = float(derivative[entry])
        recovery_slope = float(derivative[recovery])
        collapse_amplitude = max(0.0, 1.0 - min_q)
        entry_tau = collapse_amplitude / (
            abs(entry_slope) + config.epsilon
        )
        recovery_tau = collapse_amplitude / (
            abs(recovery_slope) + config.epsilon
        )

        duration_s = (
            end - start + 1
        ) * baseline.sample_interval
        duration_cycles = (
            duration_s * config.nominal_frequency_hz
        )
        subtype = _duration_subtype(
            duration_s,
            config,
        )
        confidence = _event_confidence(
            median_q,
            duration_s,
            open_ended,
            config,
        )

        standardized_unknown = unknown[sl] / (
            baseline.pointwise_std[sl]
            + config.epsilon
        )
        standardized_known = known_noise[sl] / (
            baseline.pointwise_std[sl]
            + config.epsilon
        )
        unknown_energy = float(
            np.mean(standardized_unknown**2)
        )
        known_energy = float(
            np.mean(standardized_known**2)
        )

        # The formal support condition remains the absolute
        # retained-RMS threshold. Correlation is not required
        # because almost no waveform may remain to correlate.
        supported = (
            median_q < config.interruption_enter_pu
            and duration_cycles
            >= config.minimum_interruption_cycles
        )
        if not supported:
            subtype = "ambiguous_low_voltage_event"

        events.append(
            InterruptionEvent(
                start_index=int(start),
                end_index=int(end),
                start_time=float(
                    start * baseline.sample_interval
                ),
                end_time=float(
                    end * baseline.sample_interval
                ),
                duration_s=float(duration_s),
                duration_cycles=float(duration_cycles),
                open_ended=bool(open_ended),
                refined_entry_index=int(entry),
                refined_recovery_index=int(recovery),
                minimum_retained_rms_pu=min_q,
                median_retained_rms_pu=median_q,
                missing_magnitude_area_pu_s=missing_area,
                below_threshold_area_pu_s=(
                    below_threshold_area
                ),
                entry_slope_pu_per_s=entry_slope,
                recovery_slope_pu_per_s=recovery_slope,
                entry_timescale_s=float(entry_tau),
                recovery_timescale_s=float(recovery_tau),
                known_noise_energy=known_energy,
                unknown_residual_energy=unknown_energy,
                subtype=subtype,
                confidence=confidence,
            )
        )

    supported_subtypes = {
        "instantaneous_interruption",
        "momentary_interruption",
        "temporary_interruption",
        "sustained_interruption",
    }
    supported_events = [
        event
        for event in events
        if event.subtype in supported_subtypes
    ]

    if not supported_events:
        status = (
            "ambiguous"
            if events
            else "rejected"
        )
    else:
        # Report the longest supported event subtype as the
        # top-level status while preserving every event.
        strongest = max(
            supported_events,
            key=lambda event: event.duration_s,
        )
        status = strongest.subtype

    return InterruptionEvidence(
        status=status,
        selected_window=selected.width,
        alignment_lag_samples=int(lag),
        alignment_correlation=float(alignment_corr),
        events=tuple(events),
        window_scores={
            analysis.width: analysis.score
            for analysis in analyses
        },
        retained_rms_pu_trace=retained_pu,
        rms_z_trace=rms_z,
        beta_trace=beta,
        alpha_trace=alpha,
        correlation_trace=correlation,
        reconstructed_waveform=reconstructed,
        residual=residual,
        known_noise_residual=known_noise,
        unknown_residual=unknown,
        notes=(
            "Interruption support requires retained local RMS below 0.1 pu.",
            "The 0.12 pu recovery gate is detector hysteresis, not a classification boundary.",
            "Duration determines instantaneous, momentary, temporary, or sustained subtype.",
            "Correlation is recorded but is not required when the waveform collapses near zero.",
            "The 0.1 pu and duration rules determine support; confidence does not veto a standards-defined event.",
            "Synthetic prototype only; no field-calibration claim.",
        ),
    )
