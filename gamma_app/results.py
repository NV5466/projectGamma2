from __future__ import annotations

from dataclasses import asdict
from typing import Any
import json

from gamma_core.runner import CaseRunResult
from gamma_core.schema import SignatureResult

from .threshold_profiles import ThresholdProfile


HIGH_CONFIDENCE_MARGIN = 0.10
MULTI_MATCH_WARNING_MIN = 2


def result_rows(
    case_results: list[CaseRunResult],
    *,
    family_by_signature: dict[str, str],
    threshold_profile: ThresholdProfile,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in case_results:
        ranked_results = _diagnostic_rank(case.results, threshold_profile)
        high_conf_matches = [
            result
            for result, _diagnostic_score, reference_score in ranked_results
            if result.matched and result.confidence >= threshold_profile.threshold_for(result.signature_id) and reference_score > 0.0
        ]
        multi_match_count = len(high_conf_matches)
        primary_signature = high_conf_matches[0].signature_id if high_conf_matches else None
        conflict_warning = _conflict_warning(high_conf_matches)

        for rank, (result, diagnostic_score, reference_score) in enumerate(ranked_results, start=1):
            threshold = threshold_profile.threshold_for(result.signature_id)
            threshold_pass = bool(result.matched and result.confidence >= threshold)
            reference_status = required_reference_status(result)
            is_primary = bool(result.signature_id == primary_signature)
            candidate_role = (
                "primary_diagnosis"
                if is_primary
                else "secondary_candidate"
                if threshold_pass
                else "rejected_or_below_threshold"
            )
            row_warnings = [*result.rejections, *result.errors]
            if conflict_warning and threshold_pass:
                row_warnings.append(conflict_warning)
            if threshold_pass and reference_score <= 0.0:
                row_warnings.append("required_reference_evidence_missing_or_weak")

            rows.append(
                {
                    "capture_id": case.capture_id,
                    "truth_label": case.truth_label,
                    "signature_id": result.signature_id,
                    "family": family_by_signature.get(result.signature_id, "unknown"),
                    "rank": rank,
                    "diagnostic_rank": rank,
                    "diagnostic_score": diagnostic_score,
                    "candidate_role": candidate_role,
                    "primary_diagnosis": primary_signature or "",
                    "secondary_candidates": ",".join(
                        item.signature_id for item in high_conf_matches if item.signature_id != primary_signature
                    ),
                    "multi_match_count": multi_match_count,
                    "multi_match_ambiguity": bool(multi_match_count >= MULTI_MATCH_WARNING_MIN),
                    "raw_matched": bool(result.matched),
                    "threshold_pass": threshold_pass,
                    "confidence": float(result.confidence),
                    "threshold": threshold,
                    "decision": candidate_role,
                    "is_selected": is_primary,
                    "is_primary_diagnosis": is_primary,
                    "best_reference": result.best_reference,
                    "required_reference_status": reference_status,
                    "reference_evidence_score": reference_score,
                    "evidence_summary": summarize_evidence(result.evidence, result.rejections, result.errors),
                    "feature_values_json": json.dumps(_jsonable(result.features), sort_keys=True),
                    "warnings": " | ".join(row_warnings),
                    "conflict_warning": conflict_warning,
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
    by_capture: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_capture.setdefault(str(row["capture_id"]), []).append(row)
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
                "primary_diagnosis": _primary_for_capture(by_capture.get(case.capture_id, [])),
                "secondary_candidates": _secondary_for_capture(by_capture.get(case.capture_id, [])),
                "multi_match_ambiguity": any(row["multi_match_ambiguity"] for row in by_capture.get(case.capture_id, [])),
                "conflict_warnings": sorted(
                    {row["conflict_warning"] for row in by_capture.get(case.capture_id, []) if row["conflict_warning"]}
                ),
                "ranked_signature_ids": case.ranked_signature_ids,
                "results": [_jsonable(asdict(result)) for result in case.results],
            }
            for case in case_results
        ],
    }


def _diagnostic_rank(
    results: list[SignatureResult],
    threshold_profile: ThresholdProfile,
) -> list[tuple[SignatureResult, float, float]]:
    scored = []
    for result in results:
        reference_score = reference_evidence_score(result)
        threshold = threshold_profile.threshold_for(result.signature_id)
        threshold_bonus = 0.05 if result.matched and result.confidence >= threshold else 0.0
        diagnostic_score = max(0.0, min(1.0, float(result.confidence) * (0.70 + 0.30 * reference_score) + threshold_bonus))
        scored.append((result, diagnostic_score, reference_score))
    return sorted(scored, key=lambda item: (item[1], item[0].confidence, item[2]), reverse=True)


def reference_evidence_score(result: SignatureResult) -> float:
    if result.best_reference:
        return 1.0
    if any(ref.matched for ref in result.reference_results):
        return 0.8
    if result.reference_results:
        return 0.25
    return 0.0


def required_reference_status(result: SignatureResult) -> str:
    if result.best_reference:
        return "best_reference_available"
    if any(ref.matched for ref in result.reference_results):
        return "matched_reference_available"
    if result.reference_results:
        return "reference_present_but_weak"
    return "missing_or_not_reported"


def _conflict_warning(high_conf_matches: list[SignatureResult]) -> str:
    if len(high_conf_matches) < MULTI_MATCH_WARNING_MIN:
        return ""
    top = high_conf_matches[0].confidence
    close = [item.signature_id for item in high_conf_matches if top - item.confidence <= HIGH_CONFIDENCE_MARGIN]
    if len(close) >= MULTI_MATCH_WARNING_MIN:
        return "multiple_high_confidence_signatures_match: " + ", ".join(close)
    return "multiple_signatures_match_above_threshold: " + ", ".join(item.signature_id for item in high_conf_matches)


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


def _primary_for_capture(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    primary = [row for row in rows if row["is_primary_diagnosis"]]
    if not primary:
        return None
    row = primary[0]
    return {
        "signature_id": row["signature_id"],
        "family": row["family"],
        "confidence": row["confidence"],
        "diagnostic_score": row["diagnostic_score"],
        "required_reference_status": row["required_reference_status"],
    }


def _secondary_for_capture(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "signature_id": row["signature_id"],
            "family": row["family"],
            "confidence": row["confidence"],
            "diagnostic_score": row["diagnostic_score"],
            "required_reference_status": row["required_reference_status"],
        }
        for row in rows
        if row["candidate_role"] == "secondary_candidate"
    ]


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
