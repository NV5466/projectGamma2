from pathlib import Path

from gamma_app.runner import analyze_path
from gamma_app.waveform_sets import import_waveforms, list_waveform_sets, read_manifest, sanitize_set_id


def test_import_waveforms_creates_definitive_set_structure(tmp_path: Path):
    library = tmp_path / "waveform_sets"
    waveform_set, imported, warnings = import_waveforms(
        ["validation/fixtures/three_signature_smoke/case_001_relay_kick.npz"],
        "Bench Run 001",
        library_root=library,
        notes="bench notes",
    )

    assert warnings == []
    assert waveform_set.set_id == "Bench_Run_001"
    assert waveform_set.captures_dir.exists()
    assert waveform_set.manifest_path.exists()
    assert waveform_set.notes_path.exists()
    assert len(imported) == 1
    assert (waveform_set.root / imported[0]["stored_path"]).exists()

    manifest = read_manifest(waveform_set.manifest_path)
    assert manifest["schema"] == "gamma.waveform_set.v1"
    assert manifest["capture_count"] == 1
    assert manifest["captures"][0]["original_path"].endswith("case_001_relay_kick.npz")
    assert list_waveform_sets(library)[0].set_id == "Bench_Run_001"


def test_analyze_path_accepts_imported_waveform_set(tmp_path: Path):
    library = tmp_path / "waveform_sets"
    waveform_set, _imported, _warnings = import_waveforms(
        ["validation/fixtures/three_signature_smoke/case_001_relay_kick.npz"],
        "app upload",
        library_root=library,
    )
    out_dir = tmp_path / "analysis"
    run = analyze_path(waveform_set.captures_dir, out_dir)

    assert len(run.case_results) == 1
    assert (out_dir / "campaign_results.csv").exists()


def test_sanitize_set_id_keeps_upload_paths_predictable():
    assert sanitize_set_id(" my bench/run 001 ") == "my_bench_run_001"
