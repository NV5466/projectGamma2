from __future__ import annotations

from dataclasses import asdict
from typing import Any
import json

from gamma_core.runner import CaseRunResult

from .threshold_profiles import ThresholdProfile


def result_rows(
    case_results: list[CaseRunResult],
    *,
    family_by_signature: dict[str, str],
    threshold_profile: ThresholdProfile,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in case_results:
        for rank, result in enumerate(case.results, start=1):
            threshold = threshold_profile.threshold_for(result.signature_id)
            threshold_pass = bool(result.matched and result.confidence >= threshold)
            rows.append(
                {
                    "capture_id": case.capture_id,
                    "truth_label": case.truth_label,
                    "signature_id": result.signature_id,
                    "family": family_by_signature.get(result.signature_id, "unknown"),
                    "rank": rank,
                    "raw_matched": bool(result.matched),
                    "threshold_pass": threshold_pass,
                    "confidence": float(result.confidence),
                    "threshold": threshold,
                    "decision": "matched" if threshold_pass else "no_match",
                    "is_selected": bool(rank == 1 and threshold_pass),
                    "best_reference": result.best_reference,
                    "required_reference_status": "available" if result.best_reference else "not_selected",
                    "evidence_summary": summarize_evidence(result.evidence, result.rejections, result.errors),
                    "feature_values_json": json.dumps(_jsonable(result.features), sort_keys=True),
                    "warnings": " | ".join([*result.rejections, *result.errors]),
                    "recommended_next_check": recommended_next_check(result.signature_id, threshold_pass, result.errors),
                    "threshold_profile": threshold_profile.name,
                }
            )
    return rows


def campaign_json(
    case_results: list[CaseRunResult],
    *,
    family_by_signature: dict[str, str],
    threshold_profile: ThresholdProfile,
    warnings: list[str],
    registry_failures: list[dict[str, str]],
) -> dict[str, Any]:
    rows = result_rows(case_results, family_by_signature=family_by_signature, threshold_profile=threshold_profile)
    selected = [row for row in rows if row["is_selected"]]
    return {
        "total_captures": len(case_results),
        "total_result_rows": len(rows),
        "selected_count": len(selected),
        "threshold_profile": threshold_profile.to_dict(),
        "warnings": warnings,
        "registry_failures": registry_failures,
        "captures": [
            {
                "capture_id": case.capture_id,
                "truth_label": case.truth_label,
                "core_winner": case.winner,
                "core_decision": case.decision,
                "ranked_signature_ids": case.ranked_signature_ids,
                "results": [_jsonable(asdict(result)) for result in case.results],
            }
            for case in case_results
        ],
    }


def summarize_evidence(evidence: list[str], rejections: list[str], errors: list[str]) -> str:
    parts = []
    if evidence:
        parts.append("; ".join(map(str, evidence[:3])))
    if rejections:
        parts.append("Rejected: " + "; ".join(map(str, rejections[:3])))
    if errors:
        parts.append("Errors: " + "; ".join(map(str, errors[:2])))
    return " | ".join(parts)


def recommended_next_check(signature_id: str, matched: bool, errors: list[str]) -> str:
    if errors:
        return "Review analyzer runtime error and capture schema before interpreting this result."
    if not matched:
        return "Treat as weak/no evidence; verify channel mapping, reference channel, and capture duration."
    recommendations = {
        "relay_coil_inductive_kick": "Check relay coil suppression path, clamp/snubber condition, and victim-channel coupling.",
        "high_speed_input_bounce": "Inspect digital input wiring, debounce/filter settings, and clustered transition timing.",
        "missed_short_pulse": "Check input scan/filter bandwidth, pulse width margin, and reference pulse timing.",
    }
    return recommendations.get(signature_id, "Review waveform, reference channel, and seed-specific evidence before action.")


def _jsonable(value: Any) -> Any:
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value
