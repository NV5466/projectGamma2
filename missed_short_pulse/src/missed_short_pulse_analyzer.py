from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, Sequence
import math

import numpy as np
import pandas as pd


@dataclass
class Pulse:
    rise_s: float
    fall_s: float
    width_s: float
    peak: float
    area: float
    rise_index: int
    fall_index: int


@dataclass
class AcquisitionAssessment:
    samples_across_pulse: float
    confidence: str
    note: str


@dataclass
class PulseEventResult:
    source_index: int
    source_rise_s: float
    source_width_s: float
    source_samples: float
    acquisition_confidence: str
    matched_output_indices: str
    output_count: int
    output_rise_s: Optional[float]
    output_width_s: Optional[float]
    latency_s: Optional[float]
    width_ratio: Optional[float]
    downstream_peak: float
    observed_failure_mode: str
    candidate_mechanism: str
    system_consequence: str
    confidence: str
    estimated_tau_s: Optional[float]
    estimated_cutoff_hz: Optional[float]
    estimated_q: Optional[float]
    notes: str


@dataclass
class AnalysisSummary:
    expected_pulses: int
    matched_pulses: int
    missed_pulses: int
    split_pulses: int
    merged_groups: int
    extra_output_pulses: int
    detection_ratio: float
    acquisition_limited_events: int
    dominant_classification: str


def moving_average(x: np.ndarray, samples: int) -> np.ndarray:
    samples = max(1, int(samples))
    if samples == 1:
        return np.asarray(x, dtype=float)
    kernel = np.ones(samples, dtype=float) / samples
    return np.convolve(np.asarray(x, dtype=float), kernel, mode="same")

