from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import argparse
import csv
import json
import math

import numpy as np
import pandas as pd

from .registry import ALLOWED_FAMILIES, is_mechanical_only_id
from .threshold_profiles import ThresholdProfile, load_threshold_profile, save_threshold_profile


SPLIT_NAMES = ("train", "dev", "test")
SPLIT_PURPOSES = {
    "train": "tune/dev",
    "dev": "validation/model-selection",
    "test": "locked_test",
}
DEFAULT_SPLIT_RATIOS = (0.60, 0.20, 0.20)
DEFAULT_OBJECTIVE = "balanced_default"
OBJECTIVE_NAMES = {
    "balanced_default",
    "conservative_precision",
    "sensitive_fault_finding",
    "field_triage",
}
METRIC_COLUMNS = [
    "total_cases",
    "positives",
    "negatives",
    "TP",
    "FP",
    "TN",
    "FN",
    "accuracy",
    "precision",
    "recall",
    "sensitivity",
    "specificity",
    "balanced_accuracy",
    "F1",
    "false_positive_rate",
    "false_negative_rate",
]


@dataclass(frozen=True)
class ProfileRun:
    name: str
    profile: ThresholdProfile
    per_case_rows: list[dict[str, Any]]
    overall_metrics: dict[str, Any]
    split_metrics: dict[str, dict[str, Any]]
    per_analyzer_rows: list[dict[str, Any]]
    per_waveform_intent_rows: list[dict[str, Any]]
    per_noise_tier_rows: list[dict[str, Any]]
    bootstrap_rows: list[dict[str, Any]]


def parse_ratio_list(value: str | None) -> tuple[float, float, float]:
    if not value:
        return DEFAULT_SPLIT_RATIOS
    parts = [float(item.strip()) for item in value.split(",") if item.strip()]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("split ratios must contain exactly three values")
    if any(part < 0 for part in parts):
        raise argparse.ArgumentTypeError("split ratios must be non-negative")
    total = sum(parts)
    if not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise argparse.ArgumentTypeError("split ratios must sum to 1.0")
    return float(parts[0]), float(parts[1]), float(parts[2])


def resolve_profile_path(path: str | Path | None) -> Path:
    if path is None:
        from .runtime import default_threshold_profile_path

        return default_threshold_profile_path()
    candidate = Path(path)
    if candidate.exists():
        return candidate
    if candidate.name in {"default.yaml", "default_thresholds.yaml"}:
        fallback = Path("configs/default_thresholds.yaml")
        if fallback.exists():
            return fallback
    raise FileNotFoundError(f"threshold profile not found: {candidate}")


