from __future__ import annotations

from pathlib import Path
from typing import Iterable
import json

import pandas as pd


THRESHOLD_COLUMNS = [
    "signature_id",
    "threshold",
    "total_cases",
    "truth_cases",
    "TP",
    "FP",
    "TN",
    "FN",
    "TPR",
    "FPR",
    "precision",
    "recall",
    "F1",
    "Youden_J",
    "accuracy",
    "deployable",
    "min_required_TPR",
    "max_allowed_FPR",
]

DEPLOYABLE_COLUMNS = [
    "signature_id",
    "selected_threshold",
    "TPR",
    "FPR",
    "precision",
    "F1",
    "Youden_J",
    "TP",
    "FP",
    "TN",
    "FN",
]


def default_thresholds() -> list[float]:
    return [round(i / 100.0, 2) for i in range(5, 100, 5)]


def _safe_div(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _load_campaign_metadata(campaign_dir: Path) -> tuple[list[str], list[dict[str, str]]]:
    summary_path = campaign_dir / "campaign_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"missing required input: {summary_path}")
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    signatures = [str(item) for item in data.get("signatures_loaded", [])]
    failures = data.get("signatures_failed_to_load", [])
    if not isinstance(failures, list):
        failures = []
    return signatures, failures


def _load_signature_summary(campaign_dir: Path) -> list[str]:
    summary_path = campaign_dir / "signature_summary.csv"
    if not summary_path.exists():
        raise FileNotFoundError(f"missing required input: {summary_path}")
    frame = pd.read_csv(summary_path)
    if "signature_id" not in frame.columns:
        raise ValueError(f"{summary_path} must contain signature_id")
    return [str(item) for item in frame["signature_id"].dropna().tolist()]


def load_campaign_scores(campaign_dir: str | Path) -> tuple[pd.DataFrame, list[str], list[dict[str, str]]]:
    campaign_path = Path(campaign_dir)
    scores_path = campaign_path / "per_case_signature_scores.csv"
    if not scores_path.exists():
        raise FileNotFoundError(f"missing required input: {scores_path}")

    scores = pd.read_csv(scores_path)
    required = {"capture_id", "truth_label", "signature_id", "confidence"}
    missing = sorted(required - set(scores.columns))
    if missing:
        raise ValueError(f"{scores_path} missing required columns: {missing}")
    if not scores["truth_label"].astype(str).str.len().any():
        raise ValueError("threshold evaluation requires truth_label values")

    loaded_signatures, failures = _load_campaign_metadata(campaign_path)
    summary_signatures = _load_signature_summary(campaign_path)
    signatures = loaded_signatures or summary_signatures or sorted(scores["signature_id"].dropna().astype(str).unique().tolist())

    scores = scores.copy()
    scores["signature_id"] = scores["signature_id"].astype(str)
    scores["truth_label"] = scores["truth_label"].astype(str)
    scores["confidence"] = pd.to_numeric(scores["confidence"], errors="coerce").fillna(0.0)
    return scores, signatures, failures


def evaluate_thresholds(
    scores: pd.DataFrame,
    signatures: Iterable[str],
    thresholds: Iterable[float],
    *,
    min_required_tpr: float,
    max_allowed_fpr: float,
) -> pd.DataFrame:
    rows = []
    total_cases = int(scores["capture_id"].nunique())
    for signature_id in signatures:
        sig_frame = scores[scores["signature_id"] == signature_id]
        if sig_frame.empty:
            continue
        truth_mask = sig_frame["truth_label"] == signature_id
        truth_cases = int(truth_mask.sum())
        for threshold in thresholds:
            threshold = float(threshold)
            positive = sig_frame["confidence"] >= threshold
            tp = int((positive & truth_mask).sum())
            fp = int((positive & ~truth_mask).sum())
            tn = int((~positive & ~truth_mask).sum())
            fn = int((~positive & truth_mask).sum())

            tpr = _safe_div(tp, tp + fn)
            fpr = _safe_div(fp, fp + tn)
            precision = _safe_div(tp, tp + fp)
            f1 = _safe_div(2 * precision * tpr, precision + tpr)
            accuracy = _safe_div(tp + tn, tp + fp + tn + fn)
            deployable = bool(tpr >= min_required_tpr and fpr <= max_allowed_fpr)
            rows.append(
                {
                    "signature_id": signature_id,
                    "threshold": threshold,
                    "total_cases": total_cases,
                    "truth_cases": truth_cases,
                    "TP": tp,
                    "FP": fp,
                    "TN": tn,
                    "FN": fn,
                    "TPR": tpr,
                    "FPR": fpr,
                    "precision": precision,
                    "recall": tpr,
                    "F1": f1,
                    "Youden_J": tpr - fpr,
                    "accuracy": accuracy,
                    "deployable": deployable,
                    "min_required_TPR": float(min_required_tpr),
                    "max_allowed_FPR": float(max_allowed_fpr),
                }
            )
    return pd.DataFrame(rows, columns=THRESHOLD_COLUMNS)


def select_deployable_thresholds(threshold_results: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if threshold_results.empty:
        return pd.DataFrame(columns=DEPLOYABLE_COLUMNS)

    deployable = threshold_results[threshold_results["deployable"] == True]  # noqa: E712
    for signature_id, frame in deployable.groupby("signature_id", sort=True):
        selected = frame.sort_values(["threshold", "Youden_J", "F1"], ascending=[False, False, False]).iloc[0]
        rows.append(
            {
                "signature_id": signature_id,
                "selected_threshold": float(selected["threshold"]),
                "TPR": float(selected["TPR"]),
                "FPR": float(selected["FPR"]),
                "precision": float(selected["precision"]),
                "F1": float(selected["F1"]),
                "Youden_J": float(selected["Youden_J"]),
                "TP": int(selected["TP"]),
                "FP": int(selected["FP"]),
                "TN": int(selected["TN"]),
                "FN": int(selected["FN"]),
            }
        )
    return pd.DataFrame(rows, columns=DEPLOYABLE_COLUMNS)


def write_threshold_outputs(
    campaign_dir: str | Path,
    *,
    thresholds: Iterable[float] | None = None,
    min_required_tpr: float = 0.90,
    max_allowed_fpr: float = 0.05,
    out: str | Path | None = None,
    deployable_out: str | Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    campaign_path = Path(campaign_dir)
    scores, signatures, _failures = load_campaign_scores(campaign_path)
    threshold_results = evaluate_thresholds(
        scores,
        signatures,
        thresholds or default_thresholds(),
        min_required_tpr=min_required_tpr,
        max_allowed_fpr=max_allowed_fpr,
    )
    deployable = select_deployable_thresholds(threshold_results)

    out_path = Path(out) if out else campaign_path / "threshold_evaluation.csv"
    deployable_path = Path(deployable_out) if deployable_out else out_path.with_name("deployable_thresholds.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    deployable_path.parent.mkdir(parents=True, exist_ok=True)
    threshold_results.to_csv(out_path, index=False)
    deployable.to_csv(deployable_path, index=False)
    return threshold_results, deployable
