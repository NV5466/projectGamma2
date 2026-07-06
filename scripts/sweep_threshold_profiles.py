from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import csv
import json
import sys
from collections import defaultdict
from copy import deepcopy
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gamma_app.threshold_profiles import ThresholdProfile, load_threshold_profile, save_threshold_profile


def _parse_thresholds(value: str | None) -> list[float]:
    if not value:
        return [round(i / 100.0, 2) for i in range(5, 100, 5)]
    thresholds = [float(item.strip()) for item in value.split(",") if item.strip()]
    if not thresholds:
        raise argparse.ArgumentTypeError("at least one threshold is required")
    for threshold in thresholds:
        if not 0.0 <= threshold <= 1.0:
            raise argparse.ArgumentTypeError(f"threshold out of [0, 1]: {threshold}")
    return thresholds


def _parse_overrides(values: list[str] | None) -> dict[str, float]:
    overrides: dict[str, float] = {}
    for item in values or []:
        if "=" not in item:
            raise argparse.ArgumentTypeError(f"override must be signature=threshold: {item}")
        key, raw = item.split("=", 1)
        threshold = float(raw.strip())
        if not 0.0 <= threshold <= 1.0:
            raise argparse.ArgumentTypeError(f"threshold out of [0, 1]: {threshold}")
        overrides[key.strip()] = threshold
    return overrides


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _normalize_signature(signature_id: str) -> str:
    return "emi_eft_burst" if signature_id == "emi_eft_burst_v010" else signature_id


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except Exception:
        return default


@dataclass(frozen=True)
class CaseOutcome:
    capture_id: str
    truth_label: str
    expected_signature: str
    predicted_signature: str | None
    is_correct: bool
    selected_row: dict[str, Any] | None


def _load_manifest(manifest_path: Path) -> dict[str, dict[str, str]]:
    rows = _read_csv(manifest_path)
    if not rows:
        raise RuntimeError(f"manifest has no rows: {manifest_path}")
    return {row["capture_id"]: row for row in rows}


def _load_results(campaign_dir: Path) -> dict[str, list[dict[str, str]]]:
    for name in ("campaign_results.csv", "per_case_signature_scores.csv"):
        path = campaign_dir / name
        if path.exists():
            rows = _read_csv(path)
            grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in rows:
                grouped[str(row["capture_id"])].append(row)
            return grouped
    raise FileNotFoundError(
        f"missing campaign results in {campaign_dir}; expected campaign_results.csv or per_case_signature_scores.csv"
    )


def _simulate_case(group: list[dict[str, str]], profile: ThresholdProfile, manifest_row: dict[str, str]) -> CaseOutcome:
    candidates: list[tuple[float, float, float, str, dict[str, Any]]] = []
    for row in group:
        signature_id = str(row["signature_id"])
        threshold = profile.threshold_for(signature_id)
        matched = str(row.get("raw_matched", "")).lower() == "true"
        confidence = _safe_float(row.get("confidence"))
        reference_score = _safe_float(row.get("reference_evidence_score"))
        threshold_pass = bool(matched and confidence >= threshold and reference_score > 0.0)
        diagnostic_score = max(
            0.0,
            min(1.0, confidence * (0.70 + 0.30 * reference_score) + (0.05 if threshold_pass else 0.0)),
        )
        if threshold_pass:
            candidates.append((diagnostic_score, confidence, reference_score, int(row.get("rank", 0) or 0), signature_id, row))

    candidates.sort(key=lambda item: (item[0], item[1], item[2], -item[3]), reverse=True)
    selected = candidates[0][5] if candidates else None
    if not group:
        raise RuntimeError("empty case group")
    expected_signature = _normalize_signature(str(manifest_row["signature_id"]))
    truth_label = str(manifest_row["truth_label"])
    capture_id = str(group[0]["capture_id"])
    predicted_signature = str(selected["signature_id"]) if selected else None
    is_correct = (truth_label == expected_signature and predicted_signature == expected_signature) or (
        truth_label != expected_signature and predicted_signature != expected_signature
    )
    return CaseOutcome(
        capture_id=capture_id,
        truth_label=truth_label,
        expected_signature=expected_signature,
        predicted_signature=predicted_signature,
        is_correct=is_correct,
        selected_row=selected,
    )


