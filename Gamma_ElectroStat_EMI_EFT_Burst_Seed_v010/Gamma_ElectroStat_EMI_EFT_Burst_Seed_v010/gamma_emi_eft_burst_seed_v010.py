
"""Gamma / ElectroStat EMI EFT burst seed v0.1.0.

Purpose
-------
Analyze electrical-fast-transient / burst measurements as a hierarchy:

    acquisition observability
    -> individual pulse morphology
    -> repeatable pulse template and residuals
    -> post-pulse real-decay / oscillatory modes
    -> pulse-train timing and drift
    -> burst-scale consequence

The worker does not claim IEC compliance, causal component identification,
field accuracy, or calibrated probability. SNR is intentionally deferred.
Every result therefore reports ``snr_evaluated = False`` and uses categorical,
provisional evidence labels rather than confidence percentages.

The explicit waveform always remains available. Feature tables and pole
clusters are coordinate systems, not replacements for the measured data.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable
import json
import math
import zipfile

import numpy as np
from numpy.typing import NDArray
import pandas as pd
import matplotlib.pyplot as plt
from scipy.ndimage import binary_closing, binary_dilation
from scipy.signal import correlate, correlation_lags, find_peaks
from numpy.lib.stride_tricks import sliding_window_view
from threadpoolctl import threadpool_limits

Array = NDArray[np.float64]


# ---------------------------------------------------------------------------
# Configuration and output models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EFTAcquisitionMetadata:
    scope_model: str = "unknown"
    probe_model: str = "unknown"
    analog_bandwidth_hz: float | None = None
    probe_bandwidth_hz: float | None = None
    bandwidth_limit_hz: float | None = None
    adc_bits: int | None = None
    vertical_min_v: float | None = None
    vertical_max_v: float | None = None
    input_impedance_ohm: float | None = None
    coupling: str = "unknown"
    acquisition_mode: str = "real_time"
    averaging_count: int = 1
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EFTConfig:
    # Nominal feature scale used only for acquisition observability.
    nominal_rise_time_s: float = 5e-9

    # Detail-event segmentation. These are robust activity multipliers,
    # not SNR calculations.
    residual_activity_multiplier: float = 6.0
    derivative_activity_multiplier: float = 7.0
    derivative_residual_gate_multiplier: float = 1.5
    detail_event_padding_s: float = 12e-9
    detail_merge_gap_s: float = 8e-9
    detail_min_event_width_s: float = 1e-9
    detail_max_event_width_s: float = 2e-6

    # Pulse-local windows.
    template_pre_peak_s: float = 20e-9
    template_post_peak_s: float = 180e-9
    recovery_hold_s: float = 10e-9
    recovery_fraction: float = 0.05
    ring_start_after_peak_s: float = 12e-9
    ring_window_s: float = 60e-9

    # Matrix pencil / modal support.
    pencil_rows_fraction: float = 0.42
    max_model_order: int = 6
    minimum_model_order: int = 2
    svd_relative_floor: float = 0.012
    minimum_mode_amplitude_fraction: float = 0.025
    minimum_ring_frequency_hz: float = 1e6
    maximum_ring_fraction_of_sample_rate: float = 0.45
    cluster_frequency_relative_tolerance: float = 0.10
    cluster_decay_relative_tolerance: float = 0.55
    minimum_cluster_occurrences: int = 3
    maximum_pencil_samples: int = 160

    # Overview pulse-train detection.
    overview_activity_multiplier: float = 6.0
    overview_minimum_peak_distance_fraction: float = 0.35
    expected_repetition_frequencies_hz: tuple[float, ...] = (5e3, 100e3)
    repetition_relative_tolerance: float = 0.30
    burst_gap_multiple: float = 5.0

    # EFT-like descriptive bounds. These are classification limits for this
    # research worker, not an IEC conformance decision.
    eft_like_max_rise_time_s: float = 25e-9
    eft_like_max_half_width_s: float = 500e-9
    minimum_detail_pulses: int = 3

    # Stability.
    bootstrap_iterations: int = 40
    bootstrap_seed: int = 610044
    epsilon: float = 1e-15

    def __post_init__(self) -> None:
        positive = (
            self.nominal_rise_time_s,
            self.residual_activity_multiplier,
            self.derivative_activity_multiplier,
            self.derivative_residual_gate_multiplier,
            self.template_pre_peak_s,
            self.template_post_peak_s,
            self.recovery_hold_s,
            self.recovery_fraction,
            self.ring_window_s,
            self.pencil_rows_fraction,
            self.svd_relative_floor,
            self.minimum_mode_amplitude_fraction,
            self.minimum_ring_frequency_hz,
            self.maximum_ring_fraction_of_sample_rate,
            self.cluster_frequency_relative_tolerance,
            self.cluster_decay_relative_tolerance,
            self.overview_activity_multiplier,
            self.overview_minimum_peak_distance_fraction,
            self.repetition_relative_tolerance,
            self.burst_gap_multiple,
            self.eft_like_max_rise_time_s,
            self.eft_like_max_half_width_s,
            self.epsilon,
        )
        if min(positive) <= 0:
            raise ValueError("EFTConfig positive-valued fields must be > 0")
        if not 0 < self.pencil_rows_fraction < 0.9:
            raise ValueError("pencil_rows_fraction must lie in (0, 0.9)")
        if not 0 < self.maximum_ring_fraction_of_sample_rate < 0.5:
            raise ValueError("maximum_ring_fraction_of_sample_rate must lie in (0, 0.5)")
        if self.minimum_model_order < 1 or self.max_model_order < self.minimum_model_order:
            raise ValueError("invalid model-order limits")
        if self.bootstrap_iterations < 20:
            raise ValueError("bootstrap_iterations must be >= 20")
        if self.maximum_pencil_samples < 48:
            raise ValueError("maximum_pencil_samples must be >= 48")


@dataclass(frozen=True)
class AcquisitionAssessment:
    sample_interval_s: float
    sample_rate_hz: float
    effective_bandwidth_hz: float | None
    estimated_instrument_rise_time_s: float | None
    samples_across_nominal_rise: float
    bandwidth_to_nominal_edge_ratio: float | None
    clipping_detected: bool
    uniformly_sampled: bool
    real_time_acquisition: bool
    observability_status: str
    flags: tuple[str, ...]


@dataclass(frozen=True)
class EFTResult:
    status: str
    snr_evaluated: bool
    confidence_status: str
    acquisition: AcquisitionAssessment
    pulse_features: pd.DataFrame
    pulse_template_time_s: Array
    pulse_template_v: Array
    aligned_pulse_windows_v: Array
    pulse_residuals_v: Array
    modes: pd.DataFrame
    mode_clusters: pd.DataFrame
    train_summary: pd.DataFrame
    burst_summary: pd.DataFrame
    overview_pulses: pd.DataFrame
    evidence: dict[str, str]
    diagnostics: dict[str, Any]
    notes: tuple[str, ...]

    def summary_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "snr_evaluated": self.snr_evaluated,
            "confidence_status": self.confidence_status,
            "acquisition": asdict(self.acquisition),
            "pulse_count": int(len(self.pulse_features)),
            "mode_count": int(len(self.modes)),
            "mode_cluster_count": int(len(self.mode_clusters)),
            "evidence": self.evidence,
            "train_summary": (
                self.train_summary.iloc[0].to_dict()
                if not self.train_summary.empty else {}
            ),
            "burst_count": int(len(self.burst_summary)),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Input validation and acquisition observability
# ---------------------------------------------------------------------------

def _validate_uniform_time(time_s: Array, minimum_samples: int = 32) -> tuple[Array, float]:
    time_s = np.asarray(time_s, dtype=float)
    if time_s.ndim != 1 or time_s.size < minimum_samples:
        raise ValueError(f"time_s must be 1D with at least {minimum_samples} samples")
    if not np.isfinite(time_s).all():
        raise ValueError("time_s contains non-finite values")
    steps = np.diff(time_s)
    dt = float(np.median(steps))
    if dt <= 0 or np.any(steps <= 0):
        raise ValueError("time_s must be strictly increasing")
    if np.max(np.abs(steps - dt)) > 0.01 * dt:
        raise ValueError("this seed currently requires uniform sampling")
    return time_s, dt


def _validate_capture_matrix(captures: Array, sample_count: int) -> Array:
    captures = np.asarray(captures, dtype=float)
    if captures.ndim == 1:
        captures = captures[None, :]
    if captures.ndim != 2 or captures.shape[1] != sample_count:
        raise ValueError("captures must have shape (capture_count, sample_count)")
    if not np.isfinite(captures).all():
        raise ValueError("captures contain non-finite values")
    return captures


def _effective_bandwidth(metadata: EFTAcquisitionMetadata) -> float | None:
    candidates = [
        metadata.analog_bandwidth_hz,
        metadata.probe_bandwidth_hz,
        metadata.bandwidth_limit_hz,
    ]
    values = [float(v) for v in candidates if v is not None and v > 0]
    return min(values) if values else None


def assess_acquisition(
    time_s: Array,
    captures: Array,
    metadata: EFTAcquisitionMetadata,
    config: EFTConfig = EFTConfig(),
) -> AcquisitionAssessment:
    time_s, dt = _validate_uniform_time(time_s)
    captures = _validate_capture_matrix(captures, time_s.size)
    fs = 1.0 / dt
    bandwidth = _effective_bandwidth(metadata)
    instrument_rise = 0.35 / bandwidth if bandwidth else None
    nominal_edge_bw = 0.35 / config.nominal_rise_time_s
    bandwidth_ratio = bandwidth / nominal_edge_bw if bandwidth else None
    samples_across = config.nominal_rise_time_s / dt

    clipping = False
    flags: list[str] = []
    if metadata.vertical_min_v is not None:
        margin = max(config.epsilon, 0.002 * max(1.0, abs(metadata.vertical_min_v)))
        if np.any(captures <= metadata.vertical_min_v + margin):
            clipping = True
            flags.append("lower_vertical_rail_contact")
    if metadata.vertical_max_v is not None:
        margin = max(config.epsilon, 0.002 * max(1.0, abs(metadata.vertical_max_v)))
        if np.any(captures >= metadata.vertical_max_v - margin):
            clipping = True
            flags.append("upper_vertical_rail_contact")

    mode = metadata.acquisition_mode.strip().lower()
    real_time = mode in {"real_time", "realtime", "real-time"}
    if not real_time:
        flags.append("non_real_time_acquisition")

    if clipping:
        status = "rejected"
    else:
        sample_grade = (
            3 if samples_across >= 15 else
            2 if samples_across >= 8 else
            1 if samples_across >= 4 else
            0
        )
        if bandwidth_ratio is None:
            bandwidth_grade = 1
            flags.append("bandwidth_metadata_missing")
        else:
            bandwidth_grade = (
                3 if bandwidth_ratio >= 5 else
                2 if bandwidth_ratio >= 3 else
                1 if bandwidth_ratio >= 1 else
                0
            )
        grade = min(sample_grade, bandwidth_grade)
        status = ("strongly_supported", "exploratory", "supported", "strongly_supported")[grade]
        if grade == 0:
            status = "rejected"
        if not real_time and status == "strongly_supported":
            status = "supported"

    if samples_across < 8:
        flags.append("limited_samples_across_nominal_edge")
    if bandwidth_ratio is not None and bandwidth_ratio < 3:
        flags.append("limited_analog_edge_bandwidth")
    if metadata.averaging_count > 1:
        flags.append("hardware_or_scope_averaging_enabled")

    return AcquisitionAssessment(
        sample_interval_s=dt,
        sample_rate_hz=fs,
        effective_bandwidth_hz=bandwidth,
        estimated_instrument_rise_time_s=instrument_rise,
        samples_across_nominal_rise=float(samples_across),
        bandwidth_to_nominal_edge_ratio=(
            float(bandwidth_ratio) if bandwidth_ratio is not None else None
        ),
        clipping_detected=clipping,
        uniformly_sampled=True,
        real_time_acquisition=real_time,
        observability_status=status,
        flags=tuple(flags),
    )


# ---------------------------------------------------------------------------
# Robust activity, pulse segmentation, and morphology
# ---------------------------------------------------------------------------

def _robust_location_scale(values: Array) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    center = float(np.median(values))
    mad = float(np.median(np.abs(values - center)))
    scale = max(1.4826 * mad, np.finfo(float).eps)
    return center, scale


def _segments(mask: NDArray[np.bool_]) -> list[tuple[int, int]]:
    edges = np.diff(mask.astype(np.int8), prepend=0, append=0)
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def _interpolated_crossing(
    time_s: Array,
    normalized: Array,
    level: float,
    start: int,
    stop: int,
    rising: bool,
) -> float:
    if stop <= start:
        return math.nan
    x = normalized[start:stop + 1]
    t = time_s[start:stop + 1]
    if rising:
        indices = np.flatnonzero((x[:-1] < level) & (x[1:] >= level))
    else:
        indices = np.flatnonzero((x[:-1] >= level) & (x[1:] < level))
    if indices.size == 0:
        return math.nan
    idx = int(indices[-1] if rising else indices[0])
    x0, x1 = float(x[idx]), float(x[idx + 1])
    if abs(x1 - x0) < np.finfo(float).eps:
        return float(t[idx])
    fraction = (level - x0) / (x1 - x0)
    return float(t[idx] + fraction * (t[idx + 1] - t[idx]))


def _pulse_morphology(
    time_s: Array,
    waveform: Array,
    start: int,
    stop: int,
    peak: int,
    capture_id: int,
    event_id: int,
    config: EFTConfig,
) -> dict[str, Any]:
    dt = float(np.median(np.diff(time_s)))
    pre_count = max(4, int(round(config.template_pre_peak_s / dt)))
    baseline_start = max(0, start - pre_count)
    baseline_stop = max(baseline_start + 1, start)
    baseline = float(np.median(waveform[baseline_start:baseline_stop]))
    centered = waveform - baseline

    signed_peak = float(centered[peak])
    polarity = 1.0 if signed_peak >= 0 else -1.0
    normalized = polarity * centered / max(abs(signed_peak), config.epsilon)

    t10 = _interpolated_crossing(time_s, normalized, 0.10, start, peak, True)
    t90 = _interpolated_crossing(time_s, normalized, 0.90, start, peak, True)
    rise_time = t90 - t10 if np.isfinite(t10) and np.isfinite(t90) else math.nan

    t50_rise = _interpolated_crossing(time_s, normalized, 0.50, start, peak, True)
    search_stop = min(stop, waveform.size - 1)
    t50_fall = _interpolated_crossing(time_s, normalized, 0.50, peak, search_stop, False)
    half_width = (
        t50_fall - t50_rise
        if np.isfinite(t50_rise) and np.isfinite(t50_fall)
        else math.nan
    )

    t90_fall = _interpolated_crossing(time_s, normalized, 0.90, peak, search_stop, False)
    t10_fall = _interpolated_crossing(time_s, normalized, 0.10, peak, search_stop, False)
    fall_time = (
        t10_fall - t90_fall
        if np.isfinite(t90_fall) and np.isfinite(t10_fall)
        else math.nan
    )

    derivative = np.gradient(centered, dt)
    local = centered[start:search_stop + 1]
    local_time = time_s[start:search_stop + 1]
    area = float(np.trapezoid(local, local_time))
    squared_voltage_integral = float(np.trapezoid(local * local, local_time))

    post = centered[peak:search_stop + 1]
    opposite = float(np.max(np.maximum(0.0, -polarity * post)))
    same_side_post = float(np.max(np.maximum(0.0, polarity * post[1:]))) if post.size > 1 else 0.0

    recovery_samples = max(2, int(round(config.recovery_hold_s / dt)))
    recovery_level = config.recovery_fraction * max(abs(signed_peak), config.epsilon)
    recovery_time = math.nan
    for idx in range(peak + 1, waveform.size - recovery_samples + 1):
        if np.all(np.abs(centered[idx:idx + recovery_samples]) <= recovery_level):
            recovery_time = float(time_s[idx] - time_s[peak])
            break

    peaks, _ = find_peaks(np.abs(local), height=0.10 * max(abs(signed_peak), config.epsilon))
    secondary_peak_count = max(0, int(peaks.size - 1))

    post_baseline_start = min(waveform.size - 1, peak + recovery_samples)
    post_baseline = float(np.median(centered[post_baseline_start:]))

    return {
        "capture_id": capture_id,
        "event_id": event_id,
        "start_index": int(start),
        "peak_index": int(peak),
        "stop_index": int(stop),
        "start_time_s": float(time_s[start]),
        "peak_time_s": float(time_s[peak]),
        "stop_time_s": float(time_s[stop - 1]),
        "baseline_v": baseline,
        "polarity": "positive" if polarity > 0 else "negative",
        "signed_peak_v": signed_peak,
        "peak_abs_v": abs(signed_peak),
        "peak_to_peak_v": float(np.ptp(local)),
        "rise_time_s": rise_time,
        "half_width_s": half_width,
        "fall_time_s": fall_time,
        "maximum_abs_dvdt_v_per_s": float(np.max(np.abs(derivative[start:search_stop + 1]))),
        "signed_area_v_s": area,
        "squared_voltage_integral_v2_s": squared_voltage_integral,
        "opposite_polarity_rebound_v": opposite,
        "same_polarity_post_peak_v": same_side_post,
        "secondary_peak_count": secondary_peak_count,
        "post_event_baseline_shift_v": post_baseline,
        "recovery_time_s": recovery_time,
    }


def detect_detail_pulses(
    time_s: Array,
    captures: Array,
    config: EFTConfig = EFTConfig(),
) -> tuple[pd.DataFrame, list[tuple[int, int, int, int]]]:
    time_s, dt = _validate_uniform_time(time_s)
    captures = _validate_capture_matrix(captures, time_s.size)
    fs = 1.0 / dt
    pad = max(1, int(round(config.detail_event_padding_s * fs)))
    merge = max(1, int(round(config.detail_merge_gap_s * fs)))

    rows: list[dict[str, Any]] = []
    event_indices: list[tuple[int, int, int, int]] = []
    event_id = 0

    for capture_id, waveform in enumerate(captures):
        pre_count = max(8, min(waveform.size // 5, int(round(config.template_pre_peak_s / dt))))
        baseline_region = waveform[:pre_count]
        center, scale = _robust_location_scale(baseline_region)
        centered = waveform - center
        derivative = np.gradient(centered, dt)
        derivative_center, derivative_scale = _robust_location_scale(derivative[:pre_count])

        amplitude_activity = (
            np.abs(centered) >
            config.residual_activity_multiplier * scale
        )
        derivative_activity = (
            np.abs(derivative - derivative_center) >
            config.derivative_activity_multiplier * derivative_scale
        ) & (
            np.abs(centered) >
            config.derivative_residual_gate_multiplier * scale
        )
        activity = amplitude_activity | derivative_activity
        activity = binary_dilation(activity, structure=np.ones(2 * pad + 1, dtype=bool))
        activity = binary_closing(activity, structure=np.ones(merge, dtype=bool))

        for start, stop in _segments(activity):
            width = (stop - start) * dt
            if not (config.detail_min_event_width_s <= width <= config.detail_max_event_width_s):
                continue
            if stop - start < 3:
                continue
            peak = start + int(np.argmax(np.abs(centered[start:stop])))
            event_id += 1
            rows.append(
                _pulse_morphology(
                    time_s, waveform, start, stop, peak,
                    capture_id, event_id, config
                )
            )
            event_indices.append((capture_id, start, peak, stop))

    return pd.DataFrame(rows), event_indices


# ---------------------------------------------------------------------------
# Pulse alignment, explicit template, residual geometry
# ---------------------------------------------------------------------------

def _fractional_lag(reference: Array, candidate: Array) -> float:
    reference = np.asarray(reference, dtype=float)
    candidate = np.asarray(candidate, dtype=float)
    reference = reference - np.mean(reference)
    candidate = candidate - np.mean(candidate)
    corr = correlate(candidate, reference, mode="full", method="fft")
    lags = correlation_lags(candidate.size, reference.size, mode="full")
    best = int(np.argmax(corr))
    lag = float(lags[best])
    if 0 < best < corr.size - 1:
        y0, y1, y2 = corr[best - 1:best + 2]
        denominator = y0 - 2.0 * y1 + y2
        if abs(denominator) > np.finfo(float).eps:
            lag += 0.5 * (y0 - y2) / denominator
    return lag


def _shift_by_samples(values: Array, lag_samples: float) -> Array:
    x = np.arange(values.size, dtype=float)
    return np.interp(
        x,
        x + lag_samples,
        values,
        left=float(values[0]),
        right=float(values[-1]),
    )


def build_pulse_template(
    time_s: Array,
    captures: Array,
    pulse_features: pd.DataFrame,
    config: EFTConfig = EFTConfig(),
) -> tuple[Array, Array, Array, Array, pd.DataFrame]:
    time_s, dt = _validate_uniform_time(time_s)
    captures = _validate_capture_matrix(captures, time_s.size)
    if pulse_features.empty:
        return (
            np.empty(0),
            np.empty(0),
            np.empty((0, 0)),
            np.empty((0, 0)),
            pulse_features.copy(),
        )

    pre = max(2, int(round(config.template_pre_peak_s / dt)))
    post = max(8, int(round(config.template_post_peak_s / dt)))
    length = pre + post + 1

    windows: list[Array] = []
    kept_rows: list[int] = []
    for row_index, row in pulse_features.iterrows():
        capture_id = int(row["capture_id"])
        peak = int(row["peak_index"])
        start = peak - pre
        stop = peak + post + 1
        if start < 0 or stop > captures.shape[1]:
            continue
        window = captures[capture_id, start:stop].copy()
        # Reuse the pre-event baseline estimated during segmentation.  The
        # pulse may begin well before its peak, so estimating baseline from
        # the first half of a peak-centered window can subtract part of the
        # real leading edge and corrupt the explicit waveform.
        baseline = float(row.get("baseline_v", np.median(window[:max(2, pre // 2)])))
        window -= baseline
        windows.append(window)
        kept_rows.append(row_index)

    if not windows:
        return (
            np.empty(0),
            np.empty(0),
            np.empty((0, 0)),
            np.empty((0, 0)),
            pulse_features.iloc[0:0].copy(),
        )

    raw = np.vstack(windows)
    reference = np.median(raw, axis=0)
    aligned = np.empty_like(raw)
    lags: list[float] = []

    for index, window in enumerate(raw):
        lag = _fractional_lag(np.gradient(reference), np.gradient(window))
        lags.append(lag)
        aligned[index] = _shift_by_samples(window, -lag)

    template = np.median(aligned, axis=0)
    residuals = aligned - template[None, :]
    retained = pulse_features.loc[kept_rows].copy().reset_index(drop=True)
    amplitudes = np.maximum(np.max(np.abs(aligned), axis=1), config.epsilon)
    retained["alignment_lag_samples"] = lags
    retained["template_residual_rms_fraction"] = (
        np.sqrt(np.mean(residuals * residuals, axis=1)) / amplitudes
    )
    template_time = (np.arange(length) - pre) * dt
    return template_time, template, aligned, residuals, retained


# ---------------------------------------------------------------------------
# Matrix pencil and repeated mode clustering
# ---------------------------------------------------------------------------

def _hankel_pair(signal: Array, rows: int) -> tuple[np.ndarray, np.ndarray]:
    signal = np.asarray(signal, dtype=np.complex128)
    rows = max(2, min(int(rows), signal.size - 2))
    windows = sliding_window_view(signal, rows + 1)
    return windows[:, :rows].T.copy(), windows[:, 1:].T.copy()


def _select_model_order(singular_values: Array, config: EFTConfig) -> int:
    maximum = min(config.max_model_order, max(1, singular_values.size - 1))
    if maximum <= config.minimum_model_order:
        return maximum
    relative = singular_values[:maximum] / max(singular_values[0], config.epsilon)
    eligible = np.flatnonzero(relative >= config.svd_relative_floor)
    candidate_count = int(eligible[-1]) + 1 if eligible.size else config.minimum_model_order
    gaps = singular_values[:maximum] / np.maximum(
        singular_values[1:maximum + 1], config.epsilon
    )
    search_stop = max(config.minimum_model_order, min(candidate_count, gaps.size))
    order = int(np.argmax(gaps[:search_stop])) + 1
    return max(config.minimum_model_order, min(order, maximum))


def matrix_pencil_modes(
    signal: Array,
    sample_interval_s: float,
    config: EFTConfig = EFTConfig(),
) -> tuple[pd.DataFrame, dict[str, Any]]:
    signal = np.asarray(signal, dtype=float)
    if signal.ndim != 1 or signal.size < 24:
        return pd.DataFrame(), {"reason": "insufficient_samples"}

    # Bound matrix size for repeated-pulse analysis. Uniform decimation is
    # safe here only when the retained Nyquist rate still exceeds the configured
    # modal search ceiling.
    original_dt = sample_interval_s
    if signal.size > config.maximum_pencil_samples:
        factor = int(math.ceil(signal.size / config.maximum_pencil_samples))
        candidate_dt = sample_interval_s * factor
        candidate_fs = 1.0 / candidate_dt
        if config.minimum_ring_frequency_hz < config.maximum_ring_fraction_of_sample_rate * candidate_fs:
            signal = signal[::factor]
            sample_interval_s = candidate_dt

    signal = signal - np.median(signal[-max(4, signal.size // 10):])
    scale = float(np.max(np.abs(signal)))
    if scale <= config.epsilon:
        return pd.DataFrame(), {"reason": "zero_signal"}
    normalized = signal / scale

    rows = int(round(config.pencil_rows_fraction * normalized.size))
    h0, h1 = _hankel_pair(normalized, rows)
    with threadpool_limits(limits=1, user_api="blas"):
        u, s, vh = np.linalg.svd(h0, full_matrices=False)
    order = _select_model_order(s, config)

    ur = u[:, :order]
    vr = vh.conj().T[:, :order]
    shift = ur.conj().T @ h1 @ vr @ np.diag(1.0 / np.maximum(s[:order], config.epsilon))
    z = np.linalg.eigvals(shift)
    z = z[np.isfinite(z) & (np.abs(z) > config.epsilon)]
    if z.size == 0:
        return pd.DataFrame(), {"reason": "no_finite_poles"}

    p = np.log(z) / sample_interval_s
    k = np.arange(normalized.size)
    vandermonde = np.column_stack([pole ** k for pole in z])
    amplitudes, *_ = np.linalg.lstsq(vandermonde, normalized, rcond=None)
    reconstruction = np.real(vandermonde @ amplitudes)
    denominator = max(
        float(np.linalg.norm(normalized - np.mean(normalized))),
        config.epsilon,
    )
    nrmse = float(np.linalg.norm(normalized - reconstruction) / denominator)
    maximum_amplitude = max(float(np.max(np.abs(amplitudes))), config.epsilon)

    rows_out: list[dict[str, Any]] = []
    for mode_index, (zp, pp, amplitude) in enumerate(zip(z, p, amplitudes), start=1):
        decay = -float(pp.real)
        imag = float(pp.imag)
        frequency = abs(imag) / (2.0 * np.pi)
        natural = float(np.hypot(decay, imag))
        amplitude_fraction = float(abs(amplitude) / maximum_amplitude)
        if decay <= 0:
            continue
        if amplitude_fraction < config.minimum_mode_amplitude_fraction:
            continue

        if abs(imag) < 2.0 * np.pi * config.minimum_ring_frequency_hz:
            mode_type = "real_decay"
        elif imag > 0 and frequency < (
            config.maximum_ring_fraction_of_sample_rate / sample_interval_s
        ):
            mode_type = "oscillatory"
        else:
            continue

        rows_out.append({
            "mode_index": mode_index,
            "mode_type": mode_type,
            "frequency_hz": frequency if mode_type == "oscillatory" else 0.0,
            "decay_rate_per_s": decay,
            "time_constant_s": 1.0 / decay,
            "estimated_four_tau_settling_s": 4.0 / decay,
            "damping_ratio": decay / natural if natural > 0 else math.nan,
            "amplitude_abs_v": float(abs(amplitude) * scale * (2.0 if mode_type == "oscillatory" else 1.0)),
            "amplitude_fraction": amplitude_fraction,
            "phase_rad": float(np.angle(amplitude)),
            "continuous_pole_real_per_s": float(pp.real),
            "continuous_pole_imag_rad_per_s": imag,
            "discrete_pole_real": float(zp.real),
            "discrete_pole_imag": float(zp.imag),
            "model_order": order,
            "reconstruction_nrmse": nrmse,
        })

    return pd.DataFrame(rows_out), {
        "singular_values": s,
        "selected_model_order": order,
        "reconstruction": reconstruction * scale,
        "reconstruction_nrmse": nrmse,
    }


def extract_modes_from_aligned_pulses(
    template_time_s: Array,
    aligned_windows: Array,
    config: EFTConfig = EFTConfig(),
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if aligned_windows.size == 0 or template_time_s.size == 0:
        return pd.DataFrame(), pd.DataFrame(), {}

    dt = float(np.median(np.diff(template_time_s)))
    peak_index = int(np.argmin(np.abs(template_time_s)))
    ring_start = peak_index + max(1, int(round(config.ring_start_after_peak_s / dt)))
    ring_count = max(24, int(round(config.ring_window_s / dt)))
    ring_stop = min(aligned_windows.shape[1], ring_start + ring_count)
    if ring_stop - ring_start < 24:
        return pd.DataFrame(), pd.DataFrame(), {"reason": "ring_window_too_short"}

    mode_frames: list[pd.DataFrame] = []
    per_pulse_diagnostics: dict[int, Any] = {}
    for pulse_index, window in enumerate(aligned_windows):
        segment = window[ring_start:ring_stop]
        stride = max(1, int(math.ceil(segment.size / 192)))
        segment = segment[::stride]
        effective_dt = dt * stride
        modes, diagnostics = matrix_pencil_modes(
            segment, effective_dt, config
        )
        diagnostics["decimation_stride"] = stride
        per_pulse_diagnostics[pulse_index] = diagnostics
        if modes.empty:
            continue
        modes.insert(0, "pulse_index", pulse_index)
        mode_frames.append(modes)

    all_modes = (
        pd.concat(mode_frames, ignore_index=True)
        if mode_frames else pd.DataFrame()
    )
    clusters = cluster_modes(all_modes, aligned_windows.shape[0], config)
    return all_modes, clusters, {
        "ring_start_index": ring_start,
        "ring_stop_index": ring_stop,
        "per_pulse": per_pulse_diagnostics,
    }


def cluster_modes(
    modes: pd.DataFrame,
    pulse_count: int,
    config: EFTConfig = EFTConfig(),
) -> pd.DataFrame:
    if modes.empty:
        return pd.DataFrame()

    records: list[dict[str, Any]] = []
    working = modes.copy()
    working["cluster_id"] = -1
    clusters: list[dict[str, Any]] = []

    for mode_type in ("oscillatory", "real_decay"):
        subset_indices = list(working.index[working["mode_type"] == mode_type])
        key = "frequency_hz" if mode_type == "oscillatory" else "decay_rate_per_s"
        subset_indices.sort(key=lambda idx: float(working.loc[idx, key]))

        for index in subset_indices:
            frequency = float(working.loc[index, "frequency_hz"])
            decay = float(working.loc[index, "decay_rate_per_s"])
            best: dict[str, Any] | None = None
            best_distance = math.inf

            for cluster in clusters:
                if cluster["mode_type"] != mode_type:
                    continue
                center_f = float(np.median(cluster["frequencies"])) if mode_type == "oscillatory" else 0.0
                center_d = float(np.median(cluster["decays"]))
                f_distance = (
                    abs(frequency - center_f) / max(center_f, config.epsilon)
                    if mode_type == "oscillatory" else 0.0
                )
                d_distance = abs(decay - center_d) / max(center_d, config.epsilon)
                distance = f_distance + d_distance
                if (
                    f_distance <= config.cluster_frequency_relative_tolerance
                    and d_distance <= config.cluster_decay_relative_tolerance
                    and distance < best_distance
                ):
                    best = cluster
                    best_distance = distance

            if best is None:
                best = {
                    "cluster_id": len(clusters) + 1,
                    "mode_type": mode_type,
                    "frequencies": [],
                    "decays": [],
                    "indices": [],
                }
                clusters.append(best)

            best["frequencies"].append(frequency)
            best["decays"].append(decay)
            best["indices"].append(index)
            working.loc[index, "cluster_id"] = best["cluster_id"]

    for cluster in clusters:
        subset = working.loc[cluster["indices"]]
        unique_pulses = int(subset["pulse_index"].nunique())
        if unique_pulses < config.minimum_cluster_occurrences:
            support = "exploratory"
        elif unique_pulses >= max(config.minimum_cluster_occurrences, int(math.ceil(0.65 * pulse_count))):
            support = "strongly_supported"
        else:
            support = "supported"

        records.append({
            "cluster_id": cluster["cluster_id"],
            "mode_type": cluster["mode_type"],
            "mode_occurrence_count": int(len(subset)),
            "unique_pulse_count": unique_pulses,
            "occurrence_fraction": unique_pulses / max(pulse_count, 1),
            "median_frequency_hz": float(np.median(subset["frequency_hz"])),
            "frequency_mad_hz": float(
                np.median(np.abs(subset["frequency_hz"] - np.median(subset["frequency_hz"])))
            ),
            "median_decay_rate_per_s": float(np.median(subset["decay_rate_per_s"])),
            "decay_rate_mad_per_s": float(
                np.median(np.abs(subset["decay_rate_per_s"] - np.median(subset["decay_rate_per_s"])))
            ),
            "median_time_constant_s": float(np.median(subset["time_constant_s"])),
            "median_amplitude_abs_v": float(np.median(subset["amplitude_abs_v"])),
            "median_reconstruction_nrmse": float(np.median(subset["reconstruction_nrmse"])),
            "support_status": support,
        })

    return pd.DataFrame(records).sort_values(
        ["mode_type", "occurrence_fraction"],
        ascending=[True, False],
    ).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Overview pulse train and burst grouping
# ---------------------------------------------------------------------------

def analyze_overview(
    time_s: Array | None,
    waveform: Array | None,
    config: EFTConfig = EFTConfig(),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if time_s is None or waveform is None:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {"overview_available": False}

    time_s, dt = _validate_uniform_time(time_s, minimum_samples=64)
    waveform = np.asarray(waveform, dtype=float)
    if waveform.ndim != 1 or waveform.size != time_s.size:
        raise ValueError("overview waveform must match overview time")
    if not np.isfinite(waveform).all():
        raise ValueError("overview waveform contains non-finite values")

    baseline_count = max(16, waveform.size // 20)
    baseline, scale = _robust_location_scale(waveform[:baseline_count])
    centered = waveform - baseline
    absolute = np.abs(centered)
    threshold = config.overview_activity_multiplier * scale

    expected_max = max(config.expected_repetition_frequencies_hz)
    minimum_distance = max(
        1,
        int(round(
            config.overview_minimum_peak_distance_fraction
            / (expected_max * dt)
        )),
    )
    peaks, properties = find_peaks(
        absolute,
        height=threshold,
        distance=minimum_distance,
    )
    if peaks.size == 0:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {
            "overview_available": True,
            "threshold_v": threshold,
        }

    times = time_s[peaks]
    amplitudes = centered[peaks]
    intervals = np.diff(times)
    positive_intervals = intervals[intervals > 0]
    if positive_intervals.size:
        base_interval = float(np.median(positive_intervals))
    else:
        base_interval = math.nan

    if np.isfinite(base_interval):
        gap_threshold = config.burst_gap_multiple * base_interval
        burst_ids = np.ones(peaks.size, dtype=int)
        if intervals.size:
            burst_ids[1:] += np.cumsum(intervals > gap_threshold)
    else:
        burst_ids = np.ones(peaks.size, dtype=int)

    pulse_rows: list[dict[str, Any]] = []
    for index, peak in enumerate(peaks):
        pulse_rows.append({
            "overview_pulse_id": index + 1,
            "burst_id": int(burst_ids[index]),
            "sample_index": int(peak),
            "time_s": float(time_s[peak]),
            "signed_amplitude_v": float(amplitudes[index]),
            "peak_abs_v": float(abs(amplitudes[index])),
            "interval_from_previous_s": (
                float(intervals[index - 1]) if index > 0 else math.nan
            ),
        })
    pulse_table = pd.DataFrame(pulse_rows)

    within_intervals: list[float] = []
    burst_rows: list[dict[str, Any]] = []
    for burst_id, group in pulse_table.groupby("burst_id", sort=True):
        group = group.sort_values("time_s")
        local_intervals = np.diff(group["time_s"].to_numpy())
        within_intervals.extend(local_intervals.tolist())
        local_base = float(np.median(local_intervals)) if local_intervals.size else math.nan
        missing_count = 0
        if local_intervals.size and local_base > 0:
            multiples = np.maximum(1, np.rint(local_intervals / local_base).astype(int))
            missing_count = int(np.sum(multiples - 1))
        amplitude_values = group["peak_abs_v"].to_numpy()
        x = np.arange(amplitude_values.size, dtype=float)
        slope = (
            float(np.polyfit(x, amplitude_values, 1)[0])
            if amplitude_values.size >= 2 else 0.0
        )
        burst_rows.append({
            "burst_id": int(burst_id),
            "pulse_count": int(len(group)),
            "burst_start_time_s": float(group["time_s"].iloc[0]),
            "burst_end_time_s": float(group["time_s"].iloc[-1]),
            "burst_duration_s": float(group["time_s"].iloc[-1] - group["time_s"].iloc[0]),
            "median_interval_s": local_base,
            "repetition_frequency_hz": 1.0 / local_base if np.isfinite(local_base) and local_base > 0 else math.nan,
            "interval_mad_s": (
                float(np.median(np.abs(local_intervals - np.median(local_intervals))))
                if local_intervals.size else math.nan
            ),
            "inferred_missing_pulse_count": missing_count,
            "median_peak_abs_v": float(np.median(amplitude_values)),
            "amplitude_drift_v_per_pulse": slope,
        })
    burst_table = pd.DataFrame(burst_rows)

    within = np.asarray(within_intervals, dtype=float)
    median_interval = float(np.median(within)) if within.size else math.nan
    repetition = 1.0 / median_interval if np.isfinite(median_interval) and median_interval > 0 else math.nan
    nearest_expected = (
        min(config.expected_repetition_frequencies_hz, key=lambda f: abs(f - repetition))
        if np.isfinite(repetition) else math.nan
    )
    repetition_error = (
        abs(repetition - nearest_expected) / nearest_expected
        if np.isfinite(repetition) else math.nan
    )
    matched = bool(
        np.isfinite(repetition_error)
        and repetition_error <= config.repetition_relative_tolerance
    )

    train_table = pd.DataFrame([{
        "overview_pulse_count": int(len(pulse_table)),
        "burst_count": int(pulse_table["burst_id"].nunique()),
        "median_within_burst_interval_s": median_interval,
        "repetition_frequency_hz": repetition,
        "nearest_expected_repetition_hz": nearest_expected,
        "expected_repetition_match": matched,
        "repetition_relative_error": repetition_error,
        "interval_mad_s": (
            float(np.median(np.abs(within - np.median(within))))
            if within.size else math.nan
        ),
        "total_inferred_missing_pulse_count": int(
            burst_table["inferred_missing_pulse_count"].sum()
        ) if not burst_table.empty else 0,
    }])

    return pulse_table, train_table, burst_table, {
        "overview_available": True,
        "threshold_v": threshold,
        "baseline_v": baseline,
        "activity_scale_v": scale,
    }


# ---------------------------------------------------------------------------
# Provisional evidence without SNR
# ---------------------------------------------------------------------------

_SUPPORT_ORDER = {
    "rejected": 0,
    "exploratory": 1,
    "supported": 2,
    "strongly_supported": 3,
}


def _minimum_support(*statuses: str) -> str:
    valid = [status for status in statuses if status in _SUPPORT_ORDER]
    if not valid:
        return "exploratory"
    return min(valid, key=lambda status: _SUPPORT_ORDER[status])


def _bootstrap_stability(
    pulse_features: pd.DataFrame,
    config: EFTConfig,
) -> tuple[str, dict[str, float]]:
    if len(pulse_features) < 3:
        return "exploratory", {}
    rng = np.random.default_rng(config.bootstrap_seed)
    amplitude = pulse_features["peak_abs_v"].to_numpy(float)
    rise = pulse_features["rise_time_s"].to_numpy(float)
    rise = rise[np.isfinite(rise)]
    amplitude_medians: list[float] = []
    rise_medians: list[float] = []
    for _ in range(config.bootstrap_iterations):
        indices = rng.integers(0, amplitude.size, amplitude.size)
        amplitude_medians.append(float(np.median(amplitude[indices])))
        if rise.size:
            rise_indices = rng.integers(0, rise.size, rise.size)
            rise_medians.append(float(np.median(rise[rise_indices])))

    amp_center = max(abs(float(np.median(amplitude_medians))), config.epsilon)
    amp_relative_spread = float(np.std(amplitude_medians) / amp_center)
    if rise_medians:
        rise_center = max(abs(float(np.median(rise_medians))), config.epsilon)
        rise_relative_spread = float(np.std(rise_medians) / rise_center)
    else:
        rise_relative_spread = math.inf

    worst = max(amp_relative_spread, rise_relative_spread)
    status = (
        "strongly_supported" if worst <= 0.08 else
        "supported" if worst <= 0.20 else
        "exploratory"
    )
    return status, {
        "bootstrap_amplitude_median_relative_spread": amp_relative_spread,
        "bootstrap_rise_median_relative_spread": rise_relative_spread,
    }


def _repeatability_support(pulse_features: pd.DataFrame) -> str:
    if len(pulse_features) < 3:
        return "exploratory"
    amplitude = pulse_features["peak_abs_v"].to_numpy(float)
    amplitude_cv = float(np.std(amplitude) / max(np.mean(amplitude), np.finfo(float).eps))
    residual = pulse_features.get(
        "template_residual_rms_fraction",
        pd.Series(np.ones(len(pulse_features))),
    ).to_numpy(float)
    median_residual = float(np.median(residual))
    if len(pulse_features) >= 8 and amplitude_cv <= 0.15 and median_residual <= 0.18:
        return "strongly_supported"
    if amplitude_cv <= 0.35 and median_residual <= 0.35:
        return "supported"
    return "exploratory"


def _method_agreement_support(
    template_time_s: Array,
    template_v: Array,
    pulse_features: pd.DataFrame,
    mode_clusters: pd.DataFrame,
    config: EFTConfig,
) -> tuple[str, dict[str, float]]:
    diagnostics: dict[str, float] = {}
    statuses: list[str] = []

    if pulse_features.empty or "rise_time_s" not in pulse_features:
        return "exploratory", diagnostics
    rises = pulse_features["rise_time_s"].to_numpy(float)
    rises = rises[np.isfinite(rises)]
    if rises.size and template_v.size:
        peak = int(np.argmax(np.abs(template_v)))
        polarity = 1.0 if template_v[peak] >= 0 else -1.0
        norm = polarity * template_v / max(abs(template_v[peak]), config.epsilon)
        t10 = _interpolated_crossing(template_time_s, norm, 0.10, 0, peak, True)
        t90 = _interpolated_crossing(template_time_s, norm, 0.90, 0, peak, True)
        template_rise = t90 - t10 if np.isfinite(t10) and np.isfinite(t90) else math.nan
        median_rise = float(np.median(rises))
        relative = (
            abs(template_rise - median_rise) / max(median_rise, config.epsilon)
            if np.isfinite(template_rise) else math.inf
        )
        diagnostics["template_vs_pulse_rise_relative_difference"] = relative
        statuses.append(
            "strongly_supported" if relative <= 0.10 else
            "supported" if relative <= 0.25 else
            "exploratory"
        )

    oscillatory = mode_clusters[
        mode_clusters.get("mode_type", pd.Series(dtype=str)) == "oscillatory"
    ] if not mode_clusters.empty else pd.DataFrame()
    if not oscillatory.empty and template_v.size:
        dt = float(np.median(np.diff(template_time_s)))
        peak = int(np.argmin(np.abs(template_time_s)))
        start = peak + max(1, int(round(config.ring_start_after_peak_s / dt)))
        stop = min(template_v.size, start + max(24, int(round(config.ring_window_s / dt))))
        tail = template_v[start:stop]
        tail = tail - np.mean(tail)
        if tail.size >= 24:
            # Differentiate before the independent FFT estimate.  The raw
            # post-pulse tail may contain a large nonoscillatory exponential
            # recovery whose low-frequency energy hides the faster ring.
            # The derivative suppresses that slow component without using the
            # matrix-pencil result to choose a frequency band.
            spectral_signal = np.gradient(tail, dt)
            spectral_signal -= np.mean(spectral_signal)
            window = np.hanning(tail.size)
            spectrum = np.abs(np.fft.rfft(spectral_signal * window))
            freqs = np.fft.rfftfreq(tail.size, dt)
            mask = (
                (freqs >= config.minimum_ring_frequency_hz)
                & (freqs <= config.maximum_ring_fraction_of_sample_rate / dt)
            )
            if np.any(mask):
                fft_frequency = float(freqs[np.flatnonzero(mask)[np.argmax(spectrum[mask])]])
                modal_frequency = float(
                    oscillatory.sort_values("occurrence_fraction", ascending=False)
                    ["median_frequency_hz"].iloc[0]
                )
                relative = abs(fft_frequency - modal_frequency) / max(modal_frequency, config.epsilon)
                diagnostics["fft_vs_matrix_pencil_frequency_relative_difference"] = relative
                statuses.append(
                    "strongly_supported" if relative <= 0.08 else
                    "supported" if relative <= 0.20 else
                    "exploratory"
                )

    if not statuses:
        return "exploratory", diagnostics
    return _minimum_support(*statuses), diagnostics


def _eft_like_detail_status(pulse_features: pd.DataFrame, config: EFTConfig) -> tuple[bool, dict[str, float]]:
    rises = pulse_features["rise_time_s"].to_numpy(float) if not pulse_features.empty else np.empty(0)
    widths = pulse_features["half_width_s"].to_numpy(float) if not pulse_features.empty else np.empty(0)
    rises = rises[np.isfinite(rises)]
    widths = widths[np.isfinite(widths)]
    median_rise = float(np.median(rises)) if rises.size else math.nan
    median_width = float(np.median(widths)) if widths.size else math.nan
    supported = bool(
        len(pulse_features) >= config.minimum_detail_pulses
        and np.isfinite(median_rise)
        and np.isfinite(median_width)
        and median_rise <= config.eft_like_max_rise_time_s
        and median_width <= config.eft_like_max_half_width_s
    )
    return supported, {
        "median_rise_time_s": median_rise,
        "median_half_width_s": median_width,
    }


# ---------------------------------------------------------------------------
# Public analysis entry point
# ---------------------------------------------------------------------------

def analyze_emi_eft_burst(
    detail_time_s: Array,
    detail_captures_v: Array,
    metadata: EFTAcquisitionMetadata,
    *,
    overview_time_s: Array | None = None,
    overview_waveform_v: Array | None = None,
    config: EFTConfig = EFTConfig(),
) -> EFTResult:
    detail_time_s, _ = _validate_uniform_time(detail_time_s)
    detail_captures_v = _validate_capture_matrix(
        detail_captures_v, detail_time_s.size
    )
    acquisition = assess_acquisition(
        detail_time_s, detail_captures_v, metadata, config
    )

    pulse_features, _ = detect_detail_pulses(
        detail_time_s, detail_captures_v, config
    )
    (
        template_time,
        template,
        aligned,
        residuals,
        pulse_features,
    ) = build_pulse_template(
        detail_time_s,
        detail_captures_v,
        pulse_features,
        config,
    )
    modes, clusters, mode_diagnostics = extract_modes_from_aligned_pulses(
        template_time, aligned, config
    )
    overview_pulses, train, bursts, overview_diagnostics = analyze_overview(
        overview_time_s, overview_waveform_v, config
    )

    detail_supported, detail_metrics = _eft_like_detail_status(
        pulse_features, config
    )
    train_supported = bool(
        not train.empty
        and bool(train["expected_repetition_match"].iloc[0])
        and int(train["overview_pulse_count"].iloc[0]) >= 3
    )

    repeatability = _repeatability_support(pulse_features)
    stability, stability_metrics = _bootstrap_stability(pulse_features, config)
    agreement, agreement_metrics = _method_agreement_support(
        template_time, template, pulse_features, clusters, config
    )
    overall_support = _minimum_support(
        acquisition.observability_status,
        repeatability,
        stability,
        agreement,
    )

    geometry_supported = bool(
        np.isfinite(detail_metrics["median_rise_time_s"])
        and np.isfinite(detail_metrics["median_half_width_s"])
        and detail_metrics["median_rise_time_s"] <= config.eft_like_max_rise_time_s
        and detail_metrics["median_half_width_s"] <= config.eft_like_max_half_width_s
    )

    if acquisition.observability_status == "rejected":
        status = "measurement_rejected"
    elif pulse_features.empty:
        status = "no_fast_transient_detected"
    elif geometry_supported and len(pulse_features) < config.minimum_detail_pulses:
        status = "fast_pulse_detected_insufficient_ensemble"
    elif not detail_supported:
        status = "sharp_transient_detected_not_eft_like"
    elif overview_time_s is None or overview_waveform_v is None:
        status = "eft_like_pulse_supported_burst_unresolved"
    elif train_supported:
        status = "eft_like_burst_supported"
    else:
        status = "eft_like_pulse_supported_train_not_confirmed"

    confidence_status = (
        "final_confidence_unavailable_snr_deferred"
    )

    evidence = {
        "acquisition_observability": acquisition.observability_status,
        "repeatability": repeatability,
        "resampling_stability": stability,
        "method_agreement": agreement,
        "provisional_combined_support": overall_support,
    }

    diagnostics: dict[str, Any] = {
        "detail_metrics": detail_metrics,
        "stability_metrics": stability_metrics,
        "agreement_metrics": agreement_metrics,
        "mode_diagnostics": mode_diagnostics,
        "overview_diagnostics": overview_diagnostics,
    }

    return EFTResult(
        status=status,
        snr_evaluated=False,
        confidence_status=confidence_status,
        acquisition=acquisition,
        pulse_features=pulse_features,
        pulse_template_time_s=template_time,
        pulse_template_v=template,
        aligned_pulse_windows_v=aligned,
        pulse_residuals_v=residuals,
        modes=modes,
        mode_clusters=clusters,
        train_summary=train,
        burst_summary=bursts,
        overview_pulses=overview_pulses,
        evidence=evidence,
        diagnostics=diagnostics,
        notes=(
            "SNR is intentionally not calculated in v0.1.0.",
            "All support labels are provisional and categorical.",
            "The worker reports EFT-like measured behavior, not IEC compliance.",
            "The explicit pulse waveform and residuals are preserved.",
            "Matrix-pencil modes describe post-pulse dynamics, not a unique physical component.",
            "Equivalent-time acquisition is not trusted for pulse-to-pulse variation.",
            "Synthetic validation is not field calibration.",
        ),
    )


# ---------------------------------------------------------------------------
# Synthetic validation
# ---------------------------------------------------------------------------

def _double_exponential_pulse(
    t: Array,
    start_s: float,
    amplitude_v: float,
    rise_tau_s: float,
    decay_tau_s: float,
) -> Array:
    x = t - start_s
    pulse = np.zeros_like(t)
    mask = x >= 0
    y = (1.0 - np.exp(-x[mask] / rise_tau_s)) * np.exp(-x[mask] / decay_tau_s)
    if y.size and np.max(y) > 0:
        y /= np.max(y)
    pulse[mask] = amplitude_v * y
    return pulse


def _synthetic_detail_set(
    rng: np.random.Generator,
    *,
    sample_rate_hz: float = 4e9,
    capture_count: int = 8,
    rise_tau_s: float = 1.8e-9,
    decay_tau_s: float = 70e-9,
    amplitude_v: float = 1.0,
    ring_frequency_hz: float | None = 120e6,
    ring_decay_s: float = 65e-9,
    ring_fraction: float = 0.18,
    amplitude_drift_fraction: float = 0.0,
    no_event: bool = False,
    broad_step: bool = False,
) -> tuple[Array, Array]:
    duration_s = 260e-9
    n = int(round(duration_s * sample_rate_hz))
    t = np.arange(n, dtype=float) / sample_rate_hz
    captures = []
    for index in range(capture_count):
        jitter = rng.normal(0.0, 0.45e-9)
        start = 42e-9 + jitter
        drift = 1.0 + amplitude_drift_fraction * (
            index / max(1, capture_count - 1) - 0.5
        )
        if no_event:
            signal = np.zeros_like(t)
        elif broad_step:
            # Finite, deliberately slow transient: detectable, but outside the
            # EFT-like rise-time gate.
            signal = _double_exponential_pulse(
                t, start, amplitude_v, 35e-9, 150e-9
            )
        else:
            signal = _double_exponential_pulse(
                t, start, amplitude_v * drift, rise_tau_s, decay_tau_s
            )
            if ring_frequency_hz is not None:
                ring_start = start + 15e-9
                x = t - ring_start
                mask = x >= 0
                ring = np.zeros_like(t)
                ring[mask] = (
                    ring_fraction * amplitude_v * drift
                    * np.exp(-x[mask] / ring_decay_s)
                    * np.sin(2.0 * np.pi * ring_frequency_hz * x[mask] + 0.35)
                )
                signal += ring
        noise = rng.normal(0.0, 0.0035 * max(amplitude_v, 1.0), n)
        offset = rng.normal(0.0, 0.002)
        captures.append(signal + noise + offset)
    return t, np.vstack(captures)


def _synthetic_overview(
    rng: np.random.Generator,
    *,
    repetition_hz: float = 100e3,
    bursts: int = 2,
    pulses_per_burst: int = 45,
    sample_rate_hz: float = 20e6,
    inter_burst_gap_s: float = 2.5e-3,
    amplitude_v: float = 1.0,
    missing_fraction: float = 0.0,
    amplitude_drift_fraction: float = 0.0,
) -> tuple[Array, Array]:
    interval = 1.0 / repetition_hz
    burst_duration = pulses_per_burst * interval
    duration = bursts * burst_duration + (bursts - 1) * inter_burst_gap_s + 0.5e-3
    n = int(math.ceil(duration * sample_rate_hz))
    t = np.arange(n, dtype=float) / sample_rate_hz
    waveform = rng.normal(0.0, 0.0025 * amplitude_v, n)
    width_samples = max(1, int(round(80e-9 * sample_rate_hz)))

    pulse_counter = 0
    current = 0.2e-3
    for burst_index in range(bursts):
        for local_index in range(pulses_per_burst):
            pulse_counter += 1
            if rng.random() < missing_fraction:
                continue
            pulse_time = current + local_index * interval + rng.normal(0.0, 0.015 * interval)
            sample = int(round(pulse_time * sample_rate_hz))
            if 0 <= sample < n:
                drift = 1.0 + amplitude_drift_fraction * (
                    local_index / max(1, pulses_per_burst - 1) - 0.5
                )
                waveform[sample:min(n, sample + width_samples)] += amplitude_v * drift
        current += burst_duration + inter_burst_gap_s

    return t, waveform


def _validation_case(
    case_family: str,
    rng: np.random.Generator,
    config: EFTConfig,
) -> tuple[EFTResult, dict[str, Any]]:
    metadata = EFTAcquisitionMetadata(
        scope_model="GW Instek GDS-3504",
        probe_model="synthetic_500MHz_probe",
        analog_bandwidth_hz=500e6,
        probe_bandwidth_hz=500e6,
        adc_bits=8,
        vertical_min_v=-2.0,
        vertical_max_v=2.0,
        input_impedance_ohm=1e6,
        coupling="DC",
        acquisition_mode="real_time",
    )

    expected_status = ""
    truth_ring_hz = math.nan
    truth_repetition_hz = math.nan

    if case_family == "nominal_100khz":
        detail_t, detail = _synthetic_detail_set(rng, ring_frequency_hz=120e6)
        overview_t, overview = _synthetic_overview(rng, repetition_hz=100e3)
        expected_status = "eft_like_burst_supported"
        truth_ring_hz = 120e6
        truth_repetition_hz = 100e3
    elif case_family == "nominal_5khz":
        detail_t, detail = _synthetic_detail_set(rng, ring_frequency_hz=85e6)
        overview_t, overview = _synthetic_overview(
            rng, repetition_hz=5e3, pulses_per_burst=18,
            sample_rate_hz=2e6, inter_burst_gap_s=8e-3
        )
        expected_status = "eft_like_burst_supported"
        truth_ring_hz = 85e6
        truth_repetition_hz = 5e3
    elif case_family == "nonoscillatory_burst":
        detail_t, detail = _synthetic_detail_set(rng, ring_frequency_hz=None)
        overview_t, overview = _synthetic_overview(rng, repetition_hz=100e3)
        expected_status = "eft_like_burst_supported"
        truth_repetition_hz = 100e3
    elif case_family == "amplitude_drift_burst":
        detail_t, detail = _synthetic_detail_set(
            rng, ring_frequency_hz=150e6, amplitude_drift_fraction=0.35
        )
        overview_t, overview = _synthetic_overview(
            rng, repetition_hz=100e3, amplitude_drift_fraction=0.45
        )
        expected_status = "eft_like_burst_supported"
        truth_ring_hz = 150e6
        truth_repetition_hz = 100e3
    elif case_family == "missing_pulses":
        detail_t, detail = _synthetic_detail_set(rng, ring_frequency_hz=105e6)
        overview_t, overview = _synthetic_overview(
            rng, repetition_hz=100e3, missing_fraction=0.12
        )
        expected_status = "eft_like_burst_supported"
        truth_ring_hz = 105e6
        truth_repetition_hz = 100e3
    elif case_family == "single_fast_pulse_no_overview":
        detail_t, detail = _synthetic_detail_set(
            rng, capture_count=1, ring_frequency_hz=130e6
        )
        overview_t = overview = None
        expected_status = "fast_pulse_detected_insufficient_ensemble"
        truth_ring_hz = 130e6
    elif case_family == "broad_step_negative":
        detail_t, detail = _synthetic_detail_set(
            rng, ring_frequency_hz=None, broad_step=True
        )
        overview_t, overview = _synthetic_overview(rng, repetition_hz=100e3)
        expected_status = "no_fast_transient_detected"
        truth_repetition_hz = 100e3
    elif case_family == "no_event_negative":
        detail_t, detail = _synthetic_detail_set(
            rng, ring_frequency_hz=None, no_event=True
        )
        overview_t = overview = None
        expected_status = "no_fast_transient_detected"
    else:
        raise ValueError(case_family)

    result = analyze_emi_eft_burst(
        detail_t,
        detail,
        metadata,
        overview_time_s=overview_t,
        overview_waveform_v=overview,
        config=config,
    )
    return result, {
        "expected_status": expected_status,
        "truth_ring_hz": truth_ring_hz,
        "truth_repetition_hz": truth_repetition_hz,
    }


def run_synthetic_validation(
    output_directory: str | Path,
    *,
    cases_per_family: int = 3,
    seed: int = 610044,
    config: EFTConfig = EFTConfig(),
) -> dict[str, Any]:
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    families = (
        "nominal_100khz",
        "nominal_5khz",
        "nonoscillatory_burst",
        "amplitude_drift_burst",
        "missing_pulses",
        "single_fast_pulse_no_overview",
        "broad_step_negative",
        "no_event_negative",
    )

    rows: list[dict[str, Any]] = []
    example: EFTResult | None = None

    for family in families:
        for case_index in range(cases_per_family):
            result, truth = _validation_case(family, rng, config)
            if example is None and family == "nominal_100khz":
                example = result

            ring_estimate = math.nan
            oscillatory = (
                result.mode_clusters[
                    result.mode_clusters["mode_type"] == "oscillatory"
                ]
                if not result.mode_clusters.empty else pd.DataFrame()
            )
            if not oscillatory.empty:
                ring_estimate = float(
                    oscillatory.sort_values(
                        "occurrence_fraction", ascending=False
                    )["median_frequency_hz"].iloc[0]
                )

            repetition_estimate = (
                float(result.train_summary["repetition_frequency_hz"].iloc[0])
                if not result.train_summary.empty else math.nan
            )
            truth_ring = float(truth["truth_ring_hz"])
            truth_rep = float(truth["truth_repetition_hz"])
            rows.append({
                "case_family": family,
                "case_index": case_index,
                "expected_status": truth["expected_status"],
                "observed_status": result.status,
                "status_match": result.status == truth["expected_status"],
                "pulse_count": len(result.pulse_features),
                "acquisition_observability": result.evidence["acquisition_observability"],
                "repeatability": result.evidence["repeatability"],
                "resampling_stability": result.evidence["resampling_stability"],
                "method_agreement": result.evidence["method_agreement"],
                "snr_evaluated": result.snr_evaluated,
                "truth_ring_frequency_hz": truth_ring,
                "estimated_ring_frequency_hz": ring_estimate,
                "ring_relative_error": (
                    abs(ring_estimate - truth_ring) / truth_ring
                    if np.isfinite(ring_estimate) and np.isfinite(truth_ring)
                    else math.nan
                ),
                "truth_repetition_frequency_hz": truth_rep,
                "estimated_repetition_frequency_hz": repetition_estimate,
                "repetition_relative_error": (
                    abs(repetition_estimate - truth_rep) / truth_rep
                    if np.isfinite(repetition_estimate) and np.isfinite(truth_rep)
                    else math.nan
                ),
                "inferred_missing_pulses": (
                    int(result.train_summary["total_inferred_missing_pulse_count"].iloc[0])
                    if not result.train_summary.empty else 0
                ),
            })

    runs = pd.DataFrame(rows)
    summary = (
        runs.groupby("case_family", as_index=False)
        .agg(
            cases=("status_match", "size"),
            status_matches=("status_match", "sum"),
            status_match_rate=("status_match", "mean"),
            median_ring_relative_error=("ring_relative_error", "median"),
            median_repetition_relative_error=("repetition_relative_error", "median"),
            snr_ever_evaluated=("snr_evaluated", "max"),
        )
    )
    overall = {
        "seed_version": "0.1.0",
        "case_count": int(len(runs)),
        "family_count": int(len(families)),
        "status_matches": int(runs["status_match"].sum()),
        "status_match_rate": float(runs["status_match"].mean()),
        "median_ring_relative_error": float(runs["ring_relative_error"].median(skipna=True)),
        "median_repetition_relative_error": float(runs["repetition_relative_error"].median(skipna=True)),
        "snr_evaluated": bool(runs["snr_evaluated"].any()),
        "scope_warning": (
            "Synthetic research validation only. Not field calibrated, "
            "not standards certified, and not a confidence calibration."
        ),
    }

    runs.to_csv(output_directory / "eft_burst_v010_validation_runs.csv", index=False)
    summary.to_csv(output_directory / "eft_burst_v010_case_summary.csv", index=False)
    pd.DataFrame([overall]).to_csv(
        output_directory / "eft_burst_v010_overall_summary.csv", index=False
    )
    (output_directory / "eft_burst_v010_overall_summary.json").write_text(
        json.dumps(overall, indent=2), encoding="utf-8"
    )

    if example is not None:
        example.pulse_features.to_csv(
            output_directory / "eft_burst_v010_example_pulses.csv", index=False
        )
        example.mode_clusters.to_csv(
            output_directory / "eft_burst_v010_example_mode_clusters.csv", index=False
        )
        example.train_summary.to_csv(
            output_directory / "eft_burst_v010_example_train_summary.csv", index=False
        )
        example.burst_summary.to_csv(
            output_directory / "eft_burst_v010_example_bursts.csv", index=False
        )
        (output_directory / "eft_burst_v010_example_summary.json").write_text(
            json.dumps(example.summary_dict(), indent=2, default=float),
            encoding="utf-8",
        )

        plt.figure(figsize=(10, 5.5))
        max_traces = min(12, example.aligned_pulse_windows_v.shape[0])
        for trace in example.aligned_pulse_windows_v[:max_traces]:
            plt.plot(example.pulse_template_time_s * 1e9, trace, alpha=0.28)
        plt.plot(
            example.pulse_template_time_s * 1e9,
            example.pulse_template_v,
            linewidth=2.2,
            label="Median pulse template",
        )
        plt.xlabel("Time relative to peak (ns)")
        plt.ylabel("Voltage (V)")
        plt.title("EFT detail captures, aligned pulse windows, and explicit template")
        plt.legend()
        plt.tight_layout()
        plt.savefig(output_directory / "eft_burst_v010_aligned_pulses.png", dpi=180)
        plt.close()

        if not example.mode_clusters.empty:
            oscillatory = example.mode_clusters[
                example.mode_clusters["mode_type"] == "oscillatory"
            ]
            if not oscillatory.empty:
                plt.figure(figsize=(8.5, 5.2))
                plt.scatter(
                    oscillatory["median_frequency_hz"] / 1e6,
                    oscillatory["occurrence_fraction"],
                    s=80,
                )
                plt.xlabel("Median ring frequency (MHz)")
                plt.ylabel("Pulse occurrence fraction")
                plt.title("Repeated post-pulse oscillatory mode clusters")
                plt.ylim(-0.03, 1.05)
                plt.tight_layout()
                plt.savefig(
                    output_directory / "eft_burst_v010_mode_occurrence.png",
                    dpi=180,
                )
                plt.close()

        if not example.overview_pulses.empty:
            plt.figure(figsize=(10, 5.2))
            plt.stem(
                example.overview_pulses["time_s"] * 1e3,
                example.overview_pulses["peak_abs_v"],
                basefmt=" ",
            )
            plt.xlabel("Time (ms)")
            plt.ylabel("Detected pulse amplitude (V)")
            plt.title("Overview-scale pulse train and burst grouping")
            plt.tight_layout()
            plt.savefig(
                output_directory / "eft_burst_v010_overview_train.png",
                dpi=180,
            )
            plt.close()

    return overall


def package_bundle(directory: str | Path, zip_path: str | Path) -> Path:
    directory = Path(directory)
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=path.relative_to(directory))
    return zip_path


if __name__ == "__main__":
    destination = Path(__file__).resolve().parent
    print(json.dumps(run_synthetic_validation(destination), indent=2))
