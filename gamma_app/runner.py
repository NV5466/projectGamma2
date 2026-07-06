from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import argparse
import csv
import json
import subprocess
import sys
import time
import uuid

from gamma_core.runner import CaseRunResult, run_campaign

from .io import load_captures
from .registry import load_available_signatures, validate_registry_families
from .reporting import write_campaign_outputs
from .results import result_rows
from .runtime import default_registry_root, default_threshold_profile_path
from .threshold_profiles import ThresholdProfile, load_threshold_profile
from .validation_store import ValidationCase, ValidationStore
from .waveform_sets import import_waveforms


DEFAULT_INCLUDE_STATUS: set[str] | None = None


@dataclass
class GammaRun:
    case_results: list[CaseRunResult]
    output_files: dict[str, Path]
    warnings: list[str]
    registry_failures: list[dict[str, str]]
    threshold_profile: ThresholdProfile
    session_id: str


def analyze_path(
    input_path: str | Path,
    out_dir: str | Path,
    *,
    registry_root: str | Path | None = None,
    threshold_profile_path: str | Path | None = None,
    include_status: set[str] | None = None,
    family_filter: set[str] | None = None,
    seed_filter: set[str] | None = None,
    max_cases: int | None = None,
    mode: str = "diagnostic",
) -> GammaRun:
    registry_root = registry_root or default_registry_root()
    threshold_profile = load_threshold_profile(threshold_profile_path or default_threshold_profile_path())
    signatures, registry_failures = load_available_signatures(registry_root, include_status=include_status)
    if family_filter:
        signatures = [spec for spec in signatures if spec.family in family_filter]
    if seed_filter:
        signatures = [spec for spec in signatures if spec.seed_id in seed_filter]
    if not signatures:
        raise RuntimeError("no electrical signatures loaded")

    captures, warnings = load_captures(input_path, max_cases=max_cases)
    if not captures:
        raise RuntimeError("no supported captures loaded")

    case_results = run_campaign(captures, signatures)
    family_by_signature = {spec.seed_id: spec.family for spec in signatures}
    session_id = str(uuid.uuid4())
    run_config: dict[str, Any] = {
        "mode": mode,
        "input_path": str(input_path),
        "registry_root": str(registry_root),
        "threshold_profile": threshold_profile.to_dict(),
        "include_status": sorted(include_status) if include_status else None,
        "family_filter": sorted(family_filter or []),
        "seed_filter": sorted(seed_filter or []),
        "max_cases": max_cases,
        "session_id": session_id,
        "generated_at_unix": time.time(),
    }
    output_files = write_campaign_outputs(
        case_results,
        out_dir,
        family_by_signature=family_by_signature,
        threshold_profile=threshold_profile,
        warnings=warnings,
        registry_failures=registry_failures,
        run_config=run_config,
    )
    return GammaRun(
        case_results=case_results,
        output_files=output_files,
        warnings=warnings,
        registry_failures=registry_failures,
        threshold_profile=threshold_profile,
        session_id=session_id,
    )


def add_capture_to_dataset(
    dataset: str | Path,
    source_file: str | Path,
    *,
    capture_id: str | None = None,
    seed_label: str | None = None,
    no_fault_control: bool = False,
    channel_labels: str | None = None,
    sample_rate_hz: float | None = None,
    capture_duration_s: float | None = None,
    notes: str | None = None,
    operator_tags: str | None = None,
    environment_notes: str | None = None,
) -> None:
    source = Path(source_file)
    store = ValidationStore(dataset)
    try:
        store.add_capture(
            ValidationCase(
                capture_id=capture_id or source.stem,
                source_file_path=str(source),
                seed_label=seed_label,
                no_fault_control=no_fault_control,
                channel_labels=channel_labels,
                sample_rate_hz=sample_rate_hz,
                capture_duration_s=capture_duration_s,
                notes=notes,
                operator_tags=operator_tags,
                environment_notes=environment_notes,
            )
        )
    finally:
        store.close()


