from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from gamma_core.registry import SignatureSpec, load_registry


ALLOWED_FAMILIES = {"power_quality", "switching_emc", "digital_timing", "measurement_artifact"}
MECHANICAL_ONLY_PATTERNS = [
    "unspecified_rotational_unbalance",
    "unspecified_bearing_fault",
    "unspecified_gear_fault",
    "bearing_fault",
    "broken_rotor",
    "rotor_bar",
    "rotating_machine",
]


def load_available_signatures(
    root: str | Path = ".",
    *,
    include_status: set[str] | None = None,
) -> tuple[list[SignatureSpec], list[dict[str, str]]]:
    specs, failures = load_registry(root, include_status=include_status)
    electrical_specs = [spec for spec in specs if spec.family in ALLOWED_FAMILIES and not is_mechanical_only_id(spec.seed_id)]
    skipped = [
        {
            "manifest": str(spec.manifest_path),
            "error": f"skipped non-electrical family or mechanical-only seed: {spec.seed_id}",
        }
        for spec in specs
        if spec not in electrical_specs
    ]
    return electrical_specs, failures + skipped


def is_mechanical_only_id(value: str) -> bool:
    normalized = value.lower().replace("-", "_")
    return any(pattern in normalized for pattern in MECHANICAL_ONLY_PATTERNS)


def read_seed_registry_entries(path: str | Path = "seed_registry.yaml") -> list[dict[str, Any]]:
    """Read the simple seed_registry.yaml shape used by this repo.

    PyYAML is optional in this project, so this falls back to a tiny parser for
    the top-level `seeds:` list and the fields needed by the app/tests.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        entries = data.get("seeds", [])
        return [dict(entry) for entry in entries if isinstance(entry, dict)]
    except Exception:
        return _parse_seed_registry_fallback(text)


def _parse_seed_registry_fallback(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_seeds = False
    field_re = re.compile(r"^\s{4}([A-Za-z0-9_]+):\s*(.*)$")
    for line in text.splitlines():
        if line.strip() == "seeds:":
            in_seeds = True
            continue
        if not in_seeds:
            continue
        if line.startswith("  - seed_id:"):
            if current:
                entries.append(current)
            current = {"seed_id": line.split(":", 1)[1].strip().strip('"')}
            continue
        if current is None:
            continue
        match = field_re.match(line)
        if match:
            key, raw = match.groups()
            current[key] = raw.strip().strip('"')
    if current:
        entries.append(current)
    return entries


def validate_registry_families(path: str | Path = "seed_registry.yaml") -> list[str]:
    errors: list[str] = []
    for entry in read_seed_registry_entries(path):
        seed_id = str(entry.get("seed_id", ""))
        family = str(entry.get("family", ""))
        if family not in ALLOWED_FAMILIES:
            errors.append(f"{seed_id}: invalid family {family!r}")
        if is_mechanical_only_id(seed_id):
            errors.append(f"{seed_id}: mechanical-only seed is not allowed")
    return errors
