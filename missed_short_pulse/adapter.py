from __future__ import annotations

import numpy as np

from gamma_core.schema import CaptureRecord, ReferenceResult, SignatureResult

from .src.missed_short_pulse_analyzer import analyze_missed_short_pulse

SIGNATURE_ID = "missed_short_pulse"


def _threshold(x: np.ndarray) -> float:
    return float(np.quantile(x, 0.05) + 0.5 * (np.quantile(x, 0.95) - np.quantile(x, 0.05)))


def _reference_score(capture: CaptureRecord, label: str, reference: np.ndarray) -> ReferenceResult:
    source_thresholds = dict(capture.metadata.get("source_thresholds", {}))
    output_threshold = float(capture.metadata.get("output_threshold", _threshold(capture.primary)))
    source_threshold = float(source_thresholds.get(label, capture.metadata.get("source_threshold", _threshold(reference))))
    frame, summary, _diagnostics = analyze_missed_short_pulse(
        t=capture.time_s,
        source=reference,
        output=capture.primary,
        source_threshold=source_threshold,
        output_threshold=output_threshold,
        sample_rate_hz=capture.sample_rate_hz,
        latency_max_s=float(capture.metadata.get("latency_max_s", 0.003)),
    )
    expected = int(summary.expected_pulses)
    missed = int(summary.missed_pulses)
    detection_ratio = float(summary.detection_ratio)
    miss_ratio = missed / expected if expected else 0.0
    max_expected = int(capture.metadata.get("missed_short_pulse_max_expected_pulses", 10))
    sparse_logic_reference = expected <= max_expected
    matched = bool(expected > 0 and missed > 0 and sparse_logic_reference)
    confidence = float(np.clip(0.55 + 0.45 * miss_ratio if matched else 0.0, 0.0, 1.0))
    features = {
        "expected_pulses": expected,
        "missed_pulses": missed,
        "matched_pulses": int(summary.matched_pulses),
        "miss_ratio": float(miss_ratio),
        "sparse_logic_reference": bool(sparse_logic_reference),
        "max_expected_pulses": max_expected,
        "detection_ratio": detection_ratio,
        "split_pulses": int(summary.split_pulses),
        "merged_groups": int(summary.merged_groups),
        "extra_output_pulses": int(summary.extra_output_pulses),
        "acquisition_limited_events": int(summary.acquisition_limited_events),
    }
    evidence = [f"{missed}/{expected} physical reference pulses missed downstream"] if matched else []
    rejections = [] if matched else [f"missed pulse gate not met: expected={expected}, missed={missed}, sparse_logic_reference={sparse_logic_reference}"]
    if not frame.empty:
        modes = frame["observed_failure_mode"].value_counts().head(3).to_dict()
        features["failure_mode_count"] = len(modes)
    return ReferenceResult(
        reference_label=label,
        matched=matched,
        confidence=confidence,
        relationship={"type": "physical_pulse_to_observed_output_propagation", "dominant_classification": summary.dominant_classification},
        features=features,
        evidence=evidence,
        rejections=rejections,
    )


def analyze(capture: CaptureRecord) -> SignatureResult:
    capture.validate()
    reference_results = [_reference_score(capture, label, wave) for label, wave in capture.references.items()]
    best = sorted(reference_results, key=lambda r: (not r.matched, -r.confidence, r.reference_label))[0]
    result = SignatureResult(
        signature_id=SIGNATURE_ID,
        matched=bool(best.matched),
        confidence=float(best.confidence),
        best_reference=best.reference_label,
        reference_results=reference_results,
        relationship={**best.relationship, "best_reference": best.reference_label},
        features=best.features,
        evidence=[f"best_reference={best.reference_label}", *best.evidence],
        rejections=best.rejections,
    )
    result.validate()
    return result