def _simulate(results_by_capture: dict[str, list[dict[str, str]]], manifest: dict[str, dict[str, str]], profile: ThresholdProfile) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    per_signature: dict[str, dict[str, int]] = defaultdict(lambda: {"TP": 0, "FP": 0, "TN": 0, "FN": 0})
    cases: list[CaseOutcome] = []
    for capture_id, group in results_by_capture.items():
        if capture_id not in manifest:
            continue
        meta = manifest[capture_id]
        outcome = _simulate_case(group, profile, meta)
        expected_signature = _normalize_signature(str(meta["signature_id"]))
        truth = str(meta["truth_label"]).lower()
        predicted = outcome.predicted_signature
        cases.append(outcome)
        if truth == "positive":
            if predicted == expected_signature:
                tp += 1
                per_signature[expected_signature]["TP"] += 1
            else:
                fn += 1
                per_signature[expected_signature]["FN"] += 1
        else:
            if predicted == expected_signature:
                fp += 1
                per_signature[expected_signature]["FP"] += 1
            else:
                tn += 1
                per_signature[expected_signature]["TN"] += 1

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    balanced = (recall + specificity) / 2.0
    accuracy = (tp + tn) / max(1, tp + tn + fp + fn)
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "balanced_accuracy": balanced,
        "accuracy": accuracy,
        "per_signature": per_signature,
        "cases": [case.__dict__ for case in cases],
    }


def _objective(metrics: dict[str, Any], min_precision: float, target_recall: float) -> tuple[float, float, float, float]:
    precision = float(metrics["precision"])
    recall = float(metrics["recall"])
    specificity = float(metrics["specificity"])
    balanced = float(metrics["balanced_accuracy"])
    precision_gate = 1.0 if precision >= min_precision else 0.0
    recall_gate = 1.0 if recall >= target_recall else 0.0
    return (precision_gate, recall_gate, recall, precision, specificity + balanced)


