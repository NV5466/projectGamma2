#!/usr/bin/env python3
"""
HSIB chunk recovery blind synthetic trial.

Chunk model:
    131 chunks total
    100 waveform pairs per chunk
    CH1 = one digital input line
    CH2 = one HSIB/middle-node candidate line or control output line

Chunks 1-100 are HSIB.
    chunk 1 has 1 ns hidden CH1-to-CH2 nuisance delay
    chunk 2 has 2 ns hidden CH1-to-CH2 nuisance delay
    ...
    chunk 100 has 100 ns hidden CH1-to-CH2 nuisance delay

Chunks 101-131 are non-HSIB controls.
    chunk 101 has 1 ns hidden nuisance delay
    chunk 102 has 2 ns hidden nuisance delay
    ...
    chunk 131 has 31 ns hidden nuisance delay

The classifier is chunk-level. It does not classify from one lonely waveform and it does not
measure timing offset. It recovers a stable response from 100 repeated captures, then asks:
    repeated input event + localized dangerous CH2 transient + downstream interpretation risk?
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import json
from typing import Dict, List, Tuple

import numpy as np


@dataclass(frozen=True)
class ChunkTruth:
    chunk_id: int
    truth_hsib: bool
    response_family: str
    noise_sigma_v: float
    nuisance_delay_ns: float


@dataclass(frozen=True)
class ChunkResult:
    chunk_id: int
    truth_hsib: bool
    predicted_hsib: bool
    response_family: str
    noise_sigma_v: float
    nuisance_delay_ns_hidden_not_used: float
    input_event_recovered: bool
    response_repeatable: bool
    localized_transient: bool
    downstream_danger: bool
    sustained_correct_waveform: bool
    recovered_peak_v: float
    recovered_rms_v: float
    off_event_rms_v: float
    localization_ratio: float
    threshold_segments: int
    zero_crossings: int
    repeatability_score: float
    reason: str


def smooth_step(t: np.ndarray, center: float, rise_s: float) -> np.ndarray:
    x = np.clip((t - center) / rise_s, -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-x))


def digital_pulse(t: np.ndarray, t0: float, width_s: float, amp_v: float = 5.0) -> np.ndarray:
    return amp_v * (smooth_step(t, t0, 0.9e-9) - smooth_step(t, t0 + width_s, 0.9e-9))


def hsib_response(t: np.ndarray, t0: float, chunk_id: int, delay_ns: float) -> np.ndarray:
    """Different hidden HSIB response for each HSIB chunk."""
    tr = t - (t0 + delay_ns * 1e-9)
    y = np.zeros_like(t)
    mask = tr >= 0.0

    amp = 3.0 + 0.55 * np.sin(0.37 * chunk_id) + 0.35 * ((chunk_id % 7) / 6.0)
    freq_hz = (28.0 + float((chunk_id * 7) % 125)) * 1e6
    tau_s = (55.0 + float((chunk_id * 11) % 145)) * 1e-9
    w = 2.0 * np.pi * freq_hz
    phase = 0.23 * chunk_id

    y[mask] = amp * np.exp(-tr[mask] / tau_s) * (
        0.58 * np.sin(w * tr[mask] + phase) + 0.42 * np.cos(0.73 * w * tr[mask])
    )
    y[mask] += 0.62 * amp * np.exp(-tr[mask] / (0.32 * tau_s))

    if chunk_id % 4 == 0:
        y[mask] += 0.28 * amp * np.exp(-tr[mask] / (1.40 * tau_s)) * np.sin(0.42 * w * tr[mask] + 0.70)
    if chunk_id % 5 == 0:
        y[mask] += 0.20 * amp * np.exp(-tr[mask] / (2.00 * tau_s))
    if chunk_id % 9 == 0:
        y[mask] *= -1.0

    return y


def control_response(t: np.ndarray, t0: float, chunk_id: int, delay_ns: float) -> np.ndarray:
    """Genuine output waveforms that are not HSIB transients."""
    control_id = chunk_id - 100
    phase = 0.31 * control_id
    shifted_t = t - delay_ns * 1e-9
    family = (control_id - 1) % 5

    if family == 0:
        return 2.5 + 1.8 * np.sign(np.sin(2.0 * np.pi * (3.0 + 0.25 * control_id) * 1e6 * shifted_t + phase))
    if family == 1:
        return 2.1 * np.sin(2.0 * np.pi * (4.5 + 0.18 * control_id) * 1e6 * shifted_t + phase)
    if family == 2:
        freq_hz = (2.5 + 0.11 * control_id) * 1e6
        frac = (shifted_t * freq_hz + phase / (2.0 * np.pi)) % 1.0
        triangle = 4.0 * np.abs(frac - 0.5) - 1.0
        return 2.0 * triangle
    if family == 3:
        return 3.0 * smooth_step(t, t0 + delay_ns * 1e-9 + 20.0e-9, 2.0e-9)

    freq_hz = (5.0 + 0.07 * control_id) * 1e6
    frac = (shifted_t * freq_hz + phase / (2.0 * np.pi)) % 1.0
    return np.where(frac < 0.35, 4.0, 0.5)


def chunk_truths() -> List[ChunkTruth]:
    truths: List[ChunkTruth] = []

    for chunk_id in range(1, 101):
        noise_sigma_v = 0.04 + 2.60 * ((chunk_id - 1) / 99.0) ** 1.35
        response_family = f"hsib_family_{((chunk_id - 1) % 10) + 1:02d}_delay_{chunk_id:03d}ns"
        truths.append(
            ChunkTruth(
                chunk_id=chunk_id,
                truth_hsib=True,
                response_family=response_family,
                noise_sigma_v=noise_sigma_v,
                nuisance_delay_ns=float(chunk_id),
            )
        )

    control_families = [
        "control_square_wave",
        "control_sine_wave",
        "control_triangle_wave",
        "control_sustained_step",
        "control_pwm_wave",
    ]
    for chunk_id in range(101, 132):
        control_id = chunk_id - 100
        noise_sigma_v = 0.35 + 1.40 * ((control_id - 1) / 30.0) ** 1.10
        response_family = f"{control_families[(control_id - 1) % len(control_families)]}_{control_id:02d}"
        truths.append(
            ChunkTruth(
                chunk_id=chunk_id,
                truth_hsib=False,
                response_family=response_family,
                noise_sigma_v=noise_sigma_v,
                nuisance_delay_ns=float(control_id),
            )
        )

    return truths


def generate_chunk(truth: ChunkTruth, rng: np.random.Generator, n_waveforms: int = 100) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    dt_s = 1.0e-9
    t = np.arange(0.0, 2.6e-6, dt_s)
    t0 = 500.0e-9
    width_s = 18.0e-9

    x_clean = digital_pulse(t, t0, width_s, 5.0)
    if truth.truth_hsib:
        m_clean = hsib_response(t, t0, truth.chunk_id, truth.nuisance_delay_ns)
    else:
        m_clean = control_response(t, t0, truth.chunk_id, truth.nuisance_delay_ns)

    x_stack = []
    m_stack = []
    for _ in range(n_waveforms):
        x_noise = rng.normal(0.0, 0.05 + 0.003 * min(truth.chunk_id, 100), size=t.size)
        m_noise = rng.normal(0.0, truth.noise_sigma_v, size=t.size)
        m_baseline = rng.normal(0.0, truth.noise_sigma_v * 0.05)
        m_slope = rng.normal(0.0, truth.noise_sigma_v * 0.03) * (t - np.mean(t)) / np.ptp(t)

        x_stack.append(x_clean + x_noise)
        m_stack.append(m_clean + m_baseline + m_slope + m_noise)

    return t, np.vstack(x_stack), np.vstack(m_stack)


def detect_input_event(t: np.ndarray, x_stack: np.ndarray) -> float:
    x_ref = np.median(x_stack, axis=0)
    threshold = float(np.min(x_ref) + 0.5 * (np.max(x_ref) - np.min(x_ref)))
    crossings = np.flatnonzero((x_ref[:-1] < threshold) & (x_ref[1:] >= threshold))
    if crossings.size == 0:
        return float("nan")
    return float(t[int(crossings[0])])


def count_segments(mask: np.ndarray) -> int:
    if mask.size == 0:
        return 0
    return int(mask[0]) + int(np.count_nonzero((~mask[:-1]) & mask[1:]))


def empty_result(truth: ChunkTruth, reason: str) -> ChunkResult:
    return ChunkResult(
        chunk_id=truth.chunk_id,
        truth_hsib=truth.truth_hsib,
        predicted_hsib=False,
        response_family=truth.response_family,
        noise_sigma_v=truth.noise_sigma_v,
        nuisance_delay_ns_hidden_not_used=truth.nuisance_delay_ns,
        input_event_recovered=False,
        response_repeatable=False,
        localized_transient=False,
        downstream_danger=False,
        sustained_correct_waveform=False,
        recovered_peak_v=0.0,
        recovered_rms_v=0.0,
        off_event_rms_v=0.0,
        localization_ratio=0.0,
        threshold_segments=0,
        zero_crossings=0,
        repeatability_score=0.0,
        reason=reason,
    )


def classify_chunk(t: np.ndarray, x_stack: np.ndarray, m_stack: np.ndarray, truth: ChunkTruth) -> ChunkResult:
    event_time = detect_input_event(t, x_stack)
    if not np.isfinite(event_time):
        return empty_result(truth, "input event not recovered")

    pre = (t >= event_time - 250.0e-9) & (t < event_time - 30.0e-9)
    post = (t >= event_time - 20.0e-9) & (t < event_time + 1050.0e-9)
    late = (t >= event_time + 1500.0e-9) & (t < event_time + 2500.0e-9)

    m_ref = np.median(m_stack, axis=0)
    baseline = float(np.median(m_ref[pre]))
    recovered = m_ref - baseline

    post_y = recovered[post]
    off_y = np.concatenate([recovered[pre], recovered[late]])
    recovered_peak = float(np.max(np.abs(post_y)))
    recovered_rms = float(np.sqrt(np.mean(post_y ** 2)))
    off_event_rms = float(np.sqrt(np.mean(off_y ** 2)))
    localization_ratio = recovered_rms / (off_event_rms + 1e-12)

    residual = m_stack - m_ref
    noise_est = float(np.std(residual[:, pre]))
    repeatability_score = recovered_peak / (noise_est / np.sqrt(m_stack.shape[0]) + 1e-12)

    receiver_threshold_v = 1.80
    above = np.abs(post_y) > receiver_threshold_v
    threshold_segments = count_segments(above)

    centered = post_y - np.median(post_y[: min(20, post_y.size)])
    zero_crossings = int(np.count_nonzero(centered[:-1] * centered[1:] < 0.0))

    late_rms = float(np.sqrt(np.mean(recovered[late] ** 2)))
    sustained_correct_waveform = bool(localization_ratio < 1.30 and late_rms > 0.45 * recovered_rms and recovered_rms > 0.50)

    input_event_recovered = True
    response_repeatable = bool(repeatability_score > 5.0)
    localized_transient = bool(localization_ratio > 1.25 and not sustained_correct_waveform)
    downstream_danger = bool(recovered_peak > receiver_threshold_v and (threshold_segments >= 1 or zero_crossings >= 1))

    predicted = bool(input_event_recovered and response_repeatable and localized_transient and downstream_danger)

    if predicted:
        reason = "input event recovered; repeatable localized CH2 transient; recovered response threatens downstream interpretation"
    elif sustained_correct_waveform:
        reason = "repeatable waveform is sustained/correct-like, not a localized HSIB transient"
    elif not localized_transient:
        reason = "CH2 response is not localized to the input event"
    elif not downstream_danger:
        reason = "recovered CH2 response does not threaten downstream interpretation"
    else:
        reason = "response did not pass repeatability gate"

    return ChunkResult(
        chunk_id=truth.chunk_id,
        truth_hsib=truth.truth_hsib,
        predicted_hsib=predicted,
        response_family=truth.response_family,
        noise_sigma_v=truth.noise_sigma_v,
        nuisance_delay_ns_hidden_not_used=truth.nuisance_delay_ns,
        input_event_recovered=input_event_recovered,
        response_repeatable=response_repeatable,
        localized_transient=localized_transient,
        downstream_danger=downstream_danger,
        sustained_correct_waveform=sustained_correct_waveform,
        recovered_peak_v=recovered_peak,
        recovered_rms_v=recovered_rms,
        off_event_rms_v=off_event_rms,
        localization_ratio=localization_ratio,
        threshold_segments=threshold_segments,
        zero_crossings=zero_crossings,
        repeatability_score=float(repeatability_score),
        reason=reason,
    )


def run_trial(seed: int = 5466) -> Dict[str, object]:
    rng = np.random.default_rng(seed)
    results: List[ChunkResult] = []

    for truth in chunk_truths():
        t, x_stack, m_stack = generate_chunk(truth, rng)
        results.append(classify_chunk(t, x_stack, m_stack, truth))

    hsib_recovered = sum(1 for r in results if r.truth_hsib and r.predicted_hsib)
    controls_rejected = sum(1 for r in results if (not r.truth_hsib) and (not r.predicted_hsib))
    false_pos = sum(1 for r in results if (not r.truth_hsib) and r.predicted_hsib)
    false_neg = sum(1 for r in results if r.truth_hsib and (not r.predicted_hsib))
    accuracy = (hsib_recovered + controls_rejected) / len(results)

    return {
        "seed": seed,
        "chunks": len(results),
        "waveforms_per_chunk": 100,
        "hsib_chunks": 100,
        "control_chunks": 31,
        "linear_hsib_delay_ns": "chunk_id, 1 through 100",
        "linear_control_delay_ns": "chunk_id - 100, 1 through 31",
        "delay_is_hidden_and_not_a_classification_feature": True,
        "hsib_recovered": hsib_recovered,
        "controls_rejected": controls_rejected,
        "false_pos": false_pos,
        "false_neg": false_neg,
        "accuracy": accuracy,
        "not_equivalent_to": [
            "chatter",
            "dropout",
            "coherence_only",
            "source_victim_only",
            "missed_short_pulse",
            "nanosecond_offset_measurement",
            "single_waveform_shape_match",
        ],
        "results": [asdict(r) for r in results],
    }


def print_table(summary: Dict[str, object]) -> None:
    print("HSIB chunk recovery synthetic trial")
    print("Chunks 1-100 are HSIB. Chunks 101-131 are genuine-waveform controls.")
    print("Hidden nuisance delay increases linearly and is not measured or used as a classifier target.")
    print()
    print(
        f"{'chunk':>5} {'truth':>6} {'pred':>6} {'dt_ns':>7} {'noise':>7} "
        f"{'family':>34} {'peak':>7} {'loc':>7} {'seg':>4} {'sustain':>8}"
    )
    print("-" * 112)
    for r in summary["results"]:
        print(
            f"{r['chunk_id']:5d} {str(r['truth_hsib']):>6} {str(r['predicted_hsib']):>6} "
            f"{r['nuisance_delay_ns_hidden_not_used']:7.1f} {r['noise_sigma_v']:7.2f} "
            f"{r['response_family']:>34} {r['recovered_peak_v']:7.3f} "
            f"{r['localization_ratio']:7.2f} {r['threshold_segments']:4d} "
            f"{str(r['sustained_correct_waveform']):>8}"
        )
    print("-" * 112)
    print(
        f"hsib_recovered={summary['hsib_recovered']}/100 "
        f"controls_rejected={summary['controls_rejected']}/31 "
        f"false_pos={summary['false_pos']} false_neg={summary['false_neg']} "
        f"accuracy={summary['accuracy']:.3f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the HSIB chunk recovery synthetic trial.")
    parser.add_argument("--seed", type=int, default=5466)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-assert", action="store_true")
    args = parser.parse_args()

    summary = run_trial(seed=args.seed)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print_table(summary)

    ok = summary["false_pos"] == 0 and summary["false_neg"] == 0
    if (not ok) and (not args.no_assert):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
