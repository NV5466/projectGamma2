from __future__ import annotations

import numpy as np

from gamma_core.schema import CaptureRecord, ReferenceResult, SignatureResult

SIGNATURE_ID = "high_speed_input_bounce"


def _segments(mask: np.ndarray) -> int:
    if mask.size == 0:
        return 0
    return int(mask[0]) + int(np.count_nonzero((~mask[:-1]) & mask[1:]))


def _reference_score(capture: CaptureRecord, label: str, reference: np.ndarray) -> ReferenceResult:
    primary = np.asarray(capture.primary, dtype=float)
    ref = np.asarray(reference, dtype=float)
    sample_rate = float(capture.sample_rate_hz)

    ref_centered = ref - np.median(ref)
    primary_centered = primary - np.median(primary)
    ref_peak_idx = int(np.argmax(np.abs(ref_centered)))
    event_time = float(capture.time_s[ref_peak_idx])
    window = max(4, int(round(1.2e-6 * sample_rate)))
    start = max(0, ref_peak_idx - window // 4)
    stop = min(len(primary), ref_peak_idx + window)
    off_mask = np.ones(len(primary), dtype=bool)
    off_mask[start:stop] = False
    local = primary_centered[start:stop]
    off = primary_centered[off_mask]

    local_rms = float(np.sqrt(np.mean(local * local))) if local.size else 0.0
    off_rms = float(np.sqrt(np.mean(off * off))) if off.size else 0.0
    localization_ratio = local_rms / (off_rms + 1e-12)
    peak = float(np.max(np.abs(local))) if local.size else 0.0
    threshold = max(1e-9, 0.45 * peak)
    threshold_segments = _segments(np.abs(local) > threshold)
    zero_crossings = int(np.count_nonzero(local[:-1] * local[1:] < 0.0)) if local.size > 1 else 0

    confidence = float(np.clip(0.28 * min(localization_ratio / 6.0, 1.0) + 0.34 * min(peak / 2.5, 1.0) + 0.18 * min(threshold_segments / 3.0, 1.0) + 0.20 * min(zero_crossings / 8.0, 1.0), 0.0, 1.0))
    matched = bool(confidence >= 0.70 and localization_ratio > 1.25 and (threshold_segments >= 1 or zero_crossings >= 1))
    features = {
        "event_time_s": event_time,
        "recovered_peak_v": peak,
        "recovered_rms_v": local_rms,
        "off_event_rms_v": off_rms,
        "localization_ratio": localization_ratio,
        "threshold_segments": threshold_segments,
        "zero_crossings": zero_crossings,
    }
    evidence = ["localized transient after repeated input reference"] if matched else []
    rejections = [] if matched else ["single-capture HSIB evidence below conservative v0.1 gate"]
    return ReferenceResult(
        reference_label=label,
        matched=matched,
        confidence=confidence,
        relationship={"type": "localized_transient_after_reference_event", "event_time_s": event_time},
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
