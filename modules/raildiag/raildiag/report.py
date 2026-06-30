from __future__ import annotations

import json
from pathlib import Path

from .metadata import metadata_warnings
from .models import AnalysisResult, Capture, Report
from .report_markdown import render_markdown_report
from .report_schema import build_report_document
from .report_text import render_text_report


def write_report(capture: Capture, results: list[AnalysisResult], warnings: list[str], output_dir: Path) -> Report:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_warnings = warnings + metadata_warnings(capture.metadata)
    document = build_report_document(capture, results, all_warnings, output_dir)

    text_path = output_dir / "report.txt"
    json_path = output_dir / "report.estat.json"
    markdown_path = output_dir / "report.md"

    text_path.write_text(render_text_report(document), encoding="utf-8")
    json_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown_report(document), encoding="utf-8")

    return Report(
        capture=capture,
        results=results,
        warnings=all_warnings,
        output_dir=output_dir,
        text_path=text_path,
        json_path=json_path,
        markdown_path=markdown_path,
    )


def write_markdown_report(capture: Capture, results: list[AnalysisResult], warnings: list[str], output_dir: Path) -> Report:
    return write_report(capture, results, warnings, output_dir)
