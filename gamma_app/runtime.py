from __future__ import annotations

from pathlib import Path
import sys


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / relative_path


def default_registry_root() -> Path:
    return resource_path("") if is_frozen() else Path(".")


def default_threshold_profile_path() -> Path:
    bundled = resource_path("configs/default_thresholds.yaml")
    return bundled if bundled.exists() else Path("configs/default_thresholds.yaml")
