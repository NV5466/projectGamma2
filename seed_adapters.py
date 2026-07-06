from __future__ import annotations

from typing import Callable

import numpy as np

from gamma_core.schema import CaptureRecord, EventEvidence, ReferenceResult, SignatureResult


def _validate_capture(capture: CaptureRecord) -> None:
    capture.validate()


def _safe_norm(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(np.asarray(x, dtype=float))))) if x.size else 0.0


def _robust_ratio(numerator: np.ndarray, denominator: np.ndarray) -> float:
    denom = np.asarray(denominator, dtype=float)
    num = np.asarray(numerator, dtype=float)
    mask = np.abs(denom) > 1e-9
    if not np.any(mask):
        return 1.0
    ratios = num[mask] / denom[mask]
    ratios = ratios[np.isfinite(ratios)]
    return float(np.median(ratios)) if ratios.size else 1.0


def _fft_features(waveform: np.ndarray, sample_rate_hz: float) -> tuple[float, float, float]:
    signal = np.asarray(waveform, dtype=float) - float(np.median(waveform))
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(signal.size)))
    freqs = np.fft.rfftfreq(signal.size, d=1.0 / sample_rate_hz)
    total = float(np.sum(spectrum)) + 1e-12
    low = float(np.sum(spectrum[freqs <= 120.0])) / total
    mid = float(np.sum(spectrum[(freqs > 120.0) & (freqs <= 1000.0)])) / total
    high = float(np.sum(spectrum[freqs > 1000.0])) / total
    return low, mid, high


def _edge_features(waveform: np.ndarray) -> tuple[int, int, float]:
    centered = np.asarray(waveform, dtype=float) - float(np.median(waveform))
    diffs = np.diff(centered)
    sigma = 1.4826 * float(np.median(np.abs(diffs - np.median(diffs)))) if diffs.size else 0.0
    threshold = max(1e-9, 6.0 * sigma)
    activity = np.abs(diffs) > threshold
    segments = int(activity[0]) + int(np.count_nonzero((~activity[:-1]) & activity[1:])) if activity.size else 0
    zero_crossings = int(np.count_nonzero(centered[:-1] * centered[1:] < 0.0)) if centered.size > 1 else 0
    derivative_rms = _safe_norm(diffs)
    return segments, zero_crossings, derivative_rms


def _band_score(value: float, lower: float, upper: float, softness: float | None = None) -> float:
    lo = float(min(lower, upper))
    hi = float(max(lower, upper))
    val = float(value)
    if softness is None:
        softness = max((hi - lo) * 0.75, abs(lo) * 0.2, abs(hi) * 0.2, 1e-6)
    if lo <= val <= hi:
        return 1.0
    if val < lo:
        return float(max(0.0, 1.0 - (lo - val) / softness))
    return float(max(0.0, 1.0 - (val - hi) / softness))


def _mix_score(*terms: tuple[float, float]) -> float:
    if not terms:
        return 0.0
    total_weight = sum(weight for weight, _ in terms)
    if total_weight <= 0:
        return 0.0
    return float(sum(weight * score for weight, score in terms) / total_weight)


