"""Gamma / ElectroStat current-inrush seed v0.1.0.

Population geometry
-------------------
A = inrush-present captures
B = validated completed transitions without inrush
F = failed or incomplete transitions
U = uncertain or unusable captures

Only A builds the inrush model. Only B builds the no-inrush reference.
Each A capture is measured twice: during inrush and post-inrush recovery.
SNR is intentionally deferred in v0.1.0.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Iterable
import json
import math
import zipfile

import numpy as np
from numpy.typing import NDArray
import pandas as pd
from scipy.ndimage import uniform_filter1d
from scipy.optimize import curve_fit
from scipy.signal import find_peaks, periodogram
import matplotlib.pyplot as plt

Array = NDArray[np.float64]


@dataclass(frozen=True)
class CurrentProbeMetadata:
    probe_model: str = "unknown"
    amperes_per_volt: float = 1.0
    bandwidth_hz: float | None = None
    current_limit_a: float | None = None
    ac_dc_capable: bool = True
    phase_or_conductor_id: str = "unknown"
    scope_model: str = "unknown"
    scope_bandwidth_hz: float | None = None
    acquisition_mode: str = "real_time"
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CaptureContext:
    capture_id: str
    transition_expected: bool = True
    transition_validated: bool = True
    transition_completed: bool | None = None
    event_marker_time_s: float | None = None
    operating_state: str = "unknown"
    load_state: str = "unknown"
    phase_or_conductor_id: str = "unknown"
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class InrushConfig:
    line_frequency_hz: float | None = 60.0
    envelope_window_s: float | None = None
    minimum_envelope_samples: int = 5
    pre_event_fraction: float = 0.15
    post_reference_fraction: float = 0.20
    minimum_post_reference_s: float = 0.05
    onset_scale_multiplier: float = 6.0
    inrush_peak_to_post_ratio_min: float = 1.35
    inrush_peak_minus_post_scale_min: float = 6.0
    recovery_band_multiplier: float = 3.5
    required_recovery_hold_s: float = 0.05
    decay_fit_min_points: int = 12
    ring_min_frequency_hz: float = 1.0
    ring_max_fraction_of_envelope_rate: float = 0.35
    ring_prominence_fraction: float = 0.08
    ring_min_cycles: float = 1.5
    ring_min_residual_fraction: float = 0.025
    retrigger_peak_prominence_fraction: float = 0.20
    altered_post_median_relative_threshold: float = 0.15
    sustained_elevation_ratio: float = 1.75
    reference_relative_spread_floor: float = 0.02
    reference_absolute_spread_floor_a: float = 0.05
    minimum_no_inrush_reference_captures: int = 2
    minimum_inrush_model_captures: int = 2
    bootstrap_iterations: int = 80
    bootstrap_seed: int = 1159745
    epsilon: float = 1e-12

    def __post_init__(self) -> None:
        if self.line_frequency_hz is not None and self.line_frequency_hz <= 0:
            raise ValueError("line_frequency_hz must be positive or None")
        if self.envelope_window_s is not None and self.envelope_window_s <= 0:
            raise ValueError("envelope_window_s must be positive or None")
        if not 0 < self.pre_event_fraction < 0.5:
            raise ValueError("pre_event_fraction must lie in (0, 0.5)")
        if not 0 < self.post_reference_fraction < 0.5:
            raise ValueError("post_reference_fraction must lie in (0, 0.5)")


@dataclass(frozen=True)
class InrushResult:
    status: str
    snr_evaluated: bool
    confidence_status: str
    capture_classification: pd.DataFrame
    inrush_features: pd.DataFrame
    envelopes: Array
    envelope_time_s: Array
    no_inrush_reference_envelope_a: Array
    no_inrush_reference_spread_a: Array
    inrush_template_envelope_a: Array
    inrush_template_spread_a: Array
    population_summary: pd.DataFrame
    evidence: dict[str, str]
    diagnostics: dict[str, Any]
    notes: tuple[str, ...]

    def summary_dict(self) -> dict[str, Any]:
        counts = (
            self.capture_classification["capture_class"].value_counts().to_dict()
            if not self.capture_classification.empty else {}
        )
        return {
            "status": self.status,
            "snr_evaluated": self.snr_evaluated,
            "confidence_status": self.confidence_status,
            "class_counts": counts,
            "evidence": self.evidence,
            "population_summary": (
                self.population_summary.iloc[0].to_dict()
                if not self.population_summary.empty else {}
            ),
            "notes": list(self.notes),
        }


def _validate(time_s: Array, captures_a: Array) -> tuple[Array, Array, float]:
    t = np.asarray(time_s, dtype=float)
    x = np.asarray(captures_a, dtype=float)
    if t.ndim != 1 or t.size < 64:
        raise ValueError("time_s must be 1D with at least 64 samples")
    if x.ndim == 1:
        x = x[None, :]
    if x.ndim != 2 or x.shape[1] != t.size:
        raise ValueError("captures_a must have shape (capture_count, sample_count)")
    if not np.isfinite(t).all() or not np.isfinite(x).all():
        raise ValueError("non-finite values are unsupported")
    steps = np.diff(t)
    dt = float(np.median(steps))
    if dt <= 0 or np.any(steps <= 0):
        raise ValueError("time_s must be strictly increasing")
    if np.max(np.abs(steps - dt)) > 0.01 * dt:
        raise ValueError("uniform sampling is required in v0.1.0")
    return t, x, dt


def _robust(values: Array, epsilon: float) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    center = float(np.median(values))
    scale = 1.4826 * float(np.median(np.abs(values - center)))
    return center, max(scale, epsilon)


def _envelope_window(config: InrushConfig, dt: float) -> int:
    if config.envelope_window_s is not None:
        width = config.envelope_window_s
    elif config.line_frequency_hz is not None:
        width = 1.0 / config.line_frequency_hz
    else:
        raise ValueError(
            "Provide line_frequency_hz or envelope_window_s; the seed will not invent an envelope scale."
        )
    return max(config.minimum_envelope_samples, int(round(width / dt)))


def sliding_rms_envelope(captures_a: Array, window_samples: int) -> Array:
    return np.sqrt(np.maximum(
        uniform_filter1d(np.square(captures_a), size=window_samples, axis=1, mode="nearest"),
        0.0,
    ))


def _marker_index(context: CaptureContext, time_s: Array, config: InrushConfig) -> int:
    if context.event_marker_time_s is not None:
        return int(np.argmin(np.abs(time_s - context.event_marker_time_s)))
    return max(1, int(round(config.pre_event_fraction * time_s.size)))


def _classify_capture(
    time_s: Array,
    envelope_a: Array,
    context: CaptureContext,
    config: InrushConfig,
) -> dict[str, Any]:
    n = time_s.size
    marker = _marker_index(context, time_s, config)
    post_count = max(
        int(round(config.post_reference_fraction * n)),
        int(round(config.minimum_post_reference_s / (time_s[1] - time_s[0]))),
    )
    post_start = max(marker + 1, n - min(post_count, n // 2))
    pre_center, pre_scale = _robust(envelope_a[:max(4, marker)], config.epsilon)
    post_center, post_scale = _robust(envelope_a[post_start:], config.epsilon)
    search = envelope_a[marker:]
    threshold = max(
        pre_center + config.onset_scale_multiplier * pre_scale,
        post_center + config.onset_scale_multiplier * post_scale,
    )
    candidates = np.flatnonzero(search > threshold)
    onset = marker + int(candidates[0]) if candidates.size else None
    peak = marker + int(np.argmax(search))
    peak_value = float(envelope_a[peak])
    ratio = peak_value / max(post_center, config.epsilon)
    excess_scales = (peak_value - post_center) / max(post_scale, config.epsilon)

    if not context.transition_expected:
        cls, reason = "uncertain", "transition_not_expected"
    elif not context.transition_validated:
        cls, reason = "uncertain", "transition_not_validated"
    elif context.transition_completed is False:
        cls, reason = "failed_transition", "transition_marked_incomplete"
    elif onset is not None and ratio >= config.inrush_peak_to_post_ratio_min and excess_scales >= config.inrush_peak_minus_post_scale_min:
        cls, reason = "inrush_present", "envelope_peak_exceeds_post_reference"
    elif context.transition_completed is True:
        cls, reason = "no_inrush", "validated_completed_transition_without_inrush"
    else:
        cls, reason = "uncertain", "transition_completion_unknown"

    return {
        "capture_id": context.capture_id,
        "capture_class": cls,
        "classification_reason": reason,
        "marker_index": marker,
        "marker_time_s": float(time_s[marker]),
        "onset_index": onset if onset is not None else -1,
        "onset_time_s": float(time_s[onset]) if onset is not None else math.nan,
        "peak_index": peak,
        "peak_time_s": float(time_s[peak]),
        "peak_envelope_a": peak_value,
        "pre_event_envelope_median_a": pre_center,
        "pre_event_envelope_scale_a": pre_scale,
        "post_envelope_median_a": post_center,
        "post_envelope_scale_a": post_scale,
        "peak_to_post_ratio": ratio,
        "peak_excess_in_post_scales": excess_scales,
        "post_reference_start_index": post_start,
        "transition_expected": context.transition_expected,
        "transition_validated": context.transition_validated,
        "transition_completed": context.transition_completed,
        "operating_state": context.operating_state,
        "load_state": context.load_state,
        "phase_or_conductor_id": context.phase_or_conductor_id,
    }


def _pointwise_reference(envelopes: Array, config: InrushConfig) -> tuple[Array, Array]:
    center = np.median(envelopes, axis=0)
    spread = 1.4826 * np.median(np.abs(envelopes - center[None, :]), axis=0)
    floor = np.maximum(
        config.reference_absolute_spread_floor_a,
        config.reference_relative_spread_floor * np.maximum(np.abs(center), config.epsilon),
    )
    return center, np.maximum(spread, floor)


def _exp_model(t: Array, amplitude: float, tau: float, offset: float) -> Array:
    return offset + amplitude * np.exp(-t / max(tau, np.finfo(float).eps))


def _fit_decay(
    time_s: Array,
    envelope_a: Array,
    peak_index: int,
    stop_index: int,
    baseline_a: float,
    config: InrushConfig,
) -> tuple[dict[str, Any], Array]:
    stop_index = min(stop_index, envelope_a.size)
    if stop_index - peak_index < config.decay_fit_min_points:
        return {
            "decay_fit_success": False,
            "decay_time_constant_s": math.nan,
            "decay_fit_nrmse": math.nan,
        }, np.empty(0)
    t = time_s[peak_index:stop_index] - time_s[peak_index]
    y = envelope_a[peak_index:stop_index]
    try:
        p0 = [max(float(y[0] - baseline_a), config.epsilon), max(float(t[-1] / 3.0), config.epsilon), baseline_a]
        bounds = ([0.0, time_s[1] - time_s[0], -np.inf], [np.inf, max(100.0 * t[-1], config.epsilon), np.inf])
        params, _ = curve_fit(_exp_model, t, y, p0=p0, bounds=bounds, maxfev=8000)
        predicted = _exp_model(t, *params)
        denom = max(float(np.linalg.norm(y - np.mean(y))), config.epsilon)
        nrmse = float(np.linalg.norm(y - predicted) / denom)
        return {
            "decay_fit_success": True,
            "decay_time_constant_s": float(params[1]),
            "decay_fit_nrmse": nrmse,
            "decay_amplitude_a": float(params[0]),
            "decay_offset_a": float(params[2]),
        }, predicted
    except Exception:
        return {
            "decay_fit_success": False,
            "decay_time_constant_s": math.nan,
            "decay_fit_nrmse": math.nan,
        }, np.empty(0)


def _ring_features(residual: Array, dt: float, event_scale: float, config: InrushConfig) -> dict[str, Any]:
    residual = np.asarray(residual, dtype=float)
    if residual.size < 16 or np.ptp(residual) <= config.epsilon:
        return {"ring_detected": False, "ring_frequency_hz": math.nan, "ring_peak_fraction": 0.0}
    centered = residual - np.mean(residual)
    residual_fraction = float(np.sqrt(np.mean(centered * centered)) / max(event_scale, config.epsilon))
    zero_crossings = int(np.sum(centered[:-1] * centered[1:] < 0))
    f, p = periodogram(centered, fs=1.0 / dt, window="hann", detrend="linear", scaling="spectrum")
    valid = (f >= config.ring_min_frequency_hz) & (f <= config.ring_max_fraction_of_envelope_rate / dt)
    if not np.any(valid):
        return {"ring_detected": False, "ring_frequency_hz": math.nan, "ring_peak_fraction": 0.0}
    indices = np.flatnonzero(valid)
    best = indices[int(np.argmax(p[valid]))]
    fraction = float(p[best] / max(np.sum(p[valid]), config.epsilon))
    cycles = float(f[best] * residual.size * dt)
    detected = (
        fraction >= config.ring_prominence_fraction
        and cycles >= config.ring_min_cycles
        and residual_fraction >= config.ring_min_residual_fraction
        and zero_crossings >= 3
    )
    return {
        "ring_detected": bool(detected),
        "ring_frequency_hz": float(f[best]) if detected else math.nan,
        "ring_peak_fraction": fraction,
        "ring_cycle_count": cycles,
        "ring_residual_fraction": residual_fraction,
        "ring_zero_crossings": zero_crossings,
    }


def _recovery_index(
    envelope: Array,
    start: int,
    center: Array | float,
    spread: Array | float,
    hold: int,
    multiplier: float,
    epsilon: float,
) -> int | None:
    c = np.full(envelope.size, float(center)) if np.isscalar(center) else np.asarray(center, dtype=float)
    s = np.full(envelope.size, max(float(spread), epsilon)) if np.isscalar(spread) else np.maximum(np.asarray(spread, dtype=float), epsilon)
    inside = np.abs(envelope - c) <= multiplier * s
    for idx in range(max(0, start), envelope.size - hold + 1):
        if np.all(inside[idx:idx + hold]):
            return idx
    return None


def _measure_inrush(
    time_s: Array,
    raw_a: Array,
    envelope_a: Array,
    row: pd.Series,
    reference: Array | None,
    reference_spread: Array | None,
    config: InrushConfig,
) -> dict[str, Any]:
    dt = float(time_s[1] - time_s[0])
    onset = int(row["onset_index"])
    peak = int(row["peak_index"])
    post_start = int(row["post_reference_start_index"])
    local_post = float(row["post_envelope_median_a"])
    local_spread = float(row["post_envelope_scale_a"])

    if reference is not None:
        recovery_center, recovery_spread = reference, reference_spread
        source = "validated_no_inrush_population"
    else:
        recovery_center, recovery_spread = local_post, local_spread
        source = "same_capture_post_region"

    hold = max(2, int(round(config.required_recovery_hold_s / dt)))
    recovery = _recovery_index(
        envelope_a, peak + 1, recovery_center, recovery_spread,
        hold, config.recovery_band_multiplier, config.epsilon,
    )
    event_stop = recovery if recovery is not None else post_start
    event_stop = max(event_stop, peak + config.decay_fit_min_points)
    event_stop = min(event_stop, envelope_a.size - 1)

    decay, predicted = _fit_decay(time_s, envelope_a, peak, event_stop, local_post, config)
    if predicted.size:
        residual = envelope_a[peak:peak + predicted.size] - predicted
    else:
        residual = envelope_a[peak:event_stop] - uniform_filter1d(
            envelope_a[peak:event_stop], size=max(3, (event_stop - peak) // 8), mode="nearest"
        )
    ring = _ring_features(residual, dt, max(float(envelope_a[peak] - local_post), config.epsilon), config)

    post_peak = envelope_a[peak:event_stop]
    prominence = config.retrigger_peak_prominence_fraction * max(float(envelope_a[peak] - local_post), config.epsilon)
    secondary, _ = find_peaks(post_peak, prominence=prominence)
    secondary = secondary[secondary > 1]
    retrigger_count = int(secondary.size)

    i2t_total = float(np.trapezoid(np.square(raw_a[onset:event_stop]), time_s[onset:event_stop]))
    excess = np.maximum(np.square(envelope_a[onset:event_stop]) - local_post ** 2, 0.0)
    excess_i2t = float(np.trapezoid(excess, time_s[onset:event_stop]))

    post_median = float(np.median(envelope_a[post_start:]))
    if reference is not None:
        ref_post = float(np.median(reference[post_start:]))
        post_rel = abs(post_median - ref_post) / max(abs(ref_post), config.epsilon)
    else:
        ref_post, post_rel = math.nan, math.nan

    recovered = recovery is not None
    post_baseline = ref_post if np.isfinite(ref_post) else local_post
    if not recovered and post_median >= config.sustained_elevation_ratio * max(post_baseline, config.epsilon):
        morphology = "sustained_elevated_current"
    elif retrigger_count >= 1:
        morphology = "repeated_or_retriggered"
    elif ring["ring_detected"]:
        morphology = "oscillatory_recovery"
    elif np.isfinite(post_rel) and post_rel >= config.altered_post_median_relative_threshold:
        morphology = "altered_post_event_state"
    elif recovered:
        morphology = "monotonic_or_normal_recovery"
    else:
        morphology = "inrush_without_confirmed_recovery"

    return {
        "capture_id": row["capture_id"],
        "onset_time_s": float(time_s[onset]),
        "peak_time_s": float(time_s[peak]),
        "peak_envelope_a": float(envelope_a[peak]),
        "local_post_envelope_a": local_post,
        "peak_to_post_ratio": float(envelope_a[peak] / max(local_post, config.epsilon)),
        "inrush_duration_s": float(time_s[event_stop] - time_s[onset]),
        "recovery_confirmed": recovered,
        "recovery_time_s": float(time_s[recovery] - time_s[onset]) if recovery is not None else math.nan,
        "recovery_reference_source": source,
        "i2t_total_a2_s": i2t_total,
        "excess_i2t_above_post_a2_s": excess_i2t,
        **decay,
        **ring,
        "retrigger_count": retrigger_count,
        "post_event_envelope_median_a": post_median,
        "no_inrush_reference_post_median_a": ref_post,
        "post_event_relative_difference_from_reference": post_rel,
        "morphology_class": morphology,
    }


def _repeatability(features: pd.DataFrame, config: InrushConfig) -> str:
    if len(features) < config.minimum_inrush_model_captures:
        return "exploratory"
    peak = features["peak_to_post_ratio"].to_numpy(float)
    duration = features["inrush_duration_s"].to_numpy(float)
    peak_cv = float(np.std(peak) / max(np.mean(peak), config.epsilon))
    duration_cv = float(np.std(duration) / max(np.mean(duration), config.epsilon))
    if len(features) >= 6 and peak_cv <= 0.15 and duration_cv <= 0.20:
        return "strongly_supported"
    if peak_cv <= 0.35 and duration_cv <= 0.45:
        return "supported"
    return "exploratory"


def _bootstrap(features: pd.DataFrame, config: InrushConfig) -> tuple[str, dict[str, float]]:
    if len(features) < 3:
        return "exploratory", {}
    rng = np.random.default_rng(config.bootstrap_seed)
    peak = features["peak_to_post_ratio"].to_numpy(float)
    duration = features["inrush_duration_s"].to_numpy(float)
    pmed, dmed = [], []
    for _ in range(config.bootstrap_iterations):
        idx = rng.integers(0, len(features), len(features))
        pmed.append(float(np.median(peak[idx])))
        dmed.append(float(np.median(duration[idx])))
    p_rel = float(np.std(pmed) / max(abs(np.median(pmed)), config.epsilon))
    d_rel = float(np.std(dmed) / max(abs(np.median(dmed)), config.epsilon))
    worst = max(p_rel, d_rel)
    status = "strongly_supported" if worst <= 0.08 else "supported" if worst <= 0.20 else "exploratory"
    return status, {
        "bootstrap_peak_ratio_relative_spread": p_rel,
        "bootstrap_duration_relative_spread": d_rel,
    }


def analyze_current_inrush(
    time_s: Array,
    captures_a: Array,
    contexts: Iterable[CaptureContext],
    probe_metadata: CurrentProbeMetadata,
    config: InrushConfig = InrushConfig(),
) -> InrushResult:
    time_s, captures_a, dt = _validate(time_s, captures_a)
    contexts = list(contexts)
    if len(contexts) != captures_a.shape[0]:
        raise ValueError("one CaptureContext is required per capture")

    window = _envelope_window(config, dt)
    envelopes = sliding_rms_envelope(captures_a, window)
    classification = pd.DataFrame([
        _classify_capture(time_s, envelopes[i], contexts[i], config)
        for i in range(len(contexts))
    ])

    a_idx = classification.index[classification["capture_class"] == "inrush_present"].to_numpy(int)
    b_idx = classification.index[classification["capture_class"] == "no_inrush"].to_numpy(int)

    if len(b_idx) >= config.minimum_no_inrush_reference_captures:
        b_ref, b_spread = _pointwise_reference(envelopes[b_idx], config)
    else:
        b_ref, b_spread = np.empty(0), np.empty(0)
    if len(a_idx):
        a_ref, a_spread = _pointwise_reference(envelopes[a_idx], config)
    else:
        a_ref, a_spread = np.empty(0), np.empty(0)

    features = pd.DataFrame([
        _measure_inrush(
            time_s, captures_a[i], envelopes[i], classification.loc[i],
            b_ref if b_ref.size else None,
            b_spread if b_spread.size else None,
            config,
        )
        for i in a_idx
    ])

    counts = classification["capture_class"].value_counts()
    a = int(counts.get("inrush_present", 0))
    b = int(counts.get("no_inrush", 0))
    f = int(counts.get("failed_transition", 0))
    u = int(counts.get("uncertain", 0))
    denominator = a + b
    population = pd.DataFrame([{
        "total_captures": len(classification),
        "inrush_present_count_A": a,
        "no_inrush_count_B": b,
        "failed_transition_count_F": f,
        "uncertain_count_U": u,
        "inrush_observation_rate_A_over_A_plus_B": a / denominator if denominator else math.nan,
        "no_inrush_reference_available": bool(b_ref.size),
        "inrush_model_available": a >= config.minimum_inrush_model_captures,
        "median_peak_to_post_ratio": float(np.median(features["peak_to_post_ratio"])) if not features.empty else math.nan,
        "median_inrush_duration_s": float(np.median(features["inrush_duration_s"])) if not features.empty else math.nan,
        "recovery_confirmed_fraction": float(np.mean(features["recovery_confirmed"])) if not features.empty else math.nan,
    }])

    repeat = _repeatability(features, config)
    stability, boot = _bootstrap(features, config)
    baseline = "strongly_supported" if len(b_idx) >= 5 else "supported" if b_ref.size else "exploratory"
    order = {"exploratory": 0, "supported": 1, "strongly_supported": 2}
    combined = min([repeat, stability, baseline], key=order.get)

    if a == 0:
        status = "no_current_inrush_population_available"
    elif a < config.minimum_inrush_model_captures:
        status = "current_inrush_detected_insufficient_ensemble"
    elif not b_ref.size:
        status = "current_inrush_modeled_without_no_inrush_reference"
    else:
        status = "current_inrush_and_recovery_modeled"

    return InrushResult(
        status=status,
        snr_evaluated=False,
        confidence_status="final_confidence_unavailable_snr_deferred",
        capture_classification=classification,
        inrush_features=features,
        envelopes=envelopes,
        envelope_time_s=time_s,
        no_inrush_reference_envelope_a=b_ref,
        no_inrush_reference_spread_a=b_spread,
        inrush_template_envelope_a=a_ref,
        inrush_template_spread_a=a_spread,
        population_summary=population,
        evidence={
            "inrush_population_repeatability": repeat,
            "resampling_stability": stability,
            "no_inrush_reference_support": baseline,
            "probe_bandwidth_metadata": "available" if probe_metadata.bandwidth_hz is not None else "missing",
            "provisional_combined_support": combined,
        },
        diagnostics={
            "envelope_window_samples": window,
            "envelope_window_s": window * dt,
            "inrush_capture_indices": a_idx.tolist(),
            "no_inrush_reference_capture_indices": b_idx.tolist(),
            "bootstrap": boot,
            "probe_metadata": asdict(probe_metadata),
        },
        notes=(
            "SNR is intentionally not calculated in v0.1.0.",
            "No-inrush means this seed signature was absent, not that the entire capture was healthy.",
            "Only validated same-transition no-inrush captures may build the B reference.",
            "Each inrush capture is measured independently before population modeling.",
            "The during-inrush and post-inrush envelopes are both preserved.",
            "Morphology labels are dynamic descriptions, not unique component diagnoses.",
        ),
    )


# ---------------------------------------------------------------------------
# Synthetic validation
# ---------------------------------------------------------------------------

def _carrier(t: Array, envelope: Array, frequency_hz: float, phase: float) -> Array:
    return np.sqrt(2.0) * envelope * np.sin(2.0 * np.pi * frequency_hz * t + phase)


def _synthetic_case(rng: np.random.Generator, family: str) -> tuple[Array, Array, CaptureContext, str]:
    fs, duration, f0, marker = 5000.0, 2.0, 60.0, 0.35
    t = np.arange(int(fs * duration)) / fs
    run = 10.0
    env = np.full_like(t, 0.5)
    after = t >= marker
    expected = "inrush_present"
    completed: bool | None = True
    x = np.maximum(0.0, t - marker)

    if family == "monotonic":
        env[after] = run + 55.0 * np.exp(-x[after] / 0.22)
    elif family == "oscillatory":
        env[after] = run + 50.0 * np.exp(-x[after] / 0.25) + 8.0 * np.exp(-x[after] / 0.45) * np.sin(2*np.pi*4.0*x[after])
    elif family == "retriggered":
        env[after] = run + 42.0 * np.exp(-x[after] / 0.20)
        env += 18.0 * np.exp(-((t - (marker + 0.32)) / 0.035)**2)
    elif family == "sustained":
        env[after] = 22.0 + 35.0 * np.exp(-x[after] / 0.45)
    elif family == "altered_post":
        env[after] = 14.0 + 45.0 * np.exp(-x[after] / 0.20)
    elif family == "no_inrush":
        env[after] = run
        expected = "no_inrush"
    elif family == "failed":
        env[after] = 0.7
        expected, completed = "failed_transition", False
    elif family == "uncertain":
        env[after] = run
        expected, completed = "uncertain", None
    else:
        raise ValueError(family)

    raw = _carrier(t, env, f0, rng.uniform(-np.pi, np.pi)) + rng.normal(0.0, 0.20, t.size)
    context = CaptureContext(
        capture_id=f"{family}_{rng.integers(1_000_000)}",
        transition_expected=True,
        transition_validated=(family != "uncertain"),
        transition_completed=completed,
        event_marker_time_s=marker,
        operating_state="synthetic_start",
        load_state="synthetic_load",
        phase_or_conductor_id="L1",
    )
    return t, raw, context, expected


def run_synthetic_validation(output_directory: str | Path, seed: int = 1159745, cases_per_family: int = 3) -> dict[str, Any]:
    out = Path(output_directory)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    families = ("monotonic", "oscillatory", "retriggered", "sustained", "altered_post", "no_inrush", "failed", "uncertain")
    raw, contexts, expected, family_names = [], [], [], []
    time_s = None
    for family in families:
        for _ in range(cases_per_family):
            time_s, x, context, cls = _synthetic_case(rng, family)
            raw.append(x); contexts.append(context); expected.append(cls); family_names.append(family)

    probe = CurrentProbeMetadata(
        probe_model="synthetic_ACDC_probe", amperes_per_volt=1.0,
        bandwidth_hz=100e3, current_limit_a=500.0,
        phase_or_conductor_id="L1", scope_model="GW Instek GDS-3504",
        scope_bandwidth_hz=500e6,
    )
    result = analyze_current_inrush(time_s, np.vstack(raw), contexts, probe, InrushConfig(line_frequency_hz=60.0))
    validation = result.capture_classification[["capture_id", "capture_class"]].copy()
    validation["expected_class"] = expected
    validation["synthetic_family"] = family_names
    validation["class_match"] = validation["capture_class"] == validation["expected_class"]
    if not result.inrush_features.empty:
        validation = validation.merge(result.inrush_features[["capture_id", "morphology_class", "ring_detected", "retrigger_count", "recovery_confirmed", "decay_time_constant_s"]], on="capture_id", how="left")

    overall = {
        "seed_version": "0.1.0",
        "case_count": int(len(validation)),
        "classification_matches": int(validation["class_match"].sum()),
        "classification_match_rate": float(validation["class_match"].mean()),
        "snr_evaluated": result.snr_evaluated,
        "status": result.status,
        "class_counts": result.capture_classification["capture_class"].value_counts().to_dict(),
        "scope_warning": "Synthetic validation only. Not bench calibration, field validation, or standards certification.",
    }
    validation.to_csv(out / "current_inrush_v010_validation_cases.csv", index=False)
    result.capture_classification.to_csv(out / "current_inrush_v010_capture_classification.csv", index=False)
    result.inrush_features.to_csv(out / "current_inrush_v010_inrush_features.csv", index=False)
    result.population_summary.to_csv(out / "current_inrush_v010_population_summary.csv", index=False)
    (out / "current_inrush_v010_summary.json").write_text(json.dumps({"validation": overall, "result": result.summary_dict()}, indent=2, default=float), encoding="utf-8")

    plt.figure(figsize=(11, 6))
    for idx, env in enumerate(result.envelopes):
        cls = result.capture_classification.loc[idx, "capture_class"]
        plt.plot(result.envelope_time_s, env, alpha=0.25 if cls == "inrush_present" else 0.12)
    if result.inrush_template_envelope_a.size:
        plt.plot(result.envelope_time_s, result.inrush_template_envelope_a, linewidth=2.3, label="Inrush population median envelope")
    if result.no_inrush_reference_envelope_a.size:
        plt.plot(result.envelope_time_s, result.no_inrush_reference_envelope_a, linewidth=2.3, label="Validated no-inrush reference")
    plt.xlabel("Time (s)")
    plt.ylabel("Sliding RMS current envelope (A)")
    plt.title("Current inrush population and no-inrush reference")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out / "current_inrush_v010_population_envelopes.png", dpi=180)
    plt.close()
    return overall


def package_bundle(directory: str | Path, zip_path: str | Path) -> Path:
    directory, zip_path = Path(directory), Path(zip_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=path.relative_to(directory))
    return zip_path


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    print(json.dumps(run_synthetic_validation(here), indent=2))
