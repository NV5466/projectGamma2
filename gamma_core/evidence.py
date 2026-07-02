from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
import hashlib
import json

import pandas as pd

from .runner import CaseRunResult
from .stats import (
    build_confusion_matrix,
    build_feature_stats,
    build_overlap_matrix,
    build_per_case_rows,
    build_reference_rows,
    build_reference_summary,
    build_signature_summary,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256_manifest(out_dir: Path) -> None:
    rows = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file() and path.name != "sha256_manifest.txt":
            rows.append(f"{sha256_file(path)} {path.relative_to(out_dir).as_posix()}")
    (out_dir / "sha256_manifest.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _result_to_jsonable(result) -> dict[str, Any]:
    return asdict(result)


def write_evidence_outputs(
    case_results: list[CaseRunResult],
    out_dir: str | Path,
    *,
    run_config: dict[str, Any] | None = None,
    signatures_failed_to_load: list[dict[str, str]] | None = None,
) -> list[str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    signatures_failed_to_load = signatures_failed_to_load or []
    run_config = run_config or {}

    per_case_df = pd.DataFrame(build_per_case_rows(case_results))
    reference_df = pd.DataFrame(build_reference_rows(case_results))
    signature_summary_df = build_signature_summary(per_case_df) if not per_case_df.empty else pd.DataFrame()
    reference_summary_df = build_reference_summary(reference_df)
    confusion_df = build_confusion_matrix(case_results)
    overlap_df = build_overlap_matrix(per_case_df) if not per_case_df.empty else pd.DataFrame()
    feature_stats_df = build_feature_stats(per_case_df) if not per_case_df.empty else pd.DataFrame()

    written: list[str] = []
    tables = {
        "per_case_signature_scores.csv": per_case_df,
        "reference_comparison.csv": reference_df,
        "signature_summary.csv": signature_summary_df,
        "overlap_matrix.csv": overlap_df,
        "feature_stats_by_signature.csv": feature_stats_df,
        "reference_summary.csv": reference_summary_df,
    }
    if not confusion_df.empty:
        tables["confusion_matrix.csv"] = confusion_df

    for name, table in tables.items():
        table.to_csv(out / name, index=False)
        written.append(name)

    with (out / "ranked_results.jsonl").open("w", encoding="utf-8") as handle:
        for case in case_results:
            payload = {
                "capture_id": case.capture_id,
                "truth_label": case.truth_label,
                "winner": case.winner,
                "decision": case.decision,
                "ranked_signature_ids": case.ranked_signature_ids,
                "ranked": [_result_to_jsonable(result) for result in case.results],
            }
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    written.append("ranked_results.jsonl")

    signature_error_counts: dict[str, int] = {}
    for case in case_results:
        for result in case.results:
            if result.errors:
                signature_error_counts[result.signature_id] = signature_error_counts.get(result.signature_id, 0) + 1

    campaign_summary = {
        "total_captures": len(case_results),
        "total_signatures": len(case_results[0].results) if case_results else 0,
        "truth_labels_present": any(case.truth_label for case in case_results),
        "winner_counts": per_case_df[per_case_df["is_winner"] == True]["signature_id"].value_counts().to_dict()
        if not per_case_df.empty
        else {},
        "signatures_loaded": sorted(per_case_df["signature_id"].unique().tolist()) if not per_case_df.empty else [],
        "signatures_failed_to_load": signatures_failed_to_load,
        "signature_error_counts": signature_error_counts,
        "output_files": sorted(written),
    }
    (out / "campaign_summary.json").write_text(json.dumps(campaign_summary, indent=2, sort_keys=True), encoding="utf-8")
    written.append("campaign_summary.json")

    (out / "run_config.json").write_text(json.dumps(run_config, indent=2, sort_keys=True), encoding="utf-8")
    written.append("run_config.json")

    write_sha256_manifest(out)
    written.append("sha256_manifest.txt")
    return sorted(written)