def validate_dataset(
    dataset: str | Path,
    out_dir: str | Path,
    *,
    registry_root: str | Path | None = None,
    threshold_profile_path: str | Path | None = None,
) -> GammaRun:
    registry_root = registry_root or default_registry_root()
    store = ValidationStore(dataset)
    try:
        captures = store.list_captures()
        if not captures:
            raise RuntimeError(f"validation dataset has no captures: {dataset}")
        temp_dir = Path(out_dir) / "_validation_inputs.json"
        temp_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_dir.write_text(json.dumps([dict(row) for row in captures], indent=2), encoding="utf-8")

        # Run each source path through the same wrapper, then merge rows into one validation session.
        all_case_results: list[CaseRunResult] = []
        all_warnings: list[str] = []
        registry_failures: list[dict[str, str]] = []
        threshold_profile = load_threshold_profile(threshold_profile_path or default_threshold_profile_path())
        signatures, registry_failures = load_available_signatures(registry_root)
        family_by_signature = {spec.seed_id: spec.family for spec in signatures}
        for row in captures:
            loaded, warnings = load_captures(row["source_file_path"], max_cases=1)
            all_warnings.extend(warnings)
            for capture in loaded:
                capture.capture_id = row["capture_id"]
                capture.truth_label = None if row["no_fault_control"] else row["seed_label"]
            all_case_results.extend(run_campaign(loaded, signatures))

        session_id = str(uuid.uuid4())
        output_files = write_campaign_outputs(
            all_case_results,
            out_dir,
            family_by_signature=family_by_signature,
            threshold_profile=threshold_profile,
            warnings=all_warnings,
            registry_failures=registry_failures,
            run_config={
                "mode": "validation",
                "dataset": str(dataset),
                "registry_root": str(registry_root),
                "threshold_profile": threshold_profile.to_dict(),
                "session_id": session_id,
            },
        )
        rows = result_rows(
            all_case_results,
            family_by_signature=family_by_signature,
            threshold_profile=threshold_profile,
        )
        store.record_result_rows(rows, session_id=session_id)
        summary_csv, summary_json = store.export_summary(Path(out_dir) / "validation_summary", session_id=session_id)
        output_files["validation_summary_csv"] = summary_csv
        output_files["validation_summary_json"] = summary_json
        return GammaRun(
            case_results=all_case_results,
            output_files=output_files,
            warnings=all_warnings,
            registry_failures=registry_failures,
            threshold_profile=threshold_profile,
            session_id=session_id,
        )
    finally:
        store.close()


def validate_manifest(
    manifest: str | Path,
    out_dir: str | Path,
    *,
    registry_root: str | Path | None = None,
    threshold_profile_path: str | Path | None = None,
) -> GammaRun:
    registry_root = registry_root or default_registry_root()
    manifest_path = Path(manifest)
    manifest_rows = _read_csv_dicts(manifest_path)
    if not manifest_rows:
        raise RuntimeError(f"manifest has no rows: {manifest_path}")
    threshold_profile = load_threshold_profile(threshold_profile_path or default_threshold_profile_path())
    signatures, registry_failures = load_available_signatures(registry_root)
    family_by_signature = {spec.seed_id: spec.family for spec in signatures}
    captures = []
    warnings: list[str] = []
    manifest_root = manifest_path.parent
    manifest_by_capture: dict[str, dict[str, Any]] = {}
    for row in manifest_rows:
        file_path = manifest_root / str(row["relative_path"])
        loaded, load_warnings = load_captures(file_path, max_cases=1)
        warnings.extend(load_warnings)
        if not loaded:
            continue
        capture = loaded[0]
        capture.capture_id = str(row["capture_id"])
        expected = _to_bool(row.get("expected_fault_present"))
        capture.truth_label = str(row["signature_id"]) if expected else None
        captures.append(capture)
        manifest_by_capture[capture.capture_id or ""] = row
    if not captures:
        raise RuntimeError("no captures from manifest could be loaded")

    case_results = run_campaign(captures, signatures)
    session_id = str(uuid.uuid4())
    output_files = write_campaign_outputs(
        case_results,
        out_dir,
        family_by_signature=family_by_signature,
        threshold_profile=threshold_profile,
        warnings=warnings,
        registry_failures=registry_failures,
        run_config={
            "mode": "manifest_validation",
            "manifest": str(manifest_path),
            "registry_root": str(registry_root),
            "threshold_profile": threshold_profile.to_dict(),
            "session_id": session_id,
        },
    )
    rows = result_rows(case_results, family_by_signature=family_by_signature, threshold_profile=threshold_profile)
    metric_outputs = write_manifest_validation_outputs(
        rows,
        manifest_by_capture,
        Path(out_dir),
    )
    output_files.update(metric_outputs)
    return GammaRun(
        case_results=case_results,
        output_files=output_files,
        warnings=warnings,
        registry_failures=registry_failures,
        threshold_profile=threshold_profile,
        session_id=session_id,
    )


