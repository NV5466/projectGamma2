from pathlib import Path

from gamma_app.runner import analyze_path


def test_report_exports_include_markdown_and_html(tmp_path: Path):
    out_dir = tmp_path / "analysis"
    analyze_path("validation/fixtures/three_signature_smoke/case_001_relay_kick.npz", out_dir)
    reports = out_dir / "reports"
    assert list(reports.glob("*.md"))
    assert list(reports.glob("*.html"))
    report_text = next(reports.glob("*.md")).read_text(encoding="utf-8")
    assert "Recommended next check" in report_text
    assert "Ranked Results" in report_text
