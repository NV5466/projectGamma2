from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from gamma_app.io import load_captures
from gamma_app.registry import load_available_signatures
from gamma_app.results import result_rows
from gamma_app.runtime import default_registry_root, default_threshold_profile_path
from gamma_app.threshold_profiles import load_threshold_profile
from gamma_core.runner import run_campaign

NO_MATCH = "no_match"
UNKNOWN_TRUTH = "__unknown__"


def infer_truth_label(capture: Any, known_seed_ids: set[str], mode: str) -> str | None:
    """Return the expected seed label for confusion-matrix scoring."""
    if mode in {"npz", "auto"} and capture.truth_label:
        return str(capture.truth_label)

    source_file = Path(str(capture.metadata.get("source_file", "")))

    if mode in {"parent", "auto"}:
        for parent in [source_file.parent, *source_file.parents]:
            if parent.name in known_seed_ids:
                return parent.name

    if mode in {"filename", "auto"}:
        name = source_file.stem
        for seed_id in sorted(known_seed_ids, key=len, reverse=True):
            if seed_id in name:
                return seed_id

    return None


def selected_prediction(rows: list[dict[str, Any]], capture_id: str) -> tuple[str, float, str]:
    capture_rows = [row for row in rows if str(row["capture_id"]) == str(capture_id)]
    selected = [row for row in capture_rows if row.get("is_primary_diagnosis")]
    if selected:
        row = selected[0]
        return str(row["signature_id"]), float(row["confidence"]), str(row.get("decision", "primary_diagnosis"))
    if capture_rows:
        top = sorted(capture_rows, key=lambda row: int(row.get("rank", 999)))[0]
        return NO_MATCH, float(top.get("confidence", 0.0)), "no_primary_diagnosis"
    return NO_MATCH, 0.0, "no_result_rows"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_confusion_matrix(prediction_rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, dict[str, int]]]:
    labels = sorted(
        {
            str(row["truth_label"])
            for row in prediction_rows
            if row["truth_label"] != UNKNOWN_TRUTH
        }
        | {str(row["predicted_label"]) for row in prediction_rows}
    )
    matrix: dict[str, dict[str, int]] = {
        truth: {predicted: 0 for predicted in labels}
        for truth in labels
        if truth != NO_MATCH
    }
    for row in prediction_rows:
        truth = str(row["truth_label"])
        predicted = str(row["predicted_label"])
        if truth == UNKNOWN_TRUTH:
            continue
        matrix.setdefault(truth, {label: 0 for label in labels})
        matrix[truth].setdefault(predicted, 0)
        matrix[truth][predicted] += 1
    return labels, matrix


def write_confusion_matrix(path: Path, labels: list[str], matrix: dict[str, dict[str, int]]) -> None:
    rows = []
    for truth in sorted(matrix):
        row = {"truth_label": truth}
        row.update({label: matrix[truth].get(label, 0) for label in labels})
        rows.append(row)
    write_csv(path, rows, ["truth_label", *labels])


