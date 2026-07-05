from pathlib import Path

from gamma_app.runner import add_capture_to_dataset, validate_dataset
from gamma_app.validation_store import ValidationCase, ValidationStore


def test_validation_store_adds_capture_and_summarizes_metrics(tmp_path: Path):
    db_path = tmp_path / "validation.db"
    store = ValidationStore(db_path)
    try:
        store.add_capture(
            ValidationCase(
                capture_id="case_a",
                source_file_path="validation/fixtures/three_signature_smoke/case_001_relay_kick.npz",
                seed_label="relay_coil_inductive_kick",
            )
        )
        session = store.record_result_rows(
            [
                {
                    "capture_id": "case_a",
                    "truth_label": "relay_coil_inductive_kick",
                    "signature_id": "relay_coil_inductive_kick",
                    "family": "switching_emc",
                    "confidence": 0.9,
                    "threshold": 0.5,
                    "raw_matched": True,
                    "threshold_pass": True,
                    "threshold_profile": "default",
                },
                {
                    "capture_id": "case_a",
                    "truth_label": "relay_coil_inductive_kick",
                    "signature_id": "missed_short_pulse",
                    "family": "digital_timing",
                    "confidence": 0.1,
                    "threshold": 0.5,
                    "raw_matched": False,
                    "threshold_pass": False,
                    "threshold_profile": "default",
                },
            ],
            session_id="session_a",
        )
        summary = store.summarize_session(session)
    finally:
        store.close()

    relay = next(row for row in summary if row["signature_id"] == "relay_coil_inductive_kick")
    assert relay["TP"] == 1
    assert relay["precision"] == 1.0


def test_validate_dataset_writes_validation_summary(tmp_path: Path):
    db_path = tmp_path / "validation.db"
    out_dir = tmp_path / "validation_out"
    add_capture_to_dataset(
        db_path,
        "validation/fixtures/three_signature_smoke/case_001_relay_kick.npz",
        capture_id="case_a",
        seed_label="relay_coil_inductive_kick",
    )
    run = validate_dataset(db_path, out_dir)
    assert len(run.case_results) == 1
    assert (out_dir / "validation_summary.csv").exists()
    assert (out_dir / "validation_summary.json").exists()
