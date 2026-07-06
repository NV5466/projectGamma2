from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import importlib
import json
import logging

from .schema import CaptureRecord, SignatureResult

LOG = logging.getLogger(__name__)


@dataclass
class SignatureSpec:
    seed_id: str
    family: str
    status: str
    validation_status: str
    entrypoint: str
    manifest_path: Path
    metadata: dict[str, Any]
    analyze: Callable[[CaptureRecord], SignatureResult]


def import_entrypoint(entrypoint: str) -> Callable[[CaptureRecord], SignatureResult]:
    if ":" not in entrypoint:
        raise ValueError(f"entrypoint must be module:function, got {entrypoint!r}")
    module_name, func_name = entrypoint.split(":", 1)
    mod = importlib.import_module(module_name)
    return getattr(mod, func_name)


def discover_manifests(root: str | Path) -> list[Path]:
    root = Path(root)
    excluded = {"dist", "build", "__pycache__", ".pytest_cache"}
    manifests: list[Path] = []
    for manifest in root.rglob("seed_manifest.json"):
        parts = {part.lower() for part in manifest.parts}
        if parts & excluded:
            continue
        manifests.append(manifest)
    return sorted(manifests)


def load_signature_spec(manifest_path: str | Path) -> SignatureSpec:
    path = Path(manifest_path)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    required = ["seed_id", "family", "status", "validation_status", "entrypoint"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"{path} missing required manifest keys: {missing}")
    analyze = import_entrypoint(data["entrypoint"])
    return SignatureSpec(
        seed_id=data["seed_id"],
        family=data["family"],
        status=data["status"],
        validation_status=data["validation_status"],
        entrypoint=data["entrypoint"],
        manifest_path=path,
        metadata=data,
        analyze=analyze,
    )


def load_registry(
    root: str | Path,
    *,
    include_status: set[str] | None = None,
) -> tuple[list[SignatureSpec], list[dict[str, str]]]:
    specs: list[SignatureSpec] = []
    failures: list[dict[str, str]] = []
    for manifest in discover_manifests(root):
        try:
            spec = load_signature_spec(manifest)
        except Exception as exc:
            failures.append({"manifest": str(manifest), "error": repr(exc)})
            LOG.warning("failed to load %s: %r", manifest, exc)
            continue
        if include_status and spec.status not in include_status:
            continue
        specs.append(spec)
    return specs, failures
