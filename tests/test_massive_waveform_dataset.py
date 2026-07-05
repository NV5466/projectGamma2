from pathlib import Path
import csv
import math

from gamma_app.registry import ALLOWED_FAMILIES, is_mechanical_only_id
from gamma_app.runner import analyze_path, validate_manifest
from scripts.generate_massive_waveform_dataset import generate_dataset, write_outputs, parse_args


def _generate(tmp_path: Path, sets_per_signature: int = 1):
    out = tmp_path / "massive"
    args = parse_args(
        [
            "--registry",
            "seed_registry.yaml",
            "--out",
            str(out),
            "--sets-per-signature",
            str(sets_per_signature),
            "--chunks-per-set",
            "10",
            "--seed",
            "1337",
        ]
    )
    rows = generate_dataset(registry_path=Path("seed_registry.yaml"), out_dir=out, sets_per_signature=sets_per_signature, seed=1337)
    write_outputs(out, rows, args)
    return out, rows


def test_smoke_dataset_distribution_and_manifest_files(tmp_path: Path):
    out, rows = _generate(tmp_path, sets_per_signature=1)
    signatures = {row["signature_id"] for row in rows}
    assert len(signatures) == 19
    assert len(rows) == 190
    assert all(row["family"] in ALLOWED_FAMILIES for row in rows)
    assert not any(is_mechanical_only_id(row["signature_id"]) for row in rows)

    for signature_id in signatures:
        sig_rows = [row for row in rows if row["signature_id"] == signature_id]
        assert len(sig_rows) == 10
        assert {row["set_index"] for row in sig_rows} == {0}
        assert sum(row["expected_fault_present"] for row in sig_rows) == 5
        assert sum(not row["expected_fault_present"] for row in sig_rows) == 5
        assert sum(row["expected_fault_present"] and row["noise_tier"] == "high" for row in sig_rows) == 2
        assert sum((not row["expected_fault_present"]) and row["noise_tier"] == "high" for row in sig_rows) == 2
        assert all(float(row["noise_scale"]) > 0 for row in sig_rows)
        base = float(sig_rows[0]["set_noise_scale"])
        for row in sig_rows:
            multiplier = 2.0 if row["noise_tier"] == "high" else 1.0
            assert math.isclose(float(row["noise_scale"]), base * multiplier, rel_tol=1e-12)
            assert (out / row["relative_path"]).exists()

    with (out / "dataset_manifest.csv").open(newline="", encoding="utf-8") as handle:
        manifest_rows = list(csv.DictReader(handle))
    assert len(manifest_rows) == len(rows)
    assert (out / "dataset_manifest.json").exists()
    assert (out / "generation_summary.json").exists()
    assert (out / "README.md").exists()


def test_default_dataset_counts_without_writing_all_binaries(tmp_path: Path):
    _out, rows = _generate(tmp_path, sets_per_signature=10)
    assert len(rows) == 1900
    for signature_id in {row["signature_id"] for row in rows}:
        sig_rows = [row for row in rows if row["signature_id"] == signature_id]
        assert len(sig_rows) == 100
        assert len({row["set_index"] for row in sig_rows}) == 10
    assert sum(row["expected_fault_present"] for row in rows) == 950
    assert sum(not row["expected_fault_present"] for row in rows) == 950
    assert sum(row["noise_tier"] == "normal" for row in rows) == 1140
    assert sum(row["noise_tier"] == "high" for row in rows) == 760
    assert sum(row["expected_fault_present"] and row["noise_tier"] == "high" for row in rows) == 380
    assert sum((not row["expected_fault_present"]) and row["noise_tier"] == "high" for row in rows) == 380


def test_runner_and_manifest_validation_process_smoke_dataset(tmp_path: Path):
    out, _rows = _generate(tmp_path, sets_per_signature=1)
    analysis_out = tmp_path / "analysis"
    run = analyze_path(out, analysis_out, max_cases=3)
    assert len(run.case_results) == 3
    assert (analysis_out / "campaign_results.csv").exists()

    validation_out = tmp_path / "validation"
    validate_manifest(out / "dataset_manifest.csv", validation_out)
    assert (validation_out / "validation_summary.csv").exists()
    assert (validation_out / "validation_summary.json").exists()
    assert (validation_out / "per_signature_metrics.csv").exists()
    assert (validation_out / "confusion_summary.csv").exists()
    assert (validation_out / "high_noise_performance.csv").exists()
    assert (validation_out / "normal_noise_performance.csv").exists()
    with (validation_out / "per_signature_metrics.csv").open(newline="", encoding="utf-8") as handle:
        metric_rows = list(csv.DictReader(handle))
    assert len(metric_rows) == 19
    assert {int(row["total_cases"]) for row in metric_rows} == {10}