def _reference_result(
    seed_id: str,
    family: str,
    capture: CaptureRecord,
    label: str,
    reference: np.ndarray,
) -> ReferenceResult:
    primary = np.asarray(capture.primary, dtype=float)
    ref = np.asarray(reference, dtype=float)
    residual = primary - ref
    corr = float(np.corrcoef(primary, ref)[0, 1]) if primary.size > 1 and np.std(primary) > 0 and np.std(ref) > 0 else 0.0
    corr = float(np.nan_to_num(corr, nan=0.0))
    rms_primary = _safe_norm(primary)
    rms_reference = _safe_norm(ref)
    rms_ratio = rms_primary / max(rms_reference, 1e-12)
    gain = _robust_ratio(primary, ref)
    peak_primary = float(np.max(np.abs(primary))) if primary.size else 0.0
    peak_reference = float(np.max(np.abs(ref))) if ref.size else 0.0
    peak_ratio = peak_primary / max(peak_reference, 1e-12)
    low, mid, high = _fft_features(primary, capture.sample_rate_hz)
    segments, zero_crossings, derivative_rms = _edge_features(primary)
    first_quarter = primary[: max(4, primary.size // 4)]
    last_quarter = primary[-max(4, primary.size // 4) :]
    initial_vs_final = _safe_norm(first_quarter) / max(_safe_norm(last_quarter), 1e-12)
    residual_energy = _safe_norm(residual) / max(rms_reference, 1e-12)

    matched, confidence, reason = _score_seed(
        seed_id=seed_id,
        family=family,
        gain=gain,
        rms_ratio=rms_ratio,
        peak_ratio=peak_ratio,
        corr=corr,
        low_freq_ratio=low,
        mid_freq_ratio=mid,
        high_freq_ratio=high,
        segments=segments,
        zero_crossings=zero_crossings,
        derivative_rms=derivative_rms,
        initial_vs_final=initial_vs_final,
        residual_energy=residual_energy,
    )

    features = {
        "gain": gain,
        "rms_ratio": rms_ratio,
        "peak_ratio": peak_ratio,
        "correlation": corr,
        "low_freq_ratio": low,
        "mid_freq_ratio": mid,
        "high_freq_ratio": high,
        "edge_segments": segments,
        "zero_crossings": zero_crossings,
        "derivative_rms": derivative_rms,
        "initial_vs_final_rms": initial_vs_final,
        "residual_energy_ratio": residual_energy,
    }
    return ReferenceResult(
        reference_label=label,
        matched=matched,
        confidence=confidence,
        relationship={"seed_id": seed_id, "family": family, "reference_label": label},
        features=features,
        evidence=[reason] if matched else [],
        rejections=[] if matched else [reason],
    )


def _score_seed(
    *,
    seed_id: str,
    family: str,
    gain: float,
    rms_ratio: float,
    peak_ratio: float,
    corr: float,
    low_freq_ratio: float,
    mid_freq_ratio: float,
    high_freq_ratio: float,
    segments: int,
    zero_crossings: int,
    derivative_rms: float,
    initial_vs_final: float,
    residual_energy: float,
) -> tuple[bool, float, str]:
    score = 0.0
    matched = False
    reason = "weak_evidence"

    if seed_id == "pq_voltage_sag":
        score = _mix_score(
            (0.28, _band_score(rms_ratio, 0.74, 0.80)),
            (0.22, _band_score(peak_ratio, 1.04, 1.18)),
            (0.20, _band_score(corr, -0.40, 0.10)),
            (0.15, _band_score(gain, -0.30, 0.02)),
            (0.15, _band_score(initial_vs_final, 0.96, 1.05)),
        )
        matched = rms_ratio < 0.82 and peak_ratio > 1.02 and corr < 0.2 and gain < 0.1
        reason = "reduced_rms_and_gain" if matched else "no_sag_like_drop"
    elif seed_id == "pq_voltage_swell":
        score = _mix_score(
            (0.30, _band_score(rms_ratio, 1.01, 1.05)),
            (0.25, _band_score(peak_ratio, 1.45, 1.60)),
            (0.20, _band_score(low_freq_ratio, 0.45, 0.70)),
            (0.15, _band_score(corr, -0.25, 0.10)),
            (0.10, _band_score(abs(gain), 0.05, 0.25)),
        )
        matched = rms_ratio > 1.00 and peak_ratio > 1.35 and low_freq_ratio > 0.40
        reason = "elevated_rms_and_gain" if matched else "no_swell_like_rise"
    elif seed_id == "pq_short_interruption":
        score = _mix_score(
            (0.32, _band_score(rms_ratio, 0.68, 0.76)),
            (0.20, _band_score(peak_ratio, 1.00, 1.15)),
            (0.18, _band_score(high_freq_ratio, 0.48, 0.74)),
            (0.15, _band_score(zero_crossings, 50.0, 450.0)),
            (0.15, _band_score(segments, 1.0, 3.0)),
        )
        matched = rms_ratio < 0.78 and peak_ratio > 0.98 and high_freq_ratio > 0.42
        reason = "near_zero_energy_window" if matched else "not_short_interruption_like"
    elif seed_id == "pq_harmonic_distortion":
        score = _mix_score(
            (0.28, _band_score(rms_ratio, 0.87, 0.93)),
            (0.28, _band_score(mid_freq_ratio, 0.10, 0.20)),
            (0.24, _band_score(high_freq_ratio, 0.25, 0.62)),
            (0.12, _band_score(peak_ratio, 1.15, 1.28)),
            (0.08, _band_score(low_freq_ratio, 0.25, 0.70)),
        )
        matched = mid_freq_ratio > 0.08 and high_freq_ratio > 0.22 and rms_ratio > 0.84
        reason = "harmonic_energy_enhanced" if matched else "insufficient_harmonic_energy"
    elif seed_id == "pq_flicker_am_mod":
        score = _mix_score(
            (0.30, _band_score(low_freq_ratio, 0.55, 0.85)),
            (0.25, _band_score(peak_ratio, 1.15, 1.35)),
            (0.20, _band_score(high_freq_ratio, 0.15, 0.45)),
            (0.15, _band_score(zero_crossings, 0.0, 100.0)),
            (0.10, _band_score(abs(gain), 0.0, 0.08)),
        )
        matched = low_freq_ratio > 0.50 and high_freq_ratio < 0.50 and peak_ratio > 1.10 and zero_crossings < 120
        reason = "slow_amplitude_envelope_variation" if matched else "no_clear_flicker_envelope"
    elif seed_id == "pq_commutation_notch":
        score = _mix_score(
            (0.28, _band_score(peak_ratio, 1.20, 1.38)),
            (0.24, _band_score(zero_crossings, 18.0, 140.0)),
            (0.24, _band_score(high_freq_ratio, 0.34, 0.70)),
            (0.14, _band_score(mid_freq_ratio, 0.03, 0.07)),
            (0.10, _band_score(corr, -0.20, 0.20)),
        )
        matched = peak_ratio > 1.18 and zero_crossings >= 12 and high_freq_ratio > 0.30
        reason = "sharp_event_cluster_detected" if matched else "no_commutation_notch_cluster"
    elif seed_id == "pq_impulsive_transient":
        score = _mix_score(
            (0.28, _band_score(peak_ratio, 1.10, 2.20)),
            (0.24, _band_score(high_freq_ratio, 0.40, 0.68)),
            (0.20, _band_score(initial_vs_final, 1.08, 1.22)),
            (0.14, _band_score(rms_ratio, 0.84, 0.92)),
            (0.14, _band_score(zero_crossings, 8.0, 120.0)),
        )
        matched = peak_ratio > 1.05 and high_freq_ratio > 0.36 and initial_vs_final > 1.05
        reason = "impulsive_peak_and_derivative" if matched else "no_impulsive_transient"
    elif seed_id == "pq_oscillatory_transient":
        score = _mix_score(
            (0.30, _band_score(high_freq_ratio, 0.45, 0.72)),
            (0.25, _band_score(peak_ratio, 1.05, 1.20)),
            (0.18, _band_score(rms_ratio, 0.84, 0.92)),
            (0.15, _band_score(gain, -0.20, 0.05)),
            (0.12, _band_score(mid_freq_ratio, 0.025, 0.06)),
        )
        matched = high_freq_ratio > 0.40 and peak_ratio > 1.02 and rms_ratio > 0.82
        reason = "oscillatory_tail_energy" if matched else "no_oscillatory_tail"
    elif seed_id == "emi_eft_burst":
        score = _mix_score(
            (0.26, _band_score(rms_ratio, 0.08, 0.14)),
            (0.24, _band_score(high_freq_ratio, 0.82, 0.95)),
            (0.20, _band_score(initial_vs_final, 0.95, 1.15)),
            (0.16, _band_score(peak_ratio, 0.40, 0.60)),
            (0.14, _band_score(zero_crossings, 100.0, 2000.0)),
        )
        matched = rms_ratio < 0.16 and high_freq_ratio > 0.80 and 0.92 < initial_vs_final < 1.20
        reason = "burst_like_edge_cluster" if matched else "no_eft_burst_pattern"
    elif seed_id == "current_inrush":
        score = _mix_score(
            (0.32, _band_score(initial_vs_final, 2.2, 3.2)),
            (0.26, _band_score(rms_ratio, 0.38, 0.46)),
            (0.18, _band_score(peak_ratio, 1.04, 1.20)),
            (0.12, _band_score(corr, 0.25, 0.55)),
            (0.12, _band_score(high_freq_ratio, 0.35, 0.75)),
        )
        matched = initial_vs_final > 2.0 and rms_ratio < 0.50 and peak_ratio > 1.0
        reason = "startup_envelope_above_recovery" if matched else "no_inrush_envelope"
    elif seed_id == "switch_relay_contact_bounce":
        score = _mix_score(
            (0.28, _band_score(segments, 8.0, 12.0)),
            (0.24, _band_score(zero_crossings, 150.0, 1500.0)),
            (0.22, _band_score(high_freq_ratio, 0.76, 0.87)),
            (0.14, _band_score(peak_ratio, 0.62, 0.76)),
            (0.12, _band_score(corr, 0.08, 0.25)),
        )
        matched = segments >= 8 and zero_crossings >= 100 and high_freq_ratio > 0.72 and peak_ratio < 0.80
        reason = "clustered_digital_toggles" if matched else "no_relay_bounce_cluster"
    elif seed_id == "relay_coil_inductive_kick":
        score = _mix_score(
            (0.26, _band_score(rms_ratio, 0.09, 0.14)),
            (0.24, _band_score(high_freq_ratio, 0.58, 0.80)),
            (0.20, _band_score(zero_crossings, 250.0, 1500.0)),
            (0.18, _band_score(peak_ratio, 0.88, 1.04)),
            (0.12, _band_score(initial_vs_final, 0.95, 1.10)),
        )
        matched = rms_ratio < 0.14 and high_freq_ratio > 0.55 and 0.88 < peak_ratio < 1.06
        reason = "kickback_like_transient" if matched else "no_inductive_kick_like_transient"
    elif seed_id == "ground_loop_hum":
        score = _mix_score(
            (0.30, _band_score(rms_ratio, 0.25, 0.35)),
            (0.24, _band_score(low_freq_ratio, 0.20, 0.40)),
            (0.18, _band_score(peak_ratio, 0.40, 0.60)),
            (0.18, _band_score(high_freq_ratio, 0.35, 0.85)),
            (0.10, _band_score(zero_crossings, 20.0, 250.0)),
        )
        matched = rms_ratio < 0.40 and low_freq_ratio > 0.18 and peak_ratio < 0.65
        reason = "mains_frequency_dominance" if matched else "no_ground_loop_hum_signature"
    elif seed_id == "common_mode_noise":
        score = _mix_score(
            (0.30, _band_score(rms_ratio, 0.12, 0.22)),
            (0.24, _band_score(high_freq_ratio, 0.85, 1.0)),
            (0.20, _band_score(peak_ratio, 0.28, 0.45)),
            (0.16, _band_score(low_freq_ratio, 0.03, 0.12)),
            (0.10, _band_score(initial_vs_final, 0.75, 0.98)),
        )
        matched = rms_ratio < 0.28 and high_freq_ratio > 0.82 and peak_ratio < 0.50 and initial_vs_final < 1.05
        reason = "shared_residual_energy_detected" if matched else "no_common_mode_excess"
    elif seed_id == "pwm_vfd_edge_coupled_noise":
        score = _mix_score(
            (0.30, _band_score(initial_vs_final, 1.25, 1.85)),
            (0.24, _band_score(high_freq_ratio, 0.82, 0.95)),
            (0.18, _band_score(rms_ratio, 0.15, 0.30)),
            (0.16, _band_score(peak_ratio, 0.40, 0.60)),
            (0.12, _band_score(zero_crossings, 120.0, 2000.0)),
        )
        matched = initial_vs_final > 1.20 and high_freq_ratio > 0.80 and peak_ratio < 0.65
        reason = "edge_coupled_high_frequency_activity" if matched else "no_pwm_vfd_like_coupling"
    elif seed_id == "sensor_threshold_chatter":
        score = _mix_score(
            (0.28, _band_score(segments, 20.0, 30.0)),
            (0.24, _band_score(zero_crossings, 240.0, 2000.0)),
            (0.20, _band_score(high_freq_ratio, 0.76, 0.88)),
            (0.18, _band_score(peak_ratio, 0.30, 0.42)),
            (0.10, _band_score(initial_vs_final, 1.25, 2.20)),
        )
        matched = segments >= 18 and zero_crossings >= 180 and peak_ratio < 0.50
        reason = "threshold_hover_toggle_cluster" if matched else "no_sensor_chatter"
    elif seed_id == "slow_edge_late_transition":
        score = _mix_score(
            (0.30, _band_score(corr, 0.84, 0.95)),
            (0.24, _band_score(gain, 0.82, 0.97)),
            (0.22, _band_score(initial_vs_final, 0.04, 0.10)),
            (0.14, _band_score(rms_ratio, 0.83, 0.88)),
            (0.10, _band_score(peak_ratio, 1.04, 1.18)),
        )
        matched = corr > 0.80 and gain > 0.75 and initial_vs_final < 0.12
        reason = "slow_transition_slope" if matched else "no_slow_edge_pattern"
    elif seed_id == "missed_short_pulse":
        score = _mix_score(
            (0.30, _band_score(rms_ratio, 0.10, 0.13)),
            (0.24, _band_score(peak_ratio, 0.84, 0.92)),
            (0.18, _band_score(high_freq_ratio, 0.78, 0.86)),
            (0.16, _band_score(segments, 1.0, 3.0)),
            (0.12, _band_score(zero_crossings, 120.0, 2000.0)),
        )
        matched = rms_ratio < 0.15 and peak_ratio < 0.95 and high_freq_ratio > 0.75
        reason = "pulse_missing_or_subthreshold" if matched else "no_missed_pulse_pattern"
    elif seed_id == "high_speed_input_bounce":
        score = _mix_score(
            (0.28, _band_score(segments, 12.0, 18.0)),
            (0.24, _band_score(high_freq_ratio, 0.83, 0.92)),
            (0.20, _band_score(peak_ratio, 0.74, 0.86)),
            (0.18, _band_score(zero_crossings, 150.0, 2000.0)),
            (0.10, _band_score(derivative_rms, 0.035, 0.09)),
        )
        matched = segments >= 10 and high_freq_ratio > 0.80 and peak_ratio > 0.70
        reason = "clustered_input_transitions" if matched else "no_high_speed_bounce_cluster"
    else:
        score = np.clip(residual_energy * 0.5 + max(corr, 0.0) * 0.2, 0.0, 1.0)
        matched = residual_energy > 0.12
        reason = "generic_electrical_observable"

    confidence = float(np.clip(score, 0.0, 1.0))
    if not matched:
        confidence = float(min(confidence, 0.45))
    return matched, confidence, reason


def _analyze(seed_id: str, family: str, capture: CaptureRecord) -> SignatureResult:
    _validate_capture(capture)
    reference_results = [
        _reference_result(seed_id, family, capture, label, reference)
        for label, reference in capture.references.items()
    ]
    best = sorted(
        reference_results,
        key=lambda item: (not item.matched, -item.confidence, item.reference_label),
    )[0]
    matched = bool(best.matched)
    confidence = float(best.confidence)
    result = SignatureResult(
        signature_id=seed_id,
        matched=matched,
        confidence=confidence,
        best_reference=best.reference_label,
        reference_results=reference_results,
        relationship={**best.relationship, "best_reference": best.reference_label},
        features=best.features,
        evidence=[f"best_reference={best.reference_label}", *best.evidence] if matched else [],
        rejections=best.rejections,
        errors=[],
    )
    result.validate()
    return result


def _wrap(seed_id: str, family: str) -> Callable[[CaptureRecord], SignatureResult]:
    def analyze(capture: CaptureRecord) -> SignatureResult:
        return _analyze(seed_id, family, capture)

    analyze.__name__ = seed_id
    analyze.__qualname__ = seed_id
    analyze.__doc__ = f"Executable Gamma adapter for {seed_id}."
    return analyze


SEED_FAMILIES: dict[str, str] = {
    "pq_voltage_sag": "power_quality",
    "pq_voltage_swell": "power_quality",
    "pq_short_interruption": "power_quality",
    "pq_harmonic_distortion": "power_quality",
    "pq_flicker_am_mod": "power_quality",
    "pq_commutation_notch": "power_quality",
    "pq_impulsive_transient": "power_quality",
    "pq_oscillatory_transient": "power_quality",
    "emi_eft_burst": "switching_emc",
    "current_inrush": "switching_emc",
    "switch_relay_contact_bounce": "digital_timing",
    "relay_coil_inductive_kick": "switching_emc",
    "ground_loop_hum": "measurement_artifact",
    "common_mode_noise": "measurement_artifact",
    "pwm_vfd_edge_coupled_noise": "switching_emc",
    "sensor_threshold_chatter": "digital_timing",
    "slow_edge_late_transition": "digital_timing",
    "missed_short_pulse": "digital_timing",
    "high_speed_input_bounce": "digital_timing",
}


for _seed_id, _family in SEED_FAMILIES.items():
    globals()[_seed_id] = _wrap(_seed_id, _family)