def load_manifest_table(manifest_path: str | Path) -> pd.DataFrame:
    path = Path(manifest_path)
    frame = pd.read_csv(path, keep_default_na=False)
    required = {"capture_id", "signature_id", "family", "truth_label", "expected_fault_present", "noise_tier"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{path} missing required columns: {missing}")

    frame = frame.copy()
    frame["capture_id"] = frame["capture_id"].astype(str)
    frame["signature_id"] = frame["signature_id"].astype(str)
    frame["family"] = frame["family"].astype(str)
    frame["truth_label"] = frame["truth_label"].astype(str)
    frame["noise_tier"] = frame["noise_tier"].astype(str)
    frame["expected_fault_present"] = frame["expected_fault_present"].map(_to_bool)
    if "waveform_intent" not in frame.columns:
        frame["waveform_intent"] = frame["variant"] if "variant" in frame.columns else frame["truth_label"]
    if "split" in frame.columns:
        frame["split"] = frame["split"].astype(str)
    validate_manifest_signatures(frame)
    return frame


def load_results_table(results_path: str | Path) -> pd.DataFrame:
    path = Path(results_path)
    if path.is_dir():
        for candidate in (path / "campaign_results.csv", path / "per_case_signature_scores.csv"):
            if candidate.exists():
                path = candidate
                break
        else:
            raise FileNotFoundError(f"missing campaign results CSV in {path}")
    frame = pd.read_csv(path, keep_default_na=False)
    required = {"capture_id", "signature_id", "confidence"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{path} missing required columns: {missing}")
    frame = frame.copy()
    frame["capture_id"] = frame["capture_id"].astype(str)
    frame["signature_id"] = frame["signature_id"].astype(str)
    frame["confidence"] = pd.to_numeric(frame["confidence"], errors="coerce").fillna(0.0)
    if "raw_matched" in frame.columns:
        frame["raw_matched"] = frame["raw_matched"].map(_to_bool)
    elif "matched" in frame.columns:
        frame["raw_matched"] = frame["matched"].map(_to_bool)
    else:
        frame["raw_matched"] = True
    if "reference_evidence_score" in frame.columns:
        frame["reference_evidence_score"] = pd.to_numeric(frame["reference_evidence_score"], errors="coerce").fillna(0.0)
    else:
        frame["reference_evidence_score"] = 1.0
    if "rank" not in frame.columns:
        frame["rank"] = frame.groupby("capture_id")["confidence"].rank(method="first", ascending=False)
    frame["rank"] = pd.to_numeric(frame["rank"], errors="coerce").fillna(0).astype(int)
    if "threshold_profile" not in frame.columns:
        frame["threshold_profile"] = "unknown"
    if "warnings" not in frame.columns:
        frame["warnings"] = ""
    if "conflict_warning" not in frame.columns:
        frame["conflict_warning"] = ""
    return frame


def validate_manifest_signatures(frame: pd.DataFrame) -> None:
    invalid = [str(signature_id) for signature_id in frame["signature_id"].astype(str).unique().tolist() if is_mechanical_only_id(str(signature_id))]
    if invalid:
        raise ValueError(f"manifest contains mechanical-only signatures: {sorted(invalid)}")


def stratified_split_manifest(
    frame: pd.DataFrame,
    *,
    seed: int,
    ratios: tuple[float, float, float] = DEFAULT_SPLIT_RATIOS,
    split_names: tuple[str, str, str] = SPLIT_NAMES,
) -> pd.DataFrame:
    if len(split_names) != 3:
        raise ValueError("split_names must contain exactly three entries")
    frame = frame.copy()
    strata_cols = ["signature_id", "family", "truth_label", "expected_fault_present", "noise_tier"]
    if "test_id" in frame.columns:
        strata_cols.append("test_id")
    if "waveform_intent" in frame.columns and "variant" not in frame.columns:
        strata_cols.append("waveform_intent")
    rng = np.random.default_rng(seed)
    assignments = pd.Series(index=frame.index, dtype="object")
    bucket_ids = []
    for bucket_index, (_, bucket) in enumerate(frame.groupby(strata_cols, sort=True)):
        shuffled = bucket.index.to_numpy(copy=True)
        rng.shuffle(shuffled)
        counts = _allocate_counts(len(shuffled), ratios)
        offset = 0
        for split_name, count in zip(split_names, counts):
            chosen = shuffled[offset : offset + count]
            assignments.loc[chosen] = split_name
            bucket_ids.extend([(idx, bucket_index) for idx in chosen])
            offset += count
    if assignments.isna().any():
        raise RuntimeError("failed to assign every capture to a split")
    frame["split"] = assignments.astype(str)
    frame["split_purpose"] = frame["split"].map(SPLIT_PURPOSES)
    frame["split_bucket"] = ""
    for idx, bucket_index in bucket_ids:
        frame.at[idx, "split_bucket"] = str(bucket_index)
    return frame


def evaluate_profile_runs(
    manifest: pd.DataFrame,
    results_by_capture: dict[str, pd.DataFrame],
    profile: ThresholdProfile,
) -> ProfileRun:
    per_case_rows: list[dict[str, Any]] = []
    for row in manifest.itertuples(index=False):
        capture_id = str(row.capture_id)
        capture_rows = results_by_capture.get(capture_id, pd.DataFrame())
        per_case_rows.append(_evaluate_capture(row._asdict(), capture_rows, profile))

    overall_metrics = compute_metrics(per_case_rows)
    split_metrics = {
        split: compute_metrics([row for row in per_case_rows if row["split"] == split])
        for split in sorted({row["split"] for row in per_case_rows})
    }
    per_analyzer_rows = aggregate_rows(per_case_rows, group_key="signature_id", profile_name=profile.name)
    per_waveform_intent_rows = aggregate_rows(per_case_rows, group_key="waveform_intent", profile_name=profile.name)
    per_noise_tier_rows = aggregate_rows(per_case_rows, group_key="noise_tier", profile_name=profile.name)
    bootstrap_rows = bootstrap_confidence_intervals(per_case_rows, profile.name)
    return ProfileRun(
        name=profile.name,
        profile=profile,
        per_case_rows=per_case_rows,
        overall_metrics=overall_metrics,
        split_metrics=split_metrics,
        per_analyzer_rows=per_analyzer_rows,
        per_waveform_intent_rows=per_waveform_intent_rows,
        per_noise_tier_rows=per_noise_tier_rows,
        bootstrap_rows=bootstrap_rows,
    )


def compare_profiles(
    baseline: ProfileRun,
    tuned: ProfileRun,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split in sorted(set(baseline.split_metrics) | set(tuned.split_metrics)):
        base_metrics = baseline.split_metrics.get(split, {})
        tuned_metrics = tuned.split_metrics.get(split, {})
        for metric in ["accuracy", "precision", "recall", "specificity", "balanced_accuracy", "F1", "false_positive_rate", "false_negative_rate"]:
            base_value = float(base_metrics.get(metric, 0.0))
            tuned_value = float(tuned_metrics.get(metric, 0.0))
            rows.append(
                {
                    "split": split,
                    "metric": metric,
                    "baseline_profile": baseline.name,
                    "tuned_profile": tuned.name,
                    "baseline": base_value,
                    "tuned": tuned_value,
                    "delta": tuned_value - base_value,
                }
            )
    return rows


def build_split_summary(
    manifest: pd.DataFrame,
    baseline: ProfileRun,
    tuned: ProfileRun,
    *,
    objective_name: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    dev_row: dict[str, Any] | None = None
    for split in ["train", "dev", "test"]:
        split_frame = manifest[manifest["split"] == split]
        if split_frame.empty:
            continue
        base_metrics = baseline.split_metrics.get(split, {})
        tuned_metrics = tuned.split_metrics.get(split, {})
        rows.append(
            {
                "split": split,
                "purpose": SPLIT_PURPOSES.get(split, ""),
                "total_cases": int(len(split_frame)),
                "positives": int(split_frame["expected_fault_present"].sum()),
                "negatives": int((~split_frame["expected_fault_present"]).sum()),
                "signatures": int(split_frame["signature_id"].nunique()),
                "families": int(split_frame["family"].nunique()),
                "normal_noise_cases": int((split_frame["noise_tier"] == "normal").sum()),
                "high_noise_cases": int((split_frame["noise_tier"] == "high").sum()),
                "baseline_accuracy": float(base_metrics.get("accuracy", 0.0)),
                "tuned_accuracy": float(tuned_metrics.get("accuracy", 0.0)),
                "baseline_precision": float(base_metrics.get("precision", 0.0)),
                "tuned_precision": float(tuned_metrics.get("precision", 0.0)),
                "baseline_recall": float(base_metrics.get("recall", 0.0)),
                "tuned_recall": float(tuned_metrics.get("recall", 0.0)),
                "baseline_specificity": float(base_metrics.get("specificity", 0.0)),
                "tuned_specificity": float(tuned_metrics.get("specificity", 0.0)),
                "baseline_balanced_accuracy": float(base_metrics.get("balanced_accuracy", 0.0)),
                "tuned_balanced_accuracy": float(tuned_metrics.get("balanced_accuracy", 0.0)),
                "objective_name": objective_name,
                "objective_score_baseline": objective_score(base_metrics, objective_name, conflict_rate=float(base_metrics.get("conflict_rate", 0.0))),
                "objective_score_tuned": objective_score(tuned_metrics, objective_name, conflict_rate=float(tuned_metrics.get("conflict_rate", 0.0))),
            }
        )
        if split == "dev":
            dev_row = rows[-1]
    if dev_row:
        recommended = "tuned" if dev_row["objective_score_tuned"] >= dev_row["objective_score_baseline"] else "baseline"
        for row in rows:
            row["recommended_profile"] = recommended
    return rows


def build_threshold_ablation_rows(
    manifest: pd.DataFrame,
    results_by_capture: dict[str, pd.DataFrame],
    baseline_profile: ThresholdProfile,
    tuned_profile: ThresholdProfile,
    tuned_run: ProfileRun,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    changed_signatures = sorted(
        sig
        for sig in set(baseline_profile.signature_thresholds) | set(tuned_profile.signature_thresholds)
        if abs(float(tuned_profile.threshold_for(sig)) - float(baseline_profile.threshold_for(sig))) > 1e-12
    )
    for signature_id in changed_signatures:
        ablated = ThresholdProfile(
            name=f"{tuned_profile.name}__ablated__{signature_id}",
            based_on=tuned_profile.name,
            created_for=tuned_profile.created_for,
            default_threshold=tuned_profile.default_threshold,
            signature_thresholds=dict(tuned_profile.signature_thresholds),
            notes=[*tuned_profile.notes, f"Reverted {signature_id} to baseline threshold for ablation analysis."],
            baseline_metrics=dict(tuned_profile.baseline_metrics),
            tuned_metrics=dict(tuned_profile.tuned_metrics),
            source_path=tuned_profile.source_path,
        )
        ablated.signature_thresholds[signature_id] = float(baseline_profile.threshold_for(signature_id))
        ablated_run = evaluate_profile_runs(manifest, results_by_capture, ablated)
        for split in ["train", "dev", "test"]:
            tuned_metrics = tuned_run.split_metrics.get(split, {})
            ablated_metrics = ablated_run.split_metrics.get(split, {})
            row = {
                "signature_id": signature_id,
                "split": split,
                "baseline_threshold": float(baseline_profile.threshold_for(signature_id)),
                "tuned_threshold": float(tuned_profile.threshold_for(signature_id)),
                "ablated_threshold": float(ablated.threshold_for(signature_id)),
            }
            for metric in ["accuracy", "precision", "recall", "specificity", "balanced_accuracy", "F1", "false_positive_rate", "false_negative_rate", "FP", "FN"]:
                row[f"tuned_{metric}"] = float(tuned_metrics.get(metric, 0.0))
                row[f"ablated_{metric}"] = float(ablated_metrics.get(metric, 0.0))
                row[f"delta_{metric}"] = float(ablated_metrics.get(metric, 0.0)) - float(tuned_metrics.get(metric, 0.0))
            row["helped_accuracy"] = row["delta_accuracy"] > 0
            row["helped_precision"] = row["delta_precision"] > 0
            row["helped_recall"] = row["delta_recall"] > 0
            row["helped_specificity"] = row["delta_specificity"] > 0
            row["helped_balanced_accuracy"] = row["delta_balanced_accuracy"] > 0
            rows.append(row)
    return rows


def build_overfit_diagnostics(
    manifest: pd.DataFrame,
    baseline: ProfileRun,
    tuned: ProfileRun,
    bootstrap_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    baseline_dev = baseline.split_metrics.get("dev", {})
    tuned_dev = tuned.split_metrics.get("dev", {})
    baseline_test = baseline.split_metrics.get("test", {})
    tuned_test = tuned.split_metrics.get("test", {})

    if tuned_dev.get("balanced_accuracy", 0.0) > baseline_dev.get("balanced_accuracy", 0.0) and tuned_test.get("balanced_accuracy", 0.0) < baseline_test.get("balanced_accuracy", 0.0):
        rows.append(
            {
                "diagnostic": "dev_improvement_not_transferred",
                "severity": "warning",
                "split": "test",
                "metric": "balanced_accuracy",
                "baseline": float(baseline_test.get("balanced_accuracy", 0.0)),
                "tuned": float(tuned_test.get("balanced_accuracy", 0.0)),
                "delta": float(tuned_test.get("balanced_accuracy", 0.0)) - float(baseline_test.get("balanced_accuracy", 0.0)),
                "details": "tuned profile improved dev balanced accuracy but worsened locked-test balanced accuracy",
            }
        )

    if tuned_test.get("recall", 0.0) >= baseline_test.get("recall", 0.0) and tuned_test.get("precision", 0.0) + 0.03 < baseline_test.get("precision", 0.0):
        rows.append(
            {
                "diagnostic": "recall_gain_with_precision_collapse",
                "severity": "warning",
                "split": "test",
                "metric": "precision",
                "baseline": float(baseline_test.get("precision", 0.0)),
                "tuned": float(tuned_test.get("precision", 0.0)),
                "delta": float(tuned_test.get("precision", 0.0)) - float(baseline_test.get("precision", 0.0)),
                "details": "recall improved or held steady while precision dropped materially on locked test",
            }
        )

    test_case_rows = [row for row in tuned.per_case_rows if row["split"] == "test"]
    fp_rows = [row for row in test_case_rows if row["is_false_positive"]]
    fn_rows = [row for row in test_case_rows if row["is_false_negative"]]
    if fp_rows:
        fp_counts = pd.DataFrame(fp_rows).groupby("predicted_primary_signature").size().sort_values(ascending=False)
        top_sig = str(fp_counts.index[0])
        share = float(fp_counts.iloc[0]) / float(fp_counts.sum())
        if share >= 0.30:
            rows.append(
                {
                    "diagnostic": "single_analyzer_dominates_false_positives",
                    "severity": "warning",
                    "split": "test",
                    "metric": "false_positives",
                    "baseline": float(baseline_test.get("FP", 0.0)),
                    "tuned": float(tuned_test.get("FP", 0.0)),
                    "delta": float(tuned_test.get("FP", 0.0)) - float(baseline_test.get("FP", 0.0)),
                    "details": f"{top_sig} accounts for {share:.1%} of locked-test false positives",
                }
            )
    if fn_rows:
        fn_counts = pd.DataFrame(fn_rows).groupby("test_id").size().sort_values(ascending=False)
        top_test_id = str(fn_counts.index[0])
        share = float(fn_counts.iloc[0]) / float(fn_counts.sum())
        if share >= 0.20:
            rows.append(
                {
                    "diagnostic": "single_test_dominates_false_negatives",
                    "severity": "warning",
                    "split": "test",
                    "metric": "false_negatives",
                    "baseline": float(baseline_test.get("FN", 0.0)),
                    "tuned": float(tuned_test.get("FN", 0.0)),
                    "delta": float(tuned_test.get("FN", 0.0)) - float(baseline_test.get("FN", 0.0)),
                    "details": f"{top_test_id} accounts for {share:.1%} of locked-test false negatives",
                }
            )

    by_noise = {
        tier: compute_metrics([row for row in tuned.per_case_rows if row["noise_tier"] == tier])
        for tier in {"normal", "high"}
    }
    if by_noise["high"]["total_cases"] and by_noise["normal"]["total_cases"]:
        high_metric = by_noise["high"]["balanced_accuracy"]
        normal_metric = by_noise["normal"]["balanced_accuracy"]
        if normal_metric - high_metric >= 0.05:
            rows.append(
                {
                    "diagnostic": "high_noise_underperforms_normal_noise",
                    "severity": "warning",
                    "split": "all",
                    "metric": "balanced_accuracy",
                    "baseline": float(normal_metric),
                    "tuned": float(high_metric),
                    "delta": float(high_metric - normal_metric),
                    "details": f"high-noise balanced accuracy trails normal-noise by {normal_metric - high_metric:.3f}",
                }
            )

    ci_rows = pd.DataFrame(bootstrap_rows)
    if not ci_rows.empty:
        for metric in ("balanced_accuracy", "precision", "recall"):
            baseline_ci = ci_rows[(ci_rows["profile_name"] == baseline.name) & (ci_rows["split"] == "test") & (ci_rows["metric"] == metric)]
            tuned_ci = ci_rows[(ci_rows["profile_name"] == tuned.name) & (ci_rows["split"] == "test") & (ci_rows["metric"] == metric)]
            if not baseline_ci.empty and not tuned_ci.empty:
                b_low, b_high = float(baseline_ci.iloc[0]["ci_low"]), float(baseline_ci.iloc[0]["ci_high"])
                t_low, t_high = float(tuned_ci.iloc[0]["ci_low"]), float(tuned_ci.iloc[0]["ci_high"])
                overlap = max(0.0, min(b_high, t_high) - max(b_low, t_low))
                if overlap > 0 and abs(float(tuned_test.get(metric, 0.0)) - float(baseline_test.get(metric, 0.0))) < 0.02:
                    rows.append(
                        {
                            "diagnostic": "confidence_interval_overlap_weak_improvement",
                            "severity": "info",
                            "split": "test",
                            "metric": metric,
                            "baseline": float(baseline_test.get(metric, 0.0)),
                            "tuned": float(tuned_test.get(metric, 0.0)),
                            "delta": float(tuned_test.get(metric, 0.0)) - float(baseline_test.get(metric, 0.0)),
                            "details": f"{metric} confidence intervals overlap on locked test; claimed improvement is weak",
                        }
                    )
                    break
    if not rows:
        rows.append(
            {
                "diagnostic": "no_material_overfit_signals",
                "severity": "info",
                "split": "all",
                "metric": "",
                "baseline": 0.0,
                "tuned": 0.0,
                "delta": 0.0,
                "details": "no strong overfit signal detected by the current heuristics",
            }
        )
    return rows


def bootstrap_confidence_intervals(
    case_rows: list[dict[str, Any]],
    profile_name: str,
    *,
    split: str | None = None,
    n_bootstrap: int = 2000,
    seed: int = 1337,
) -> list[dict[str, Any]]:
    if not case_rows:
        return []
    rng = np.random.default_rng(seed)
    observed = compute_metrics(case_rows)
    distributions: dict[str, list[float]] = {metric: [] for metric in ["accuracy", "precision", "recall", "specificity", "balanced_accuracy", "F1", "false_positive_rate", "false_negative_rate"]}
    indices = np.arange(len(case_rows))
    for _ in range(int(n_bootstrap)):
        sample = [case_rows[int(index)] for index in rng.choice(indices, size=len(indices), replace=True)]
        metrics = compute_metrics(sample)
        for metric in distributions:
            distributions[metric].append(float(metrics.get(metric, 0.0)))
    rows: list[dict[str, Any]] = []
    for metric, values in distributions.items():
        rows.append(
            {
                "profile_name": profile_name,
                "split": split or "overall",
                "metric": metric,
                "estimate": float(observed.get(metric, 0.0)),
                "ci_low": float(np.quantile(values, 0.025)),
                "ci_high": float(np.quantile(values, 0.975)),
                "n_bootstrap": int(n_bootstrap),
            }
        )
    return rows


def compute_metrics(case_rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_cases = len(case_rows)
    positives = sum(1 for row in case_rows if row["expected_fault_present"])
    negatives = total_cases - positives
    tp = fp = tn = fn = 0
    conflict_cases = sum(1 for row in case_rows if row.get("multi_match_ambiguity"))
    primary_conflicts = sum(1 for row in case_rows if row.get("conflict_warning"))
    for row in case_rows:
        expected = bool(row["expected_fault_present"])
        predicted = str(row.get("predicted_primary_signature") or "") == str(row["signature_id"])
        if expected and predicted:
            tp += 1
        elif expected and not predicted:
            fn += 1
        elif (not expected) and predicted:
            fp += 1
        else:
            tn += 1
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    specificity = _safe_div(tn, tn + fp)
    balanced_accuracy = (recall + specificity) / 2.0
    f1 = _safe_div(2 * precision * recall, precision + recall)
    return {
        "total_cases": total_cases,
        "positives": positives,
        "negatives": negatives,
        "TP": tp,
        "FP": fp,
        "TN": tn,
        "FN": fn,
        "accuracy": _safe_div(tp + tn, total_cases),
        "precision": precision,
        "recall": recall,
        "sensitivity": recall,
        "specificity": specificity,
        "balanced_accuracy": balanced_accuracy,
        "F1": f1,
        "false_positive_rate": _safe_div(fp, fp + tn),
        "false_negative_rate": _safe_div(fn, fn + tp),
        "conflict_cases": conflict_cases,
        "conflict_rate": _safe_div(conflict_cases, total_cases),
        "primary_conflicts": primary_conflicts,
    }


def aggregate_rows(
    case_rows: list[dict[str, Any]],
    *,
    group_key: str,
    profile_name: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for group, rows in sorted(_group_case_rows(case_rows, group_key).items()):
        metrics = compute_metrics(rows)
        expected_confidences = [float(row.get("confidence_from_expected_analyzer", 0.0)) for row in rows]
        primary_confidences = [float(row.get("predicted_primary_confidence", 0.0)) for row in rows]
        output.append(
            {
                "profile_name": profile_name,
                "group": group,
                "signature_id" if group_key == "signature_id" else group_key: group,
                "total_cases": metrics["total_cases"],
                "positives": metrics["positives"],
                "negatives": metrics["negatives"],
                "TP": metrics["TP"],
                "FP": metrics["FP"],
                "TN": metrics["TN"],
                "FN": metrics["FN"],
                "accuracy": metrics["accuracy"],
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "sensitivity": metrics["sensitivity"],
                "specificity": metrics["specificity"],
                "balanced_accuracy": metrics["balanced_accuracy"],
                "F1": metrics["F1"],
                "false_positive_rate": metrics["false_positive_rate"],
                "false_negative_rate": metrics["false_negative_rate"],
                "mean_expected_confidence": float(np.mean(expected_confidences)) if expected_confidences else 0.0,
                "std_expected_confidence": float(np.std(expected_confidences, ddof=1)) if len(expected_confidences) > 1 else 0.0,
                "mean_primary_confidence": float(np.mean(primary_confidences)) if primary_confidences else 0.0,
                "std_primary_confidence": float(np.std(primary_confidences, ddof=1)) if len(primary_confidences) > 1 else 0.0,
                "conflict_rate": metrics["conflict_rate"],
            }
        )
    return output


def objective_score(metrics: dict[str, Any], objective_name: str, *, conflict_rate: float = 0.0) -> float:
    precision = float(metrics.get("precision", 0.0))
    recall = float(metrics.get("recall", 0.0))
    f1 = float(metrics.get("F1", 0.0))
    balanced_accuracy = float(metrics.get("balanced_accuracy", 0.0))
    if objective_name == "balanced_default":
        return balanced_accuracy - max(0.0, 0.88 - precision) * 2.0
    if objective_name == "conservative_precision":
        return precision - max(0.0, 0.85 - recall) * 2.0
    if objective_name == "sensitive_fault_finding":
        return recall - max(0.0, 0.85 - precision) * 2.0
    if objective_name == "field_triage":
        return f1 - 0.25 * conflict_rate
    raise ValueError(f"unknown objective: {objective_name}")


def _group_case_rows(case_rows: list[dict[str, Any]], group_key: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in case_rows:
        groups.setdefault(str(row.get(group_key, "")), []).append(row)
    return groups


def _evaluate_capture(manifest_row: dict[str, Any], capture_rows: pd.DataFrame, profile: ThresholdProfile) -> dict[str, Any]:
    capture_id = str(manifest_row["capture_id"])
    expected_signature = str(manifest_row["signature_id"])
    truth_label = str(manifest_row["truth_label"])
    expected_fault_present = _to_bool(manifest_row["expected_fault_present"])
    candidate_rows = []
    for _, result in capture_rows.iterrows():
        sig_id = str(result["signature_id"])
        threshold = float(profile.threshold_for(sig_id))
        confidence = float(result["confidence"])
        matched = _to_bool(result.get("raw_matched", True))
        reference_score = float(result.get("reference_evidence_score", 1.0))
        threshold_pass = bool(matched and confidence >= threshold and reference_score > 0.0)
        diagnostic_score = max(0.0, min(1.0, confidence * (0.70 + 0.30 * reference_score) + (0.05 if threshold_pass else 0.0)))
        candidate_rows.append(
            {
                "capture_id": capture_id,
                "signature_id": sig_id,
                "confidence": confidence,
                "threshold": threshold,
                "threshold_pass": threshold_pass,
                "reference_score": reference_score,
                "rank": int(result.get("rank", 0)),
                "diagnostic_score": diagnostic_score,
                "raw_matched": matched,
                "warnings": str(result.get("warnings", "")),
                "conflict_warning": str(result.get("conflict_warning", "")),
                "required_reference_status": str(result.get("required_reference_status", "")),
            }
        )
    candidate_rows.sort(key=lambda item: (item["threshold_pass"], item["diagnostic_score"], item["confidence"], item["reference_score"], -item["rank"]), reverse=True)
    threshold_pass_rows = [row for row in candidate_rows if row["threshold_pass"]]
    primary = threshold_pass_rows[0] if threshold_pass_rows else None
    top_candidates = threshold_pass_rows[:3] if threshold_pass_rows else candidate_rows[:3]
    expected_row = next((row for row in candidate_rows if row["signature_id"] == expected_signature), None)
    primary_signature = primary["signature_id"] if primary else ""
    primary_confidence = float(primary["confidence"]) if primary else 0.0
    expected_confidence = float(expected_row["confidence"]) if expected_row else 0.0
    selected_threshold = float(primary["threshold"]) if primary else float(expected_row["threshold"]) if expected_row else profile.default_threshold
    conflict_warning = _conflict_warning(candidate_rows)
    warnings = []
    if expected_row and expected_row["reference_score"] <= 0.0:
        warnings.append("required_reference_evidence_missing_or_weak")
    if conflict_warning:
        warnings.append(conflict_warning)
    if primary is None:
        decision_reason = "rejected_or_below_threshold"
    elif primary_signature == expected_signature:
        decision_reason = "primary_diagnosis"
    else:
        decision_reason = "secondary_candidate"
    is_correct = (expected_fault_present and primary_signature == expected_signature) or ((not expected_fault_present) and primary_signature != expected_signature)
    is_false_negative = expected_fault_present and primary_signature != expected_signature
    is_false_positive = (not expected_fault_present) and primary_signature == expected_signature
    return {
        "capture_id": capture_id,
        "test_id": str(manifest_row.get("test_id", capture_id)),
        "split": str(manifest_row.get("split", "")),
        "split_purpose": str(manifest_row.get("split_purpose", "")),
        "signature_id": expected_signature,
        "family": str(manifest_row["family"]),
        "truth_label": truth_label,
        "expected_fault_present": expected_fault_present,
        "noise_tier": str(manifest_row["noise_tier"]),
        "waveform_intent": str(manifest_row.get("waveform_intent", manifest_row.get("variant", truth_label))),
        "predicted_primary_signature": primary_signature,
        "predicted_primary_confidence": primary_confidence,
        "confidence_from_expected_analyzer": expected_confidence,
        "threshold_used": selected_threshold,
        "threshold_profile": profile.name,
        "decision_reason": decision_reason,
        "warning": " | ".join(warnings),
        "missing_channel_reference_status": str(expected_row.get("required_reference_status", "")) if expected_row else "missing_or_not_reported",
        "top_3_competing_signatures": " | ".join(
            f"{row['signature_id']}@{row['confidence']}"
            for row in top_candidates
        ),
        "conflict_warning": conflict_warning,
        "multi_match_count": len(threshold_pass_rows),
        "multi_match_ambiguity": bool(len(threshold_pass_rows) >= 2),
        "primary_diagnosis": primary_signature,
        "secondary_candidates": ",".join(row["signature_id"] for row in threshold_pass_rows[1:]),
        "is_correct": is_correct,
        "is_false_negative": is_false_negative,
        "is_false_positive": is_false_positive,
        "selected_threshold_signature": primary_signature or expected_signature,
        "selected_threshold": selected_threshold,
    }


def _conflict_warning(candidate_rows: list[dict[str, Any]]) -> str:
    high = [row for row in candidate_rows if row["threshold_pass"]]
    if len(high) < 2:
        return ""
    top = max(row["confidence"] for row in high)
    close = [row["signature_id"] for row in high if top - row["confidence"] <= 0.10]
    if len(close) >= 2:
        return "multiple_high_confidence_signatures_match: " + ", ".join(close)
    return "multiple_signatures_match_above_threshold: " + ", ".join(row["signature_id"] for row in high)


def _allocate_counts(total: int, ratios: tuple[float, float, float]) -> list[int]:
    raw = [total * ratio for ratio in ratios]
    counts = [int(math.floor(value)) for value in raw]
    remainder = total - sum(counts)
    order = sorted(range(len(raw)), key=lambda idx: (raw[idx] - counts[idx], -idx), reverse=True)
    for idx in order[:remainder]:
        counts[idx] += 1
    return counts


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _safe_div(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _safe_json(value: Any) -> Any:
    try:
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
    except Exception:
        pass
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_json(v) for v in value]
    if isinstance(value, tuple):
        return [_safe_json(v) for v in value]
    return value


def write_dataframe(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(path, index=False)


def load_profiles(baseline_profile: str | Path, tuned_profile: str | Path) -> tuple[ThresholdProfile, ThresholdProfile]:
    baseline = load_threshold_profile(resolve_profile_path(baseline_profile))
    tuned = load_threshold_profile(resolve_profile_path(tuned_profile))
    return baseline, tuned


def analyze_tuning_statistics(
    *,
    manifest_path: str | Path,
    results_path: str | Path,
    baseline_profile_path: str | Path,
    tuned_profile_path: str | Path,
    out_dir: str | Path,
    split_seed: int = 1337,
    split_ratios: tuple[float, float, float] = DEFAULT_SPLIT_RATIOS,
    bootstrap: int = 2000,
    objective_name: str = DEFAULT_OBJECTIVE,
) -> dict[str, Any]:
    if objective_name not in OBJECTIVE_NAMES:
        raise ValueError(f"unknown objective {objective_name!r}; expected one of {sorted(OBJECTIVE_NAMES)}")

    manifest = load_manifest_table(manifest_path)
    results = load_results_table(results_path)
    results_by_capture = {str(capture_id): group.copy() for capture_id, group in results.groupby("capture_id", sort=False)}
    baseline_profile, tuned_profile = load_profiles(baseline_profile_path, tuned_profile_path)
    split_manifest = stratified_split_manifest(manifest, seed=split_seed, ratios=split_ratios)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    split_manifest_csv = out_path / "split_manifest.csv"
    split_manifest.to_csv(split_manifest_csv, index=False)

    baseline_run = evaluate_profile_runs(split_manifest, results_by_capture, baseline_profile)
    tuned_run = evaluate_profile_runs(split_manifest, results_by_capture, tuned_profile)

    split_summary_rows = build_split_summary(split_manifest, baseline_run, tuned_run, objective_name=objective_name)
    compare_rows = compare_profiles(baseline_run, tuned_run)
    bootstrap_rows = [
        *baseline_run.bootstrap_rows,
        *tuned_run.bootstrap_rows,
    ]
    threshold_ablation_rows = build_threshold_ablation_rows(split_manifest, results_by_capture, baseline_profile, tuned_profile, tuned_run)
    overfit_rows = build_overfit_diagnostics(split_manifest, baseline_run, tuned_run, bootstrap_rows)

    per_case_rows = []
    for profile_run in (baseline_run, tuned_run):
        for row in profile_run.per_case_rows:
            per_case_rows.append(
                {
                    **row,
                    "profile_name": profile_run.name,
                    "objective_name": objective_name,
                    "objective_score": objective_score(profile_run.overall_metrics, objective_name, conflict_rate=float(profile_run.overall_metrics.get("conflict_rate", 0.0))),
                }
            )

    per_analyzer_rows = []
    per_waveform_intent_rows = []
    per_noise_tier_rows = []
    for profile_run in (baseline_run, tuned_run):
        for row in profile_run.per_analyzer_rows:
            per_analyzer_rows.append({**row, "split": "overall"})
        for row in profile_run.per_waveform_intent_rows:
            per_waveform_intent_rows.append({**row, "split": "overall"})
        for row in profile_run.per_noise_tier_rows:
            per_noise_tier_rows.append({**row, "split": "overall"})

    # Add split-specific aggregates to make the audit layer easier to scan.
    for profile_run in (baseline_run, tuned_run):
        for split in ["train", "dev", "test"]:
            subset = [row for row in profile_run.per_case_rows if row["split"] == split]
            per_analyzer_rows.extend(
                {**row, "split": split}
                for row in aggregate_rows(subset, group_key="signature_id", profile_name=profile_run.name)
            )
            per_waveform_intent_rows.extend(
                {**row, "split": split}
                for row in aggregate_rows(subset, group_key="waveform_intent", profile_name=profile_run.name)
            )
            per_noise_tier_rows.extend(
                {**row, "split": split}
                for row in aggregate_rows(subset, group_key="noise_tier", profile_name=profile_run.name)
            )

    baseline_vs_tuned_rows = compare_rows
    bootstrap_rows = []
    for profile_run in (baseline_run, tuned_run):
        for split in ["train", "dev", "test"]:
            subset = [row for row in profile_run.per_case_rows if row["split"] == split]
            bootstrap_rows.extend(
                bootstrap_confidence_intervals(
                    subset,
                    profile_run.name,
                    split=split,
                    n_bootstrap=bootstrap,
                    seed=split_seed,
                )
            )

    split_summary_json = {
        "split_seed": split_seed,
        "split_ratios": list(split_ratios),
        "objective_name": objective_name,
        "split_names": list(SPLIT_NAMES),
        "split_purposes": dict(SPLIT_PURPOSES),
        "splits": split_summary_rows,
        "recommended_profile": "tuned"
        if any(row["split"] == "dev" and row["objective_score_tuned"] >= row["objective_score_baseline"] for row in split_summary_rows)
        else "baseline",
    }
    baseline_vs_tuned_json = _safe_json(baseline_vs_tuned_rows)
    bootstrap_json = _safe_json(bootstrap_rows)
    threshold_ablation_json = _safe_json(threshold_ablation_rows)
    overfit_json = _safe_json(overfit_rows)

    write_dataframe(out_path / "split_summary.csv", split_summary_rows)
    (out_path / "split_summary.json").write_text(json.dumps(split_summary_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_dataframe(out_path / "baseline_vs_tuned_metrics.csv", baseline_vs_tuned_rows)
    (out_path / "baseline_vs_tuned_metrics.json").write_text(json.dumps(baseline_vs_tuned_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_dataframe(out_path / "bootstrap_confidence_intervals.csv", bootstrap_rows)
    (out_path / "bootstrap_confidence_intervals.json").write_text(json.dumps(bootstrap_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_dataframe(out_path / "per_analyzer_metrics.csv", per_analyzer_rows)
    write_dataframe(out_path / "per_test_case_metrics.csv", per_case_rows)
    write_dataframe(out_path / "per_waveform_intent_metrics.csv", per_waveform_intent_rows)
    write_dataframe(out_path / "per_noise_tier_metrics.csv", per_noise_tier_rows)
    write_dataframe(out_path / "threshold_ablation_metrics.csv", threshold_ablation_rows)
    (out_path / "threshold_ablation_metrics.json").write_text(json.dumps(threshold_ablation_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_dataframe(out_path / "overfit_diagnostics.csv", overfit_rows)
    (out_path / "overfit_diagnostics.json").write_text(json.dumps(overfit_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    recommendation = "tuned" if split_summary_json["recommended_profile"] == "tuned" else "baseline"
    readme = _build_readme(
        manifest=split_manifest,
        baseline_run=baseline_run,
        tuned_run=tuned_run,
        split_summary_rows=split_summary_rows,
        baseline_vs_tuned_rows=baseline_vs_tuned_rows,
        bootstrap_rows=bootstrap_rows,
        overfit_rows=overfit_rows,
        recommendation=recommendation,
        split_seed=split_seed,
        split_ratios=split_ratios,
        objective_name=objective_name,
        baseline_profile_path=str(resolve_profile_path(baseline_profile_path)),
        tuned_profile_path=str(resolve_profile_path(tuned_profile_path)),
    )
    (out_path / "README.md").write_text(readme, encoding="utf-8")

    return {
        "split_manifest_csv": split_manifest_csv,
        "split_summary_csv": out_path / "split_summary.csv",
        "split_summary_json": out_path / "split_summary.json",
        "baseline_vs_tuned_metrics_csv": out_path / "baseline_vs_tuned_metrics.csv",
        "baseline_vs_tuned_metrics_json": out_path / "baseline_vs_tuned_metrics.json",
        "bootstrap_confidence_intervals_csv": out_path / "bootstrap_confidence_intervals.csv",
        "bootstrap_confidence_intervals_json": out_path / "bootstrap_confidence_intervals.json",
        "per_analyzer_metrics_csv": out_path / "per_analyzer_metrics.csv",
        "per_test_case_metrics_csv": out_path / "per_test_case_metrics.csv",
        "per_waveform_intent_metrics_csv": out_path / "per_waveform_intent_metrics.csv",
        "per_noise_tier_metrics_csv": out_path / "per_noise_tier_metrics.csv",
        "threshold_ablation_metrics_csv": out_path / "threshold_ablation_metrics.csv",
        "overfit_diagnostics_csv": out_path / "overfit_diagnostics.csv",
        "README": out_path / "README.md",
    }


def _build_readme(
    *,
    manifest: pd.DataFrame,
    baseline_run: ProfileRun,
    tuned_run: ProfileRun,
    split_summary_rows: list[dict[str, Any]],
    baseline_vs_tuned_rows: list[dict[str, Any]],
    bootstrap_rows: list[dict[str, Any]],
    overfit_rows: list[dict[str, Any]],
    recommendation: str,
    split_seed: int,
    split_ratios: tuple[float, float, float],
    objective_name: str,
    baseline_profile_path: str,
    tuned_profile_path: str,
) -> str:
    overall_base = baseline_run.overall_metrics
    overall_tuned = tuned_run.overall_metrics
    dev_base = baseline_run.split_metrics.get("dev", {})
    dev_tuned = tuned_run.split_metrics.get("dev", {})
    test_base = baseline_run.split_metrics.get("test", {})
    test_tuned = tuned_run.split_metrics.get("test", {})
    lines = [
        "# Gamma Threshold Tuning Audit",
        "",
        "## What this is",
        "Synthetic-corpus statistical analysis for Gamma's threshold tuning methodology.",
        "The tuned-v1 score on the 1900-case corpus is development-corpus performance unless it also holds on the locked test split.",
        "",
        "## Split setup",
        f"- Split seed: {split_seed}",
        f"- Split ratios: train/dev/test = {split_ratios[0]:.2f}/{split_ratios[1]:.2f}/{split_ratios[2]:.2f}",
        "- Split purposes: train=tune/dev, dev=validation/model-selection, test=locked_test",
        "",
        "## Profiles compared",
        f"- Baseline profile: `{baseline_profile_path}`",
        f"- Tuned profile: `{tuned_profile_path}`",
        f"- Objective: `{objective_name}`",
        f"- Recommended profile: `{recommendation}`",
        "",
        "## Overall metrics",
        f"- Baseline accuracy: {overall_base.get('accuracy', 0.0):.4f}",
        f"- Tuned accuracy: {overall_tuned.get('accuracy', 0.0):.4f}",
        f"- Baseline precision: {overall_base.get('precision', 0.0):.4f}",
        f"- Tuned precision: {overall_tuned.get('precision', 0.0):.4f}",
        f"- Baseline recall: {overall_base.get('recall', 0.0):.4f}",
        f"- Tuned recall: {overall_tuned.get('recall', 0.0):.4f}",
        f"- Baseline specificity: {overall_base.get('specificity', 0.0):.4f}",
        f"- Tuned specificity: {overall_tuned.get('specificity', 0.0):.4f}",
        f"- Baseline balanced accuracy: {overall_base.get('balanced_accuracy', 0.0):.4f}",
        f"- Tuned balanced accuracy: {overall_tuned.get('balanced_accuracy', 0.0):.4f}",
        "",
        "## Locked test split",
        f"- Baseline balanced accuracy: {test_base.get('balanced_accuracy', 0.0):.4f}",
        f"- Tuned balanced accuracy: {test_tuned.get('balanced_accuracy', 0.0):.4f}",
        f"- Baseline precision: {test_base.get('precision', 0.0):.4f}",
        f"- Tuned precision: {test_tuned.get('precision', 0.0):.4f}",
        f"- Baseline recall: {test_base.get('recall', 0.0):.4f}",
        f"- Tuned recall: {test_tuned.get('recall', 0.0):.4f}",
        "",
        "## Split summary",
    ]
    for row in split_summary_rows:
        lines.append(
            f"- {row['split']}: {row['total_cases']} cases, {row['positives']} positives, {row['negatives']} negatives, "
            f"baseline BA {row['baseline_balanced_accuracy']:.4f}, tuned BA {row['tuned_balanced_accuracy']:.4f}"
        )
    lines.extend(
        [
            "",
            "## Bootstrap confidence intervals",
            f"- Bootstrap samples: {bootstrap_rows[0]['n_bootstrap'] if bootstrap_rows else 0}",
            "- Confidence intervals are percentile bootstrap estimates.",
            "",
            "## Overfit diagnostics",
        ]
    )
    for row in overfit_rows:
        lines.append(f"- {row['severity']}: {row['diagnostic']} ({row['details']})")
    lines.extend(
        [
            "",
            "## Baseline vs tuned",
            f"- Development split balanced accuracy delta: {dev_tuned.get('balanced_accuracy', 0.0) - dev_base.get('balanced_accuracy', 0.0):.4f}",
            f"- Locked test balanced accuracy delta: {test_tuned.get('balanced_accuracy', 0.0) - test_base.get('balanced_accuracy', 0.0):.4f}",
            "",
            "## Caveats",
            "- This analysis audits the tuning methodology on a synthetic corpus; it is not field validation.",
            "- Confidence intervals can overlap even when point estimates differ, so small gains should be treated carefully.",
            "- Remaining risks before field validation include split sensitivity, high-noise collapse, and dominance by a single analyzer or test pattern.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze Gamma threshold tuning statistics and split-level audit metrics.")
    parser.add_argument("--manifest", required=True, help="Dataset manifest CSV.")
    parser.add_argument("--results", required=True, help="Campaign results CSV or score table CSV, or a directory containing them.")
    parser.add_argument("--baseline-profile", required=True, help="Baseline threshold profile YAML/JSON.")
    parser.add_argument("--tuned-profile", required=True, help="Tuned threshold profile YAML/JSON.")
    parser.add_argument("--out", required=True, help="Output directory for audit reports.")
    parser.add_argument("--split-seed", type=int, default=1337, help="Deterministic split seed.")
    parser.add_argument("--split-ratios", default="0.6,0.2,0.2", help="Comma-separated train/dev/test split ratios.")
    parser.add_argument("--bootstrap", type=int, default=2000, help="Bootstrap iterations per split/profile.")
    parser.add_argument(
        "--objective",
        default=DEFAULT_OBJECTIVE,
        choices=sorted(OBJECTIVE_NAMES),
        help="Objective function used to score candidate profiles.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    analyze_tuning_statistics(
        manifest_path=args.manifest,
        results_path=args.results,
        baseline_profile_path=args.baseline_profile,
        tuned_profile_path=args.tuned_profile,
        out_dir=args.out,
        split_seed=args.split_seed,
        split_ratios=parse_ratio_list(args.split_ratios),
        bootstrap=args.bootstrap,
        objective_name=args.objective,
    )
    return 0