def write_manifest_validation_outputs(
    result_rows_: list[dict[str, Any]],
    manifest_by_capture: dict[str, dict[str, Any]],
    out_dir: Path,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    primary_by_capture = {
        str(row["capture_id"]): str(row["signature_id"])
        for row in result_rows_
        if row.get("is_primary_diagnosis")
    }
    capture_rows = []
    for capture_id, meta in sorted(manifest_by_capture.items()):
        capture_rows.append(
            {
                "capture_id": capture_id,
                "signature_id": meta.get("signature_id", ""),
                "family": meta.get("family", ""),
                "expected_fault_present": _to_bool(meta.get("expected_fault_present")),
                "noise_tier": meta.get("noise_tier", ""),
                "predicted_signature_id": primary_by_capture.get(capture_id, ""),
            }
        )
    for row in result_rows_:
        meta = manifest_by_capture.get(str(row["capture_id"]), {})
        row["manifest_signature_id"] = meta.get("signature_id", "")
        row["manifest_family"] = meta.get("family", "")
        row["expected_fault_present"] = _to_bool(meta.get("expected_fault_present"))
        row["noise_tier"] = meta.get("noise_tier", "")

    per_signature = _capture_metric_rows(capture_rows, group_key="signature_id")
    validation_summary = _capture_metric_rows(capture_rows, group_key=None)
    high_noise = _capture_metric_rows([row for row in capture_rows if row.get("noise_tier") == "high"], group_key="signature_id")
    normal_noise = _capture_metric_rows([row for row in capture_rows if row.get("noise_tier") == "normal"], group_key="signature_id")
    family_rows = _capture_family_accuracy_rows(capture_rows)
    confusion_rows = _capture_confusion_rows(capture_rows)

    paths = {
        "validation_summary_csv": out_dir / "validation_summary.csv",
        "validation_summary_json": out_dir / "validation_summary.json",
        "per_signature_metrics_csv": out_dir / "per_signature_metrics.csv",
        "confusion_summary_csv": out_dir / "confusion_summary.csv",
        "high_noise_performance_csv": out_dir / "high_noise_performance.csv",
        "normal_noise_performance_csv": out_dir / "normal_noise_performance.csv",
        "family_performance_csv": out_dir / "family_performance.csv",
        "validation_report_md": out_dir / "README.md",
    }
    _write_csv(paths["validation_summary_csv"], validation_summary)
    paths["validation_summary_json"].write_text(json.dumps(validation_summary, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(paths["per_signature_metrics_csv"], per_signature)
    _write_csv(paths["confusion_summary_csv"], confusion_rows)
    _write_csv(paths["high_noise_performance_csv"], high_noise)
    _write_csv(paths["normal_noise_performance_csv"], normal_noise)
    _write_csv(paths["family_performance_csv"], family_rows)
    paths["validation_report_md"].write_text(_validation_report(validation_summary, per_signature), encoding="utf-8")
    return paths


def _capture_metric_rows(rows: list[dict[str, Any]], *, group_key: str | None) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {"overall": rows} if group_key is None else {}
    if group_key is not None:
        for row in rows:
            groups.setdefault(str(row.get(group_key, "")), []).append(row)
    output = []
    for group, group_rows in sorted(groups.items()):
        tp = fp = tn = fn = 0
        positives = negatives = 0
        for row in group_rows:
            expected = bool(row.get("expected_fault_present"))
            predicted = row.get("predicted_signature_id") == row.get("signature_id")
            if expected:
                positives += 1
            else:
                negatives += 1
            if predicted and expected:
                tp += 1
            elif predicted and not expected:
                fp += 1
            elif (not predicted) and expected:
                fn += 1
            else:
                tn += 1
        recall = _safe_div(tp, tp + fn)
        specificity = _safe_div(tn, tn + fp)
        output.append(
            {
                "group": group,
                "total_cases": len(group_rows),
                "positives": positives,
                "negatives": negatives,
                "true_positives": tp,
                "false_positives": fp,
                "true_negatives": tn,
                "false_negatives": fn,
                "precision": _safe_div(tp, tp + fp),
                "recall": recall,
                "sensitivity": recall,
                "specificity": specificity,
                "balanced_accuracy": (recall + specificity) / 2.0,
                "accuracy": _safe_div(tp + tn, tp + fp + tn + fn),
            }
        )
    return output


def _capture_family_accuracy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for family in sorted({str(row.get("family", "")) for row in rows}):
        family_rows = [row for row in rows if row.get("family") == family]
        metrics = _capture_metric_rows(family_rows, group_key=None)[0]
        metrics["group"] = family
        output.append(metrics)
    return output


def _capture_confusion_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str], int] = {}
    for meta in rows:
        expected = meta.get("signature_id") if meta.get("expected_fault_present") else f"{meta.get('signature_id')}:negative_control"
        predicted = meta.get("predicted_signature_id") or "no_primary"
        counts[(str(expected), str(predicted))] = counts.get((str(expected), str(predicted)), 0) + 1
    return [{"expected": key[0], "predicted": key[1], "count": value} for key, value in sorted(counts.items())]


def _validation_report(validation_summary: list[dict[str, Any]], per_signature: list[dict[str, Any]]) -> str:
    overall = validation_summary[0] if validation_summary else {}
    return "\n".join(
        [
            "# Gamma Manifest Validation Report",
            "",
            f"- Total result rows: {overall.get('total_cases', 0)}",
            f"- Precision: {overall.get('precision', 0):.4f}",
            f"- Recall/sensitivity: {overall.get('recall', 0):.4f}",
            f"- Specificity: {overall.get('specificity', 0):.4f}",
            f"- Balanced accuracy: {overall.get('balanced_accuracy', 0):.4f}",
            "",
            "Per-signature details are in `per_signature_metrics.csv`.",
        ]
    )


def _read_csv_dicts(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row.keys()}) if rows else ["group"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _safe_div(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def launch_gui() -> int:
    return subprocess.call([sys.executable, "-m", "gamma_app.gui"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gamma application wrapper")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="run diagnostics on a capture file or folder")
    analyze.add_argument("--input", required=True)
    analyze.add_argument("--out", required=True)
    analyze.add_argument("--registry-root")
    analyze.add_argument("--threshold-profile")
    analyze.add_argument("--family", action="append", default=[])
    analyze.add_argument("--seed", action="append", default=[])
    analyze.add_argument("--max-cases", type=int)

    add = sub.add_parser("dataset-add", help="add a capture to a validation dataset")
    add.add_argument("--dataset", required=True)
    add.add_argument("--source-file", required=True)
    add.add_argument("--capture-id")
    add.add_argument("--seed-label")
    add.add_argument("--no-fault-control", action="store_true")
    add.add_argument("--channel-labels")
    add.add_argument("--sample-rate-hz", type=float)
    add.add_argument("--capture-duration-s", type=float)
    add.add_argument("--notes")
    add.add_argument("--operator-tags")
    add.add_argument("--environment-notes")

    validate = sub.add_parser("validate", help="run analyzers against a validation dataset or manifest")
    validate.add_argument("--dataset")
    validate.add_argument("--manifest")
    validate.add_argument("--out", required=True)
    validate.add_argument("--registry-root")
    validate.add_argument("--threshold-profile")

    upload = sub.add_parser("waveform-import", help="import capture files/folders into a Gamma waveform set")
    upload.add_argument("--set-id", required=True)
    upload.add_argument("--source", action="append", required=True)
    upload.add_argument("--library-root", default="waveform_sets")
    upload.add_argument("--notes", default="")

    sub.add_parser("gui", help="launch the Tkinter GUI")
    sub.add_parser("check-registry", help="validate seed registry families and mechanical exclusions")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "analyze":
        run = analyze_path(
            args.input,
            args.out,
            registry_root=args.registry_root,
            threshold_profile_path=args.threshold_profile,
            family_filter=set(args.family) if args.family else None,
            seed_filter=set(args.seed) if args.seed else None,
            max_cases=args.max_cases,
        )
        print(json.dumps({k: str(v) for k, v in run.output_files.items()}, indent=2, sort_keys=True))
        return 0
    if args.command == "dataset-add":
        add_capture_to_dataset(
            args.dataset,
            args.source_file,
            capture_id=args.capture_id,
            seed_label=args.seed_label,
            no_fault_control=args.no_fault_control,
            channel_labels=args.channel_labels,
            sample_rate_hz=args.sample_rate_hz,
            capture_duration_s=args.capture_duration_s,
            notes=args.notes,
            operator_tags=args.operator_tags,
            environment_notes=args.environment_notes,
        )
        print(f"added capture to {args.dataset}")
        return 0
    if args.command == "validate":
        if args.manifest:
            run = validate_manifest(
                args.manifest,
                args.out,
                registry_root=args.registry_root,
                threshold_profile_path=args.threshold_profile,
            )
        elif args.dataset:
            run = validate_dataset(
                args.dataset,
                args.out,
                registry_root=args.registry_root,
                threshold_profile_path=args.threshold_profile,
            )
        else:
            raise SystemExit("validate requires --dataset or --manifest")
        print(json.dumps({k: str(v) for k, v in run.output_files.items()}, indent=2, sort_keys=True))
        return 0
    if args.command == "waveform-import":
        waveform_set, imported, warnings = import_waveforms(
            args.source,
            args.set_id,
            library_root=args.library_root,
            notes=args.notes,
        )
        print(
            json.dumps(
                {
                    "waveform_set": str(waveform_set.root),
                    "captures_dir": str(waveform_set.captures_dir),
                    "manifest": str(waveform_set.manifest_path),
                    "imported_count": len(imported),
                    "warnings": warnings,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "gui":
        return launch_gui()
    if args.command == "check-registry":
        errors = validate_registry_families()
        if errors:
            print("\n".join(errors))
            return 1
        print("registry families ok")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
