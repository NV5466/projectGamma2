from __future__ import annotations

from pathlib import Path
from typing import Any
import csv
import html
import json

from gamma_core.runner import CaseRunResult

from .results import campaign_json, result_rows
from .threshold_profiles import ThresholdProfile


def write_campaign_outputs(
    case_results: list[CaseRunResult],
    out_dir: str | Path,
    *,
    family_by_signature: dict[str, str],
    threshold_profile: ThresholdProfile,
    warnings: list[str],
    registry_failures: list[dict[str, str]],
    run_config: dict[str, Any],
) -> dict[str, Path]:
    out = Path(out_dir)
    reports_dir = out / "reports"
    out.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    rows = result_rows(case_results, family_by_signature=family_by_signature, threshold_profile=threshold_profile)
    csv_path = out / "campaign_results.csv"
    json_path = out / "campaign_results.json"
    config_path = out / "run_config.json"
    _write_csv(csv_path, rows)
    json_path.write_text(
        json.dumps(
            campaign_json(
                case_results,
                family_by_signature=family_by_signature,
                threshold_profile=threshold_profile,
                warnings=warnings,
                registry_failures=registry_failures,
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    config_path.write_text(json.dumps(run_config, indent=2, sort_keys=True), encoding="utf-8")

    for case in case_results:
        case_rows = [row for row in rows if row["capture_id"] == case.capture_id]
        report_text = render_markdown_report(case.capture_id, case_rows, threshold_profile=threshold_profile)
        (reports_dir / f"{_safe_name(case.capture_id)}.md").write_text(report_text, encoding="utf-8")
        (reports_dir / f"{_safe_name(case.capture_id)}.html").write_text(markdown_to_basic_html(report_text), encoding="utf-8")

    return {
        "campaign_results_csv": csv_path,
        "campaign_results_json": json_path,
        "run_config_json": config_path,
        "reports_dir": reports_dir,
    }


def render_markdown_report(
    capture_id: str,
    rows: list[dict[str, Any]],
    *,
    threshold_profile: ThresholdProfile,
) -> str:
    selected = [row for row in rows if row["is_selected"]]
    secondary = [row for row in rows if row["candidate_role"] == "secondary_candidate"]
    conflict_warnings = sorted({row["conflict_warning"] for row in rows if row["conflict_warning"]})
    lines = [
        f"# Gamma Diagnostic Report: {capture_id}",
        "",
        f"- Threshold profile: `{threshold_profile.name}`",
        f"- Candidate signatures evaluated: {len(rows)}",
        f"- Primary diagnosis: `{selected[0]['signature_id']}`" if selected else "- Primary diagnosis: `none`",
        f"- Secondary candidates: {', '.join(row['signature_id'] for row in secondary) if secondary else 'none'}",
        f"- Multi-match ambiguity: {'yes' if any(row['multi_match_ambiguity'] for row in rows) else 'no'}",
    ]
    if conflict_warnings:
        lines.extend([f"- Warning: {warning}" for warning in conflict_warnings])
    lines.extend(
        [
            "",
            "## Top Detection Summary",
            "",
        ]
    )
    if selected:
        row = selected[0]
        lines.extend(
            [
                f"- Signature: `{row['signature_id']}`",
                f"- Family: `{row['family']}`",
                f"- Confidence: {row['confidence']:.3f}",
                f"- Diagnostic score: {row['diagnostic_score']:.3f}",
                f"- Required/reference channel status: {row['required_reference_status']}",
                f"- Recommended next check: {row['recommended_next_check']}",
            ]
        )
    else:
        lines.append("- No primary diagnosis met threshold and reference-evidence requirements.")
    lines.extend(
        [
            "",
            "## Ranked Results",
            "",
            "| rank | role | signature_id | family | confidence | diagnostic_score | threshold | reference_status | decision |",
            "|---:|---|---|---|---:|---:|---:|---|---|",
        ]
    )
    for row in sorted(rows, key=lambda item: item["rank"]):
        lines.append(
            "| {rank} | {candidate_role} | {signature_id} | {family} | {confidence:.3f} | {diagnostic_score:.3f} | {threshold:.3f} | {required_reference_status} | {decision} |".format(
                **row
            )
        )
    lines.extend(["", "## Evidence And Next Checks", ""])
    for row in sorted(rows, key=lambda item: item["rank"]):
        lines.extend(
            [
                f"### {row['signature_id']}",
                "",
                f"- Confidence: {row['confidence']:.3f}",
                f"- Required/reference channel status: {row['required_reference_status']}",
                f"- Evidence: {row['evidence_summary'] or 'No positive evidence recorded.'}",
                f"- Warnings: {row['warnings'] or 'None'}",
                f"- Recommended next check: {row['recommended_next_check']}",
                f"- Feature values: `{row['feature_values_json']}`",
                "",
            ]
        )
    return "\n".join(lines)


def markdown_to_basic_html(markdown_text: str) -> str:
    body_lines = []
    for line in markdown_text.splitlines():
        escaped = html.escape(line)
        if line.startswith("# "):
            body_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            body_lines.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("- "):
            body_lines.append(f"<li>{html.escape(line[2:])}</li>")
        elif line.startswith("|"):
            body_lines.append(f"<pre>{escaped}</pre>")
        elif line:
            body_lines.append(f"<p>{escaped}</p>")
        else:
            body_lines.append("")
    return "<!doctype html><html><head><meta charset='utf-8'><title>Gamma Report</title></head><body>" + "\n".join(body_lines) + "</body></html>"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)[:120] or "capture"
