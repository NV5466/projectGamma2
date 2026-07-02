from __future__ import annotations

from itertools import combinations
from typing import Any
import json
import math

import pandas as pd

from .runner import CaseRunResult


def _json_dict(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _numeric_feature_items(features: dict[str, Any]):
    for key, value in features.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            yield key, float(value)


def build_per_case_rows(case_results: list[CaseRunResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in case_results:
        for rank, result in enumerate(case.results, start=1):
            truth = case.truth_label
            has_truth = bool(truth)
            is_truth = result.signature_id == truth if has_truth else ""
            matched = bool(result.matched)
            row: dict[str, Any] = {
                "capture_id": case.capture_id,
                "truth_label": truth or "",
                "signature_id": result.signature_id,
                "matched": matched,
                "confidence": float(result.confidence),
                "rank": rank,
                "winner": case.winner or "",
                "decision": case.decision,
                "is_winner": result.signature_id == case.winner,
                "best_reference": result.best_reference or "",
                "reference_count": len(result.reference_results),
                "is_truth_signature": is_truth,
                "is_true_positive": matched and is_truth if has_truth else "",
                "is_false_positive": matched and not is_truth if has_truth else "",
                "is_true_negative": (not matched) and not is_truth if has_truth else "",
                "is_false_negative": (not matched) and is_truth if has_truth else "",
                "primary_event_time_s": result.primary_events[0].time_s if result.primary_events else "",
                "evidence_count": len(result.evidence),
                "rejection_count": len(result.rejections),
                "error_count": len(result.errors),
                "evidence_text": " | ".join(map(str, result.evidence)),
                "rejection_text": " | ".join(map(str, result.rejections)),
                "error_text": " | ".join(map(str, result.errors)),
                "relationship_json": _json_dict(result.relationship),
                "features_json": _json_dict(result.features),
            }
            for key, value in _numeric_feature_items(result.features):
                row[f"feature.{key}"] = value
            rows.append(row)
    return rows


def build_reference_rows(case_results: list[CaseRunResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in case_results:
        rank_by_signature = {r.signature_id: i for i, r in enumerate(case.results, start=1)}
        for result in case.results:
            rank = rank_by_signature[result.signature_id]
            for ref in result.reference_results:
                row: dict[str, Any] = {
                    "capture_id": case.capture_id,
                    "truth_label": case.truth_label or "",
                    "signature_id": result.signature_id,
                    "reference_label": ref.reference_label,
                    "signature_matched": bool(result.matched),
                    "reference_matched": bool(ref.matched),
                    "signature_confidence": float(result.confidence),
                    "reference_confidence": float(ref.confidence),
                    "is_best_reference": ref.reference_label == result.best_reference,
                    "winner": case.winner or "",
                    "rank": rank,
                    "relationship_json": _json_dict(ref.relationship),
                    "features_json": _json_dict(ref.features),
                    "evidence_count": len(ref.evidence),
                    "rejection_count": len(ref.rejections),
                    "evidence_text": " | ".join(map(str, ref.evidence)),
                    "rejection_text": " | ".join(map(str, ref.rejections)),
                }
                for key, value in _numeric_feature_items(ref.features):
                    row[f"ref_feature.{key}"] = value
                rows.append(row)
    return rows


def build_signature_summary(per_case_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    has_truth = "is_true_positive" in per_case_df.columns and per_case_df["truth_label"].astype(bool).any()
    for signature_id, frame in per_case_df.groupby("signature_id", sort=True):
        confidences = frame["confidence"].astype(float)
        base = {
            "signature_id": signature_id,
            "total_cases": int(len(frame)),
            "matched_count": int(frame["matched"].astype(bool).sum()),
            "top1_count": int(frame["is_winner"].astype(bool).sum()),
            "mean_confidence": float(confidences.mean()) if len(frame) else 0.0,
            "median_confidence": float(confidences.median()) if len(frame) else 0.0,
            "p05_confidence": float(confidences.quantile(0.05)) if len(frame) else 0.0,
            "p95_confidence": float(confidences.quantile(0.95)) if len(frame) else 0.0,
            "mean_rank": float(frame["rank"].astype(float).mean()) if len(frame) else 0.0,
            "error_count": int(frame["error_count"].astype(int).sum()),
        }
        if has_truth:
            tp = int((frame["is_true_positive"] == True).sum())  # noqa: E712
            fp = int((frame["is_false_positive"] == True).sum())  # noqa: E712
            tn = int((frame["is_true_negative"] == True).sum())  # noqa: E712
            fn = int((frame["is_false_negative"] == True).sum())  # noqa: E712
            base.update(
                {
                    "truth_cases": tp + fn,
                    "tp": tp,
                    "fp": fp,
                    "tn": tn,
                    "fn": fn,
                    "recall": tp / (tp + fn) if tp + fn else "",
                    "precision": tp / (tp + fp) if tp + fp else "",
                    "false_positive_rate": fp / (fp + tn) if fp + tn else "",
                    "specificity": tn / (tn + fp) if tn + fp else "",
                    "accuracy": (tp + tn) / (tp + fp + tn + fn) if tp + fp + tn + fn else "",
                }
            )
        else:
            base.update(
                {
                    "match_rate": base["matched_count"] / base["total_cases"] if base["total_cases"] else 0.0,
                    "top1_rate": base["top1_count"] / base["total_cases"] if base["total_cases"] else 0.0,
                }
            )
        rows.append(base)
    return pd.DataFrame(rows)


def build_reference_summary(reference_df: pd.DataFrame) -> pd.DataFrame:
    if reference_df.empty:
        return pd.DataFrame()
    rows = []
    for (signature_id, reference_label), frame in reference_df.groupby(["signature_id", "reference_label"], sort=True):
        total = len(frame)
        rows.append(
            {
                "signature_id": signature_id,
                "reference_label": reference_label,
                "total_cases": total,
                "reference_matched_count": int(frame["reference_matched"].astype(bool).sum()),
                "reference_match_rate": float(frame["reference_matched"].astype(bool).mean()) if total else 0.0,
                "best_reference_count": int(frame["is_best_reference"].astype(bool).sum()),
                "best_reference_rate": float(frame["is_best_reference"].astype(bool).mean()) if total else 0.0,
                "mean_reference_confidence": float(frame["reference_confidence"].astype(float).mean()) if total else 0.0,
                "median_reference_confidence": float(frame["reference_confidence"].astype(float).median()) if total else 0.0,
            }
        )
    return pd.DataFrame(rows)


def build_confusion_matrix(case_results: list[CaseRunResult]) -> pd.DataFrame:
    if not any(case.truth_label for case in case_results):
        return pd.DataFrame()
    rows = []
    for case in case_results:
        rows.append({"truth": case.truth_label or "", "pred": f"pred_{case.winner or 'none'}"})
    frame = pd.DataFrame(rows)
    return pd.crosstab(frame["truth"], frame["pred"]).reset_index()


def build_overlap_matrix(per_case_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    signatures = sorted(per_case_df["signature_id"].unique())
    for sig_a, sig_b in combinations(signatures, 2):
        a = per_case_df[per_case_df["signature_id"] == sig_a].set_index("capture_id")
        b = per_case_df[per_case_df["signature_id"] == sig_b].set_index("capture_id")
        joined = a[["matched", "confidence"]].join(b[["matched", "confidence"]], lsuffix="_a", rsuffix="_b")
        both = joined["matched_a"].astype(bool) & joined["matched_b"].astype(bool)
        a_only = joined["matched_a"].astype(bool) & ~joined["matched_b"].astype(bool)
        b_only = ~joined["matched_a"].astype(bool) & joined["matched_b"].astype(bool)
        neither = ~joined["matched_a"].astype(bool) & ~joined["matched_b"].astype(bool)
        denom = int(a_only.sum() + b_only.sum() + both.sum())
        rows.append(
            {
                "signature_a": sig_a,
                "signature_b": sig_b,
                "total_cases": int(len(joined)),
                "both_matched": int(both.sum()),
                "a_only": int(a_only.sum()),
                "b_only": int(b_only.sum()),
                "neither": int(neither.sum()),
                "overlap_rate": float(both.mean()) if len(joined) else 0.0,
                "jaccard_overlap": int(both.sum()) / denom if denom else 0.0,
                "mean_confidence_a_when_both": float(joined.loc[both, "confidence_a"].mean()) if both.any() else "",
                "mean_confidence_b_when_both": float(joined.loc[both, "confidence_b"].mean()) if both.any() else "",
            }
        )
    return pd.DataFrame(rows)


def build_feature_stats(per_case_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    feature_cols = [c for c in per_case_df.columns if c.startswith("feature.")]
    for signature_id, frame in per_case_df.groupby("signature_id", sort=True):
        for col in feature_cols:
            series = pd.to_numeric(frame[col], errors="coerce").dropna()
            if series.empty:
                continue
            rows.append(
                {
                    "signature_id": signature_id,
                    "feature": col.removeprefix("feature."),
                    "count": int(series.count()),
                    "mean": float(series.mean()),
                    "std": float(series.std(ddof=0)),
                    "min": float(series.min()),
                    "p05": float(series.quantile(0.05)),
                    "p25": float(series.quantile(0.25)),
                    "p50": float(series.quantile(0.50)),
                    "p75": float(series.quantile(0.75)),
                    "p95": float(series.quantile(0.95)),
                    "max": float(series.max()),
                }
            )
    return pd.DataFrame(rows)
