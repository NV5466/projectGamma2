from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import argparse
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
from .threshold_profiles import ThresholdProfile, load_threshold_profile
from .validation_store import ValidationCase, ValidationStore
from .waveform_sets import import_waveforms


DEFAULT_INCLUDE_STATUS = {"implemented", "implemented_synthetic", "validated", "synthetic_research_prototype"}


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
    registry_root: str | Path = ".",
    threshold_profile_path: str | Path | None = "configs/default_thresholds.yaml",
    include_status: set[str] | None = None,
    family_filter: set[str] | None = None,
    seed_filter: set[str] | None = None,
    max_cases: int | None = None,
    mode: str = "diagnostic",
) -> GammaRun:
    threshold_profile = load_threshold_profile(threshold_profile_path)
    signatures, registry_failures = load_available_signatures(
        registry_root,
        include_status=include_status or DEFAULT_INCLUDE_STATUS,
    )
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
        "include_status": sorted(include_status or DEFAULT_INCLUDE_STATUS),
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
    registry_root: str | Path = ".",
    threshold_profile_path: str | Path | None = "configs/default_thresholds.yaml",
) -> GammaRun:
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
        threshold_profile = load_threshold_profile(threshold_profile_path)
        signatures, registry_failures = load_available_signatures(registry_root, include_status=DEFAULT_INCLUDE_STATUS)
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


def launch_gui() -> int:
    return subprocess.call([sys.executable, "-m", "gamma_app.gui"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gamma application wrapper")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="run diagnostics on a capture file or folder")
    analyze.add_argument("--input", required=True)
    analyze.add_argument("--out", required=True)
    analyze.add_argument("--registry-root", default=".")
    analyze.add_argument("--threshold-profile", default="configs/default_thresholds.yaml")
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

    validate = sub.add_parser("validate", help="run analyzers against a validation dataset")
    validate.add_argument("--dataset", required=True)
    validate.add_argument("--out", required=True)
    validate.add_argument("--registry-root", default=".")
    validate.add_argument("--threshold-profile", default="configs/default_thresholds.yaml")

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
        run = validate_dataset(
            args.dataset,
            args.out,
            registry_root=args.registry_root,
            threshold_profile_path=args.threshold_profile,
        )
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
