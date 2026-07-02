import json
from pathlib import Path

import pytest

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