def robust_noise_sigma(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    return max(1.4826 * mad, 1e-12)

def schmitt_binary(
    x: np.ndarray,
    low_threshold: float,
    high_threshold: float,
) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    state = np.zeros(len(x), dtype=np.int8)
    state[0] = int(x[0] >= (low_threshold + high_threshold) / 2)

    for i in range(1, len(x)):
        if x[i] >= high_threshold:
            state[i] = 1
        elif x[i] <= low_threshold:
            state[i] = 0
        else:
            state[i] = state[i - 1]
    return state

def detect_pulses(
    t: np.ndarray,
    x: np.ndarray,
    threshold: float,
    hysteresis_fraction: float = 0.08,
    smoothing_samples: int = 1,
) -> list[Pulse]:
    """
    Detect positive pulses using a Schmitt threshold around the requested logic threshold.
    """
    t = np.asarray(t, dtype=float)
    x = moving_average(np.asarray(x, dtype=float), smoothing_samples)

    amplitude_scale = max(
        float(np.quantile(x, 0.99) - np.quantile(x, 0.01)),
        abs(threshold),
        1e-9,
    )
    half_band = hysteresis_fraction * amplitude_scale / 2
    low_threshold = threshold - half_band
    high_threshold = threshold + half_band

    state = schmitt_binary(x, low_threshold, high_threshold)
    rising = np.flatnonzero(np.diff(state) == 1) + 1
    falling = np.flatnonzero(np.diff(state) == -1) + 1

    pulses: list[Pulse] = []
    fall_cursor = 0

    for rise_index in rising:
        while fall_cursor < len(falling) and falling[fall_cursor] <= rise_index:
            fall_cursor += 1
        if fall_cursor >= len(falling):
            fall_index = len(t) - 1
        else:
            fall_index = int(falling[fall_cursor])
            fall_cursor += 1

        if fall_index <= rise_index:
            continue

        segment = x[rise_index : fall_index + 1]
        segment_t = t[rise_index : fall_index + 1]
        pulses.append(
            Pulse(
                rise_s=float(t[rise_index]),
                fall_s=float(t[fall_index]),
                width_s=float(t[fall_index] - t[rise_index]),
                peak=float(np.max(segment)),
                area=float(np.trapezoid(segment, segment_t)),
                rise_index=int(rise_index),
                fall_index=int(fall_index),
            )
        )

    return pulses

def assess_acquisition(
    pulse_width_s: float,
    sample_rate_hz: float,
    acquisition_bandwidth_hz: Optional[float] = None,
) -> AcquisitionAssessment:
    samples = pulse_width_s * sample_rate_hz

    if samples < 2:
        confidence = "inadequate"
        note = "Fewer than two samples span the source pulse; a hardware miss cannot be confirmed."
    elif samples < 5:
        confidence = "limited"
        note = "Pulse is sparsely sampled; existence is plausible but width and morphology are unreliable."
    elif samples < 10:
        confidence = "usable"
        note = "Pulse is observable, but precision is limited."
    else:
        confidence = "strong"
        note = "Pulse has enough samples for confident event matching."

    if acquisition_bandwidth_hz is not None and pulse_width_s > 0:
        # A rectangular pulse's useful edge content extends well beyond 1/T.
        required = 0.35 / pulse_width_s
        if acquisition_bandwidth_hz < required:
            note += " Acquisition bandwidth is also low relative to the pulse edge requirement."
            if confidence == "strong":
                confidence = "usable"
            elif confidence == "usable":
                confidence = "limited"

    return AcquisitionAssessment(
        samples_across_pulse=float(samples),
        confidence=confidence,
        note=note,
    )

def analog_window_metrics(
    t: np.ndarray,
    output: np.ndarray,
    start_s: float,
    end_s: float,
    baseline_end_s: Optional[float] = None,
) -> tuple[float, float, float]:
    mask = (t >= start_s) & (t <= end_s)
    if not np.any(mask):
        return 0.0, 0.0, 0.0

    if baseline_end_s is None:
        baseline_end_s = start_s
    baseline_mask = t < baseline_end_s
    if not np.any(baseline_mask):
        baseline = float(np.median(output[: max(5, len(output) // 20)]))
        noise = robust_noise_sigma(output[: max(5, len(output) // 20)])
    else:
        baseline = float(np.median(output[baseline_mask]))
        noise = robust_noise_sigma(output[baseline_mask])

    local = output[mask]
    peak = float(np.max(local))
    excursion = float(peak - baseline)
    snr = excursion / max(noise, 1e-12)
    return peak, excursion, snr

def estimate_rc_tau(
    source_amplitude: float,
    downstream_peak: float,
    pulse_width_s: float,
    baseline: float = 0.0,
) -> tuple[Optional[float], Optional[float]]:
    """
    Estimate a first-order charging time constant from:
        Vpeak/Vin = 1 - exp(-Tp/tau)
    This is only a compatibility estimate, not proof of an RC mechanism.
    """
    vin = source_amplitude - baseline
    vout = downstream_peak - baseline
    if vin <= 0 or vout <= 0:
        return None, None

    ratio = vout / vin
    if ratio <= 0 or ratio >= 0.98:
        return None, None

    tau = -pulse_width_s / math.log(max(1e-12, 1.0 - ratio))
    if tau <= 0 or not math.isfinite(tau):
        return None, None

    cutoff = 1.0 / (2.0 * math.pi * tau)
    return float(tau), float(cutoff)

def estimate_ring_q(
    t: np.ndarray,
    x: np.ndarray,
    event_start_s: float,
    event_end_s: float,
    baseline: float,
) -> Optional[float]:
    """
    Conservative ring-down Q estimate from successive same-polarity peaks.
    Only returns a value if a visibly oscillatory decay is present.
    """
    mask = (t >= event_start_s) & (t <= event_end_s)
    if np.sum(mask) < 20:
        return None

    local_t = t[mask]
    local = x[mask] - baseline
    dt = float(np.median(np.diff(local_t)))
    smooth = moving_average(local, max(1, int(round(3e-6 / dt))))

    derivative = np.diff(smooth)
    peaks = np.flatnonzero((derivative[:-1] > 0) & (derivative[1:] <= 0)) + 1
    peaks = peaks[smooth[peaks] > 0]

    if len(peaks) < 3:
        return None

    amplitudes = smooth[peaks]
    times = local_t[peaks]

    # Require decaying positive peaks.
    valid_pairs = []
    for i in range(len(amplitudes) - 1):
        if amplitudes[i] > amplitudes[i + 1] > 0:
            valid_pairs.append((i, i + 1))

    if len(valid_pairs) < 2:
        return None

    decrements = [
        math.log(amplitudes[i] / amplitudes[j])
        for i, j in valid_pairs
        if amplitudes[i] > amplitudes[j] > 0
    ]
    periods = [
        times[j] - times[i]
        for i, j in valid_pairs
        if times[j] > times[i]
    ]

    if not decrements or not periods:
        return None

    delta = float(np.median(decrements))
    if delta <= 0:
        return None

    # Exact logarithmic-decrement relationship.
    q = math.pi / math.sqrt(delta * delta + 1e-12)
    if not (0.2 <= q <= 100):
        return None
    return float(q)

def _candidate_outputs_for_source(
    source: Pulse,
    outputs: Sequence[Pulse],
    latency_min_s: float,
    latency_max_s: float,
    extended_late_window_s: float,
) -> list[int]:
    indices = []
    lower = source.rise_s + latency_min_s
    upper = source.rise_s + max(latency_max_s, extended_late_window_s)
    for index, pulse in enumerate(outputs):
        if lower <= pulse.rise_s <= upper:
            indices.append(index)
    return indices

def analyze_missed_short_pulse(
    t: np.ndarray,
    source: np.ndarray,
    output: np.ndarray,
    source_threshold: float,
    output_threshold: float,
    latency_min_s: float = 0.0,
    latency_max_s: float = 0.003,
    minimum_valid_output_width_s: Optional[float] = None,
    sample_rate_hz: Optional[float] = None,
    acquisition_bandwidth_hz: Optional[float] = None,
    system_consequence: str = "logically missed",
) -> tuple[pd.DataFrame, AnalysisSummary, dict]:
    """
    Classify pulse propagation without forcing a physical mechanism.
    """
    t = np.asarray(t, dtype=float)
    source = np.asarray(source, dtype=float)
    output = np.asarray(output, dtype=float)

    if sample_rate_hz is None:
        sample_rate_hz = 1.0 / float(np.median(np.diff(t)))

    smoothing_samples = max(1, int(round(sample_rate_hz * 2e-6)))
    source_pulses = detect_pulses(
        t, source, source_threshold, smoothing_samples=smoothing_samples
    )
    output_pulses = detect_pulses(
        t, output, output_threshold, smoothing_samples=smoothing_samples
    )

    if minimum_valid_output_width_s is None and source_pulses:
        minimum_valid_output_width_s = 0.5 * float(
            np.median([pulse.width_s for pulse in source_pulses])
        )
    elif minimum_valid_output_width_s is None:
        minimum_valid_output_width_s = 0.0

    source_amplitude = float(
        np.quantile(source, 0.99) - np.quantile(source, 0.01)
    )
    output_baseline = float(np.quantile(output, 0.05))

    source_to_outputs: dict[int, list[int]] = {}
    output_to_sources: dict[int, list[int]] = {i: [] for i in range(len(output_pulses))}

    for source_index, source_pulse in enumerate(source_pulses):
        candidates = _candidate_outputs_for_source(
            source_pulse,
            output_pulses,
            latency_min_s,
            latency_max_s,
            extended_late_window_s=max(latency_max_s * 4, 0.020),
        )
        source_to_outputs[source_index] = candidates
        for output_index in candidates:
            output_to_sources[output_index].append(source_index)

    # Identify real merge groups: one output pulse spans the expected arrival regions
    # of multiple source pulses.
    merge_groups: list[tuple[int, list[int]]] = []
    for output_index, sources_for_output in output_to_sources.items():
        output_pulse = output_pulses[output_index]
        spanning_sources = []
        for source_index, source_pulse in enumerate(source_pulses):
            expected_start = source_pulse.rise_s + latency_min_s
            expected_end = source_pulse.fall_s + max(latency_max_s, latency_min_s)
            if (
                output_pulse.rise_s <= expected_start + 0.001
                and output_pulse.fall_s >= expected_end - 0.001
            ):
                spanning_sources.append(source_index)
        if len(spanning_sources) >= 2:
            merge_groups.append((output_index, spanning_sources))

    merged_source_indices = {
        source_index
        for _, group in merge_groups
        for source_index in group
    }

    used_output_indices: set[int] = set()
    rows: list[PulseEventResult] = []

    for source_index, source_pulse in enumerate(source_pulses):
        acquisition = assess_acquisition(
            source_pulse.width_s,
            sample_rate_hz,
            acquisition_bandwidth_hz,
        )

        expected_start = source_pulse.rise_s + latency_min_s
        expected_end = source_pulse.fall_s + max(latency_max_s, latency_min_s)
        analog_search_end = source_pulse.rise_s + max(latency_max_s * 4, 0.020)
        peak, excursion, snr = analog_window_metrics(
            t,
            output,
            start_s=max(0.0, expected_start - 0.0005),
            end_s=min(float(t[-1]), analog_search_end),
            baseline_end_s=max(0.0, expected_start - 0.0005),
        )

        if source_index in merged_source_indices:
            matching_merge = next(
                (item for item in merge_groups if source_index in item[1]),
                None,
            )
            assert matching_merge is not None
            output_index = matching_merge[0]
            output_pulse = output_pulses[output_index]
            used_output_indices.add(output_index)

            rows.append(
                PulseEventResult(
                    source_index=source_index,
                    source_rise_s=source_pulse.rise_s,
                    source_width_s=source_pulse.width_s,
                    source_samples=acquisition.samples_across_pulse,
                    acquisition_confidence=acquisition.confidence,
                    matched_output_indices=str(output_index),
                    output_count=1,
                    output_rise_s=output_pulse.rise_s,
                    output_width_s=output_pulse.width_s,
                    latency_s=output_pulse.rise_s - source_pulse.rise_s,
                    width_ratio=output_pulse.width_s / max(source_pulse.width_s, 1e-12),
                    downstream_peak=peak,
                    observed_failure_mode="pulse merging",
                    candidate_mechanism="slow recovery, filtering, saturation, or debounce",
                    system_consequence=system_consequence,
                    confidence="high" if acquisition.confidence in {"strong", "usable"} else "limited",
                    estimated_tau_s=None,
                    estimated_cutoff_hz=None,
                    estimated_q=None,
                    notes=acquisition.note,
                )
            )
            continue

        candidates = source_to_outputs[source_index]

        # Restrict normal matches to the expected latency window.
        expected_candidates = [
            index
            for index in candidates
            if output_pulses[index].rise_s <= source_pulse.rise_s + latency_max_s
        ]
        late_candidates = [
            index
            for index in candidates
            if output_pulses[index].rise_s > source_pulse.rise_s + latency_max_s
        ]

        if len(expected_candidates) > 1:
            for output_index in expected_candidates:
                used_output_indices.add(output_index)

            first = output_pulses[expected_candidates[0]]
            q_est = estimate_ring_q(
                t,
                output,
                first.rise_s,
                min(float(t[-1]), first.rise_s + 0.010),
                baseline=output_baseline,
            )

            rows.append(
                PulseEventResult(
                    source_index=source_index,
                    source_rise_s=source_pulse.rise_s,
                    source_width_s=source_pulse.width_s,
                    source_samples=acquisition.samples_across_pulse,
                    acquisition_confidence=acquisition.confidence,
                    matched_output_indices=",".join(map(str, expected_candidates)),
                    output_count=len(expected_candidates),
                    output_rise_s=first.rise_s,
                    output_width_s=first.width_s,
                    latency_s=first.rise_s - source_pulse.rise_s,
                    width_ratio=first.width_s / max(source_pulse.width_s, 1e-12),
                    downstream_peak=peak,
                    observed_failure_mode="pulse splitting",
                    candidate_mechanism=(
                        "resonant distortion or ringing"
                        if q_est is not None
                        else "chatter, ringing, or repeated threshold crossing"
                    ),
                    system_consequence=system_consequence,
                    confidence="high" if acquisition.confidence in {"strong", "usable"} else "limited",
                    estimated_tau_s=None,
                    estimated_cutoff_hz=None,
                    estimated_q=q_est,
                    notes=acquisition.note,
                )
            )
            continue

        selected_index: Optional[int] = None
        late = False

        if expected_candidates:
            selected_index = min(
                expected_candidates,
                key=lambda index: abs(
                    output_pulses[index].rise_s
                    - (source_pulse.rise_s + latency_min_s)
                ),
            )
        elif late_candidates:
            selected_index = min(
                late_candidates,
                key=lambda index: output_pulses[index].rise_s,
            )
            late = True

        if selected_index is None:
            tau, cutoff = estimate_rc_tau(
                source_amplitude=source_amplitude,
                downstream_peak=peak,
                pulse_width_s=source_pulse.width_s,
                baseline=output_baseline,
            )

            if acquisition.confidence == "inadequate":
                failure = "possible acquisition miss"
                mechanism = "insufficient sample rate or acquisition bandwidth"
                confidence = "unresolved"
            elif excursion <= max(5.0 * robust_noise_sigma(output[t < expected_start]), 0.03 * source_amplitude):
                failure = "complete pulse non-propagation"
                mechanism = "open path, gating, dead time, disabled logic, or total attenuation"
                confidence = "high" if acquisition.confidence == "strong" else "moderate"
            elif peak < output_threshold:
                failure = "subthreshold pulse suppression"
                mechanism = (
                    "bandwidth-limited attenuation compatible with a real-pole response"
                    if tau is not None
                    else "attenuation, loading, weak drive, or threshold rejection"
                )
                confidence = "high" if snr >= 8 else "moderate"
            else:
                failure = "unresolved pulse miss"
                mechanism = "state-dependent gating, nonlinearity, or unmatched timing"
                confidence = "moderate"

            rows.append(
                PulseEventResult(
                    source_index=source_index,
                    source_rise_s=source_pulse.rise_s,
                    source_width_s=source_pulse.width_s,
                    source_samples=acquisition.samples_across_pulse,
                    acquisition_confidence=acquisition.confidence,
                    matched_output_indices="",
                    output_count=0,
                    output_rise_s=None,
                    output_width_s=None,
                    latency_s=None,
                    width_ratio=None,
                    downstream_peak=peak,
                    observed_failure_mode=failure,
                    candidate_mechanism=mechanism,
                    system_consequence=system_consequence,
                    confidence=confidence,
                    estimated_tau_s=tau,
                    estimated_cutoff_hz=cutoff,
                    estimated_q=None,
                    notes=f"{acquisition.note} Analog-response SNR ≈ {snr:.1f}.",
                )
            )
            continue

        used_output_indices.add(selected_index)
        output_pulse = output_pulses[selected_index]
        latency = output_pulse.rise_s - source_pulse.rise_s
        width_ratio = output_pulse.width_s / max(source_pulse.width_s, 1e-12)

        if late:
            failure = "late pulse propagation"
            mechanism = "delayed actuation, gating, processing latency, or state-dependent path delay"
        elif output_pulse.width_s < minimum_valid_output_width_s or width_ratio < 0.5:
            failure = "pulse-width collapse"
            mechanism = "threshold clipping, weak drive, narrow pass window, or filtering"
        elif width_ratio > 1.5:
            failure = "pulse stretching"
            mechanism = "slow discharge, saturation recovery, filtering, or hold/debounce behavior"
        else:
            failure = "valid pulse propagation"
            mechanism = "no fault mechanism indicated"

        rows.append(
            PulseEventResult(
                source_index=source_index,
                source_rise_s=source_pulse.rise_s,
                source_width_s=source_pulse.width_s,
                source_samples=acquisition.samples_across_pulse,
                acquisition_confidence=acquisition.confidence,
                matched_output_indices=str(selected_index),
                output_count=1,
                output_rise_s=output_pulse.rise_s,
                output_width_s=output_pulse.width_s,
                latency_s=latency,
                width_ratio=width_ratio,
                downstream_peak=peak,
                observed_failure_mode=failure,
                candidate_mechanism=mechanism,
                system_consequence=system_consequence,
                confidence="high" if acquisition.confidence == "strong" else "moderate",
                estimated_tau_s=None,
                estimated_cutoff_hz=None,
                estimated_q=None,
                notes=acquisition.note,
            )
        )

    extra_outputs = [
        index for index in range(len(output_pulses)) if index not in used_output_indices
    ]

    results_df = pd.DataFrame([asdict(row) for row in rows])

    missed_modes = {
        "complete pulse non-propagation",
        "subthreshold pulse suppression",
        "possible acquisition miss",
        "unresolved pulse miss",
    }
    matched_count = int(
        np.sum(~results_df["observed_failure_mode"].isin(missed_modes))
    ) if not results_df.empty else 0
    missed_count = int(
        np.sum(results_df["observed_failure_mode"].isin(missed_modes))
    ) if not results_df.empty else 0
    split_count = int(
        np.sum(results_df["observed_failure_mode"] == "pulse splitting")
    ) if not results_df.empty else 0
    acquisition_limited = int(
        np.sum(results_df["acquisition_confidence"].isin(["inadequate", "limited"]))
    ) if not results_df.empty else 0

    if results_df.empty:
        dominant = "no source pulses detected"
    else:
        dominant = str(
            results_df["observed_failure_mode"]
            .value_counts()
            .index[0]
        )

    summary = AnalysisSummary(
        expected_pulses=len(source_pulses),
        matched_pulses=matched_count,
        missed_pulses=missed_count,
        split_pulses=split_count,
        merged_groups=len(merge_groups),
        extra_output_pulses=len(extra_outputs),
        detection_ratio=(
            matched_count / len(source_pulses) if source_pulses else 0.0
        ),
        acquisition_limited_events=acquisition_limited,
        dominant_classification=dominant,
    )

    diagnostics = {
        "source_pulses": [asdict(pulse) for pulse in source_pulses],
        "output_pulses": [asdict(pulse) for pulse in output_pulses],
        "merge_groups": merge_groups,
        "extra_output_indices": extra_outputs,
        "source_amplitude": source_amplitude,
        "output_baseline": output_baseline,
        "minimum_valid_output_width_s": minimum_valid_output_width_s,
        "sample_rate_hz": sample_rate_hz,
    }

    return results_df, summary, diagnostics

def _recalculate_summary_v2(
    frame: pd.DataFrame,
    source_count: int,
    output_count: int,
    merged_groups: int,
    used_outputs: set[int],
) -> AnalysisSummary:
    missed_modes = {
        "complete pulse non-propagation",
        "subthreshold pulse suppression",
        "possible acquisition miss",
        "unresolved pulse miss",
    }

    missed_count = int(frame["observed_failure_mode"].isin(missed_modes).sum())
    matched_count = source_count - missed_count
    split_count = int((frame["observed_failure_mode"] == "pulse splitting").sum())
    acquisition_limited = int(
        frame["acquisition_confidence"].isin(["inadequate", "limited"]).sum()
    )
    extra_outputs = max(0, output_count - len(used_outputs))

    dominant = (
        str(frame["observed_failure_mode"].value_counts().index[0])
        if not frame.empty
        else "no source pulses detected"
    )

    return AnalysisSummary(
        expected_pulses=source_count,
        matched_pulses=matched_count,
        missed_pulses=missed_count,
        split_pulses=split_count,
        merged_groups=merged_groups,
        extra_output_pulses=extra_outputs,
        detection_ratio=matched_count / source_count if source_count else 0.0,
        acquisition_limited_events=acquisition_limited,
        dominant_classification=dominant,
    )

def analyze_missed_short_pulse_v2(
    t: np.ndarray,
    source: np.ndarray,
    output: np.ndarray,
    source_threshold: float,
    output_threshold: float,
    latency_min_s: float = 0.0,
    latency_max_s: float = 0.003,
    minimum_valid_output_width_s: Optional[float] = None,
    sample_rate_hz: Optional[float] = None,
    acquisition_bandwidth_hz: Optional[float] = None,
    system_consequence: str = "logically missed",
):
    frame, summary, diagnostics = analyze_missed_short_pulse(
        t=t,
        source=source,
        output=output,
        source_threshold=source_threshold,
        output_threshold=output_threshold,
        latency_min_s=latency_min_s,
        latency_max_s=latency_max_s,
        minimum_valid_output_width_s=minimum_valid_output_width_s,
        sample_rate_hz=sample_rate_hz,
        acquisition_bandwidth_hz=acquisition_bandwidth_hz,
        system_consequence=system_consequence,
    )

    source_pulses = [Pulse(**item) for item in diagnostics["source_pulses"]]
    output_pulses = [Pulse(**item) for item in diagnostics["output_pulses"]]

    merge_groups = []
    for output_index, output_pulse in enumerate(output_pulses):
        overlapping_sources = []
        for source_index, source_pulse in enumerate(source_pulses):
            window_start = source_pulse.rise_s + latency_min_s
            window_end = source_pulse.rise_s + latency_max_s

            # A downstream pulse can represent a source pulse when it overlaps
            # that source's valid arrival window. If the same downstream pulse
            # overlaps two or more source windows, the events have merged.
            overlaps = (
                output_pulse.fall_s >= window_start
                and output_pulse.rise_s <= window_end
            )
            if overlaps:
                overlapping_sources.append(source_index)

        if len(overlapping_sources) >= 2:
            merge_groups.append((output_index, overlapping_sources))

    if not merge_groups or frame.empty:
        return frame, summary, diagnostics

    used_outputs: set[int] = set()
    for output_index, source_indices in merge_groups:
        output_pulse = output_pulses[output_index]
        used_outputs.add(output_index)

        for source_index in source_indices:
            row_mask = frame["source_index"] == source_index
            if not row_mask.any():
                continue

            source_pulse = source_pulses[source_index]
            frame.loc[row_mask, "matched_output_indices"] = str(output_index)
            frame.loc[row_mask, "output_count"] = 1
            frame.loc[row_mask, "output_rise_s"] = output_pulse.rise_s
            frame.loc[row_mask, "output_width_s"] = output_pulse.width_s
            frame.loc[row_mask, "latency_s"] = (
                output_pulse.rise_s - source_pulse.rise_s
            )
            frame.loc[row_mask, "width_ratio"] = (
                output_pulse.width_s / max(source_pulse.width_s, 1e-12)
            )
            frame.loc[row_mask, "observed_failure_mode"] = "pulse merging"
            frame.loc[row_mask, "candidate_mechanism"] = (
                "slow recovery, filtering, saturation, or debounce"
            )
            frame.loc[row_mask, "confidence"] = "high"

    # Collect all output indices already claimed by non-missed rows.
    for value in frame["matched_output_indices"].astype(str):
        if not value:
            continue
        for token in value.split(","):
            token = token.strip()
            if token.isdigit():
                used_outputs.add(int(token))

    summary = _recalculate_summary_v2(
        frame=frame,
        source_count=len(source_pulses),
        output_count=len(output_pulses),
        merged_groups=len(merge_groups),
        used_outputs=used_outputs,
    )
    diagnostics["merge_groups"] = merge_groups
    diagnostics["extra_output_indices"] = [
        i for i in range(len(output_pulses)) if i not in used_outputs
    ]
    return frame, summary, diagnostics

__all__ = [
    "Pulse",
    "AcquisitionAssessment",
    "PulseEventResult",
    "AnalysisSummary",
    "detect_pulses",
    "assess_acquisition",
    "estimate_rc_tau",
    "estimate_ring_q",
    "analyze_missed_short_pulse",
    "analyze_missed_short_pulse_v2",
]