def _sweep_profile(
    base_profile: ThresholdProfile,
    results_by_capture: dict[str, list[dict[str, str]]],
    manifest: dict[str, dict[str, str]],
    candidate_thresholds: list[float],
    signatures: list[str],
    *,
    min_precision: float,
    target_recall: float,
    max_iterations: int = 4,
) -> tuple[ThresholdProfile, list[dict[str, Any]], dict[str, Any]]:
    profile = deepcopy(base_profile)
    sweep_rows: list[dict[str, Any]] = []

    for iteration in range(1, max_iterations + 1):
        changed = False
        for signature_id in signatures:
            current_threshold = profile.threshold_for(signature_id)
            best_threshold = current_threshold
            best_metrics = _simulate(results_by_capture, manifest, profile)
            best_score = _objective(best_metrics, min_precision, target_recall)
            for threshold in candidate_thresholds:
                trial = deepcopy(profile)
                trial.signature_thresholds[signature_id] = float(threshold)
                metrics = _simulate(results_by_capture, manifest, trial)
                score = _objective(metrics, min_precision, target_recall)
                sweep_rows.append(
                    {
                        "iteration": iteration,
                        "signature_id": signature_id,
                        "threshold": float(threshold),
                        "TP": metrics["tp"],
                        "FP": metrics["fp"],
                        "TN": metrics["tn"],
                        "FN": metrics["fn"],
                        "precision": metrics["precision"],
                        "recall": metrics["recall"],
                        "specificity": metrics["specificity"],
                        "balanced_accuracy": metrics["balanced_accuracy"],
                        "accuracy": metrics["accuracy"],
                        "objective_gate": score[0],
                        "objective_recall_gate": score[1],
                        "objective_recall": score[2],
                        "objective_precision": score[3],
                        "objective_tail": score[4],
                        "selected": False,
                    }
                )
                if score > best_score:
                    best_score = score
                    best_threshold = float(threshold)
                    best_metrics = metrics
            if best_threshold != current_threshold:
                profile.signature_thresholds[signature_id] = best_threshold
                changed = True
                for row in reversed(sweep_rows):
                    if row["iteration"] == iteration and row["signature_id"] == signature_id and row["threshold"] == best_threshold:
                        row["selected"] = True
                        break
        if not changed:
            break

    tuned_metrics = _simulate(results_by_capture, manifest, profile)
    return profile, sweep_rows, tuned_metrics


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep Gamma threshold profiles against a validation corpus.")
    parser.add_argument("--campaign-dir", required=True, help="Campaign output directory containing cached Gamma CSV/JSON outputs.")
    parser.add_argument("--manifest", required=True, help="Dataset manifest CSV for truth labels and capture metadata.")
    parser.add_argument("--base-profile", help="Optional starting threshold profile YAML/JSON.")
    parser.add_argument("--out-dir", required=True, help="Directory to write sweep_results.csv/json and the recommended profile.")
    parser.add_argument("--thresholds", help="Comma-separated threshold candidates. Default: 0.05..0.95.")
    parser.add_argument("--min-precision", type=float, default=0.88, help="Minimum precision gate used during sweep selection.")
    parser.add_argument("--target-recall", type=float, default=0.92, help="Target recall gate used during sweep selection.")
    parser.add_argument("--max-iterations", type=int, default=4, help="Coordinate descent passes to run.")
    parser.add_argument(
        "--override",
        action="append",
        help="Override a threshold in the starting profile, formatted as signature_id=threshold. May be repeated.",
    )
    parser.add_argument("--profile-name", default="gamma_1900_tuned_v1")
    parser.add_argument("--based-on", default="default")
    parser.add_argument("--created-for", default="massive_1900 analyzer-validation corpus")
    parser.add_argument("--recommendation-out", help="Optional explicit path for the recommended profile.")
    parser.add_argument("--summary-out", help="Optional explicit path for a JSON summary.")
    args = parser.parse_args(argv)

    candidate_thresholds = _parse_thresholds(args.thresholds)
    manifest = _load_manifest(Path(args.manifest))
    results_by_capture = _load_results(Path(args.campaign_dir))
    base_profile = load_threshold_profile(args.base_profile) if args.base_profile else ThresholdProfile()
    base_profile.name = str(base_profile.name or "default")
    for item in _parse_overrides(args.override).items():
        base_profile.signature_thresholds[item[0]] = float(item[1])

    signatures = sorted({row["signature_id"] for rows in results_by_capture.values() for row in rows})
    baseline_metrics = _simulate(results_by_capture, manifest, base_profile)
    tuned_profile, sweep_rows, tuned_metrics = _sweep_profile(
        base_profile,
        results_by_capture,
        manifest,
        candidate_thresholds,
        signatures,
        min_precision=args.min_precision,
        target_recall=args.target_recall,
        max_iterations=args.max_iterations,
    )
    tuned_profile.name = args.profile_name
    tuned_profile.based_on = args.based_on
    tuned_profile.created_for = args.created_for
    tuned_profile.baseline_metrics = {k: baseline_metrics[k] for k in ("tp", "fp", "tn", "fn", "precision", "recall", "specificity", "balanced_accuracy", "accuracy")}
    tuned_profile.tuned_metrics = {k: tuned_metrics[k] for k in ("tp", "fp", "tn", "fn", "precision", "recall", "specificity", "balanced_accuracy", "accuracy")}
    tuned_profile.notes = [
        "Synthetic corpus tuning only; not field calibration.",
        "Thresholds were chosen by coordinate sweep over the cached 1900-case validation corpus.",
        f"Precision gate: {args.min_precision:.2f}; recall target: {args.target_recall:.2f}.",
    ]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sweep_csv = out_dir / "sweep_results.csv"
    sweep_json = out_dir / "sweep_results.json"
    profile_out = Path(args.recommendation_out) if args.recommendation_out else out_dir / "recommended_threshold_profile.yaml"
    summary_out = Path(args.summary_out) if args.summary_out else out_dir / "sweep_results_summary.json"

    # Mark the winning threshold for each signature in the exported CSV.
    selected_map = {sig: tuned_profile.threshold_for(sig) for sig in signatures}
    for row in sweep_rows:
        if selected_map.get(row["signature_id"]) == row["threshold"]:
            row["selected"] = True
    _write_csv(sweep_csv, sweep_rows)
    sweep_json.write_text(json.dumps({"baseline_metrics": baseline_metrics, "tuned_metrics": tuned_metrics, "selected_thresholds": selected_map, "rows": sweep_rows}, indent=2, sort_keys=True, default=str), encoding="utf-8")
    save_threshold_profile(tuned_profile, profile_out)
    summary_out.write_text(
        json.dumps(
            {
                "profile_name": tuned_profile.name,
                "based_on": tuned_profile.based_on,
                "created_for": tuned_profile.created_for,
                "baseline_metrics": tuned_profile.baseline_metrics,
                "tuned_metrics": tuned_profile.tuned_metrics,
                "selected_thresholds": selected_map,
                "candidate_thresholds": candidate_thresholds,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    print(json.dumps({"baseline_metrics": baseline_metrics, "tuned_metrics": tuned_metrics, "profile_out": str(profile_out), "summary_out": str(summary_out)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
