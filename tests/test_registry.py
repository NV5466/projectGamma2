import json
from pathlib import Path

import numpy as np
import pytest

from gamma_app.registry import load_available_signatures
from gamma_core.schema import CaptureRecord
from gamma_core.registry import discover_manifests, load_registry, load_signature_spec


def test_manifest_discovery_finds_temp_manifest(tmp_path: Path):
    manifest = tmp_path / "seed_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "seed_id": "fake",
                "family": "test",
                "status": "implemented",
                "validation_status": "test",
                "entrypoint": "tests.test_registry:fake_analyze",
            }
        ),
        encoding="utf-8",
    )
    assert discover_manifests(tmp_path) == [manifest]


def fake_analyze(_capture):
    raise RuntimeError("not called")


def test_missing_required_keys_fails(tmp_path: Path):
    manifest = tmp_path / "seed_manifest.json"
    manifest.write_text(json.dumps({"seed_id": "bad"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_signature_spec(manifest)


def test_entrypoint_import_works(tmp_path: Path):
    manifest = tmp_path / "seed_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "seed_id": "fake",
                "family": "test",
                "status": "implemented",
                "validation_status": "test",
                "entrypoint": "tests.test_registry:fake_analyze",
            }
        ),
        encoding="utf-8",
    )
    assert load_signature_spec(manifest).analyze is fake_analyze


def test_bad_entrypoint_reports_failure(tmp_path: Path):
    manifest = tmp_path / "seed_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "seed_id": "bad",
                "family": "test",
                "status": "implemented",
                "validation_status": "test",
                "entrypoint": "missing.module:analyze",
            }
        ),
        encoding="utf-8",
    )
    specs, failures = load_registry(tmp_path)
    assert specs == []
    assert failures


def test_all_registered_electrical_seeds_are_executable():
    specs, failures = load_available_signatures(Path("."))
    assert not failures
    assert len(specs) == 19
    assert len({spec.seed_id for spec in specs}) == 19

    t = np.linspace(0.0, 1.0, 256, endpoint=False)
    primary = np.sin(2 * np.pi * 5.0 * t) + 0.05 * np.sin(2 * np.pi * 40.0 * t)
    reference = np.sin(2 * np.pi * 5.0 * t)
    capture = CaptureRecord(
        sample_rate_hz=256.0,
        primary=primary,
        secondary=reference,
        references={"secondary": reference},
        time_s=t,
        capture_id="smoke",
        metadata={"reference_modes": {"secondary": "voltage"}},
    )
    for spec in specs:
        result = spec.analyze(capture)
        assert result.signature_id == spec.seed_id
        result.validate()
