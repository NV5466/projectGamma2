import json
from pathlib import Path

import pandas as pd

from gamma_app.runner import analyze_path


def test_gamma_app_runner_writes_usable_outputs(tmp_path: Path):
    out_dir = tmp_path / "analysis"
    run = analyze_path(
        "validation/fixtures/three_signature_smoke",
        out_dir,
        threshold_profile_path="configs/default_thresholds.yaml",
        max_cases=1,
    )

    assert len(run.case_results) == 1
    assert (out_dir / "campaign_results.csv").exists()
    assert (out_dir / "campaign_results.json").exists()
    assert (out_dir / "reports").exists()

    frame = pd.read_csv(out_dir / "campaign_results.csv")
    assert {"capture_id", "signature_id", "family", "confidence", "threshold", "evidence_summary"} <= set(frame.columns)
    payload = json.loads((out_dir / "campaign_results.json").read_text(encoding="utf-8"))
    assert payload["threshold_profile"]["name"] == "default"
    assert payload["captures"]
    assert list((out_dir / "reports").glob("*.md"))