def run_confusion_matrix(
    input_path: str | Path,
    out_dir: str | Path,
    *,
    registry_root: str | Path | None = None,
    threshold_profile_path: str | Path | None = None,
    truth_source: str = "auto",
    max_cases: int | None = None,
) -> dict[str, Any]:
    registry_root = registry_root or default_registry_root()
    threshold_profile = load_threshold_profile(threshold_profile_path or default_threshold_profile_path())
    signatures, registry_failures = load_available_signatures(registry_root)
    if not signatures:
        raise RuntimeError("no electrical signatures loaded")

    captures, warnings = load_captures(input_path, max_cases=max_cases)
    if not captures:
        raise RuntimeError("no supported captures loaded")

    case_results = run_campaign(captures, signatures)
    family_by_signature = {spec.seed_id: spec.family for spec in signatures}
    known_seed_ids = {spec.seed_id for spec in signatures}
    rows = result_rows(
        case_results,
        family_by_signature=family_by_signature,
        threshold_profile=threshold_profile,
    )

    prediction_rows: list[dict[str, Any]] = []
    by_capture_id = {case.capture_id: case for case in case_results}
    for capture in captures:
        capture_id = capture.capture_id or "capture"
        case = by_capture_id.get(capture_id)
        truth = infer_truth_label(capture, known_seed_ids, truth_source) or UNKNOWN_TRUTH
        predicted, confidence, decision = selected_prediction(rows, capture_id)
        correct = bool(truth != UNKNOWN_TRUTH and predicted == truth)
        prediction_rows.append(
            {
                "capture_id": capture_id,
                "source_file": capture.metadata.get("source_file", ""),
                "truth_label": truth,
                "predicted_label": predicted,
                "correct": correct,
                "confidence": confidence,
                "decision": decision,
                "core_winner": case.winner if case else "",
                "ranked_signature_ids": ",".join(case.ranked_signature_ids) if case else "",
            }
        )

    labels, matrix = build_confusion_matrix(prediction_rows)
    labeled_rows = [row for row in prediction_rows if row["truth_label"] != UNKNOWN_TRUTH]
    correct_count = sum(1 for row in labeled_rows if row["correct"])
    total_labeled = len(labeled_rows)
    per_truth: dict[str, dict[str, Any]] = defaultdict(lambda: {"total": 0, "correct": 0})
    for row in labeled_rows:
        truth = str(row["truth_label"])
        per_truth[truth]["total"] += 1
        per_truth[truth]["correct"] += int(bool(row["correct"]))

    summary = {
        "input_path": str(input_path),
        "total_captures": len(prediction_rows),
        "labeled_captures": total_labeled,
        "unlabeled_captures": len(prediction_rows) - total_labeled,
        "correct": correct_count,
        "accuracy": correct_count / total_labeled if total_labeled else None,
        "truth_source": truth_source,
        "threshold_profile": threshold_profile.to_dict(),
        "labels": labels,
        "per_truth": {
            truth: {
                "total": stats["total"],
                "correct": stats["correct"],
                "accuracy": stats["correct"] / stats["total"] if stats["total"] else None,
            }
            for truth, stats in sorted(per_truth.items())
        },
        "warnings": warnings,
        "registry_failures": registry_failures,
    }

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    write_csv(
        out_path / "predictions.csv",
        prediction_rows,
        [
            "capture_id",
            "source_file",
            "truth_label",
            "predicted_label",
            "correct",
            "confidence",
            "decision",
            "core_winner",
            "ranked_signature_ids",
        ],
    )
    write_confusion_matrix(out_path / "confusion_matrix.csv", labels, matrix)
    (out_path / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Gamma seed adapters over a folder of NPZ captures and output a confusion matrix."
    )
    parser.add_argument("input", help="Folder or single .npz capture to analyze")
    parser.add_argument("--out", default="outputs/confusion_matrix", help="Output folder")
    parser.add_argument("--registry-root", default=None, help="Repo root containing seed_manifest.json files")
    parser.add_argument("--threshold-profile", default=None, help="Threshold profile JSON path")
    parser.add_argument(
        "--truth-source",
        choices=["auto", "npz", "parent", "filename"],
        default="auto",
        help="How to find expected truth labels for matrix rows",
    )
    parser.add_argument("--max-cases", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_confusion_matrix(
        args.input,
        args.out,
        registry_root=args.registry_root,
        threshold_profile_path=args.threshold_profile,
        truth_source=args.truth_source,
        max_cases=args.max_cases,
    )
    accuracy = summary["accuracy"]
    accuracy_text = "n/a" if accuracy is None else f"{accuracy:.6f}"
    print(f"captured={summary['total_captures']} labeled={summary['labeled_captures']} accuracy={accuracy_text}")
    print(f"wrote {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
