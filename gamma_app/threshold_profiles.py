from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


DEFAULT_PROFILE_NAME = "default"
DEFAULT_THRESHOLD = 0.50


@dataclass
class ThresholdProfile:
    name: str = DEFAULT_PROFILE_NAME
    default_threshold: float = DEFAULT_THRESHOLD
    signature_thresholds: dict[str, float] = field(default_factory=dict)
    source_path: str | None = None

    def threshold_for(self, signature_id: str) -> float:
        return float(self.signature_thresholds.get(signature_id, self.default_threshold))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "default_threshold": self.default_threshold,
            "signature_thresholds": dict(sorted(self.signature_thresholds.items())),
            "source_path": self.source_path,
        }


def default_profile() -> ThresholdProfile:
    return ThresholdProfile()


def load_threshold_profile(path: str | Path | None) -> ThresholdProfile:
    if path is None:
        return default_profile()
    profile_path = Path(path)
    if not profile_path.exists():
        raise FileNotFoundError(f"threshold profile not found: {profile_path}")
    text = profile_path.read_text(encoding="utf-8-sig")
    data = _load_mapping(text, profile_path.suffix.lower())
    return ThresholdProfile(
        name=str(data.get("name", profile_path.stem)),
        default_threshold=float(data.get("default_threshold", DEFAULT_THRESHOLD)),
        signature_thresholds={str(k): float(v) for k, v in dict(data.get("signature_thresholds", {})).items()},
        source_path=str(profile_path),
    )


def save_threshold_profile(profile: ThresholdProfile, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(profile.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    else:
        lines = [
            f"name: {profile.name}",
            f"default_threshold: {profile.default_threshold}",
            "signature_thresholds:",
        ]
        for signature_id, threshold in sorted(profile.signature_thresholds.items()):
            lines.append(f"  {signature_id}: {threshold}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_mapping(text: str, suffix: str) -> dict[str, Any]:
    if suffix == ".json":
        return dict(json.loads(text))
    try:
        import yaml  # type: ignore

        return dict(yaml.safe_load(text) or {})
    except Exception:
        return _parse_profile_yaml_subset(text)


def _parse_profile_yaml_subset(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    thresholds: dict[str, float] = {}
    in_thresholds = False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("signature_thresholds:"):
            in_thresholds = True
            continue
        if in_thresholds and line.startswith("  ") and ":" in line:
            key, raw = line.split(":", 1)
            thresholds[key.strip()] = float(raw.strip())
            continue
        in_thresholds = False
        if ":" in line:
            key, raw = line.split(":", 1)
            value = raw.strip()
            if key.strip() == "default_threshold":
                data[key.strip()] = float(value)
            else:
                data[key.strip()] = value
    data["signature_thresholds"] = thresholds
    return data
