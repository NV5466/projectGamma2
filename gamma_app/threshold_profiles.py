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
    based_on: str | None = None
    created_for: str | None = None
    default_threshold: float = DEFAULT_THRESHOLD
    signature_thresholds: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    baseline_metrics: dict[str, Any] = field(default_factory=dict)
    tuned_metrics: dict[str, Any] = field(default_factory=dict)
    source_path: str | None = None

    def threshold_for(self, signature_id: str) -> float:
        if signature_id in self.signature_thresholds:
            return float(self.signature_thresholds[signature_id])
        if signature_id == "emi_eft_burst_v010" and "emi_eft_burst" in self.signature_thresholds:
            return float(self.signature_thresholds["emi_eft_burst"])
        return float(self.default_threshold)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "based_on": self.based_on,
            "created_for": self.created_for,
            "default_threshold": self.default_threshold,
            "signature_thresholds": dict(sorted(self.signature_thresholds.items())),
            "notes": list(self.notes),
            "baseline_metrics": dict(self.baseline_metrics),
            "tuned_metrics": dict(self.tuned_metrics),
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
        based_on=(str(data.get("based_on")) if data.get("based_on") is not None else None),
        created_for=(str(data.get("created_for")) if data.get("created_for") is not None else None),
        default_threshold=float(data.get("default_threshold", DEFAULT_THRESHOLD)),
        signature_thresholds={
            ("emi_eft_burst" if str(k) == "emi_eft_burst_v010" else str(k)): float(v)
            for k, v in dict(data.get("signature_thresholds", {})).items()
        },
        notes=[str(item) for item in list(data.get("notes", []))],
        baseline_metrics=dict(data.get("baseline_metrics", {}) or {}),
        tuned_metrics=dict(data.get("tuned_metrics", {}) or {}),
        source_path=str(profile_path),
    )


def save_threshold_profile(profile: ThresholdProfile, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(profile.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    else:
        try:
            import yaml  # type: ignore

            path.write_text(yaml.safe_dump(profile.to_dict(), sort_keys=False), encoding="utf-8")
        except Exception:
            path.write_text(_dump_yaml_subset(profile.to_dict()), encoding="utf-8")


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


def _dump_yaml_subset(data: dict[str, Any], indent: int = 0) -> str:
    lines: list[str] = []
    pad = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{pad}{key}:")
            lines.append(_dump_yaml_subset(value, indent + 1).rstrip("\n"))
        elif isinstance(value, list):
            if not value:
                lines.append(f"{pad}{key}: []")
            else:
                lines.append(f"{pad}{key}:")
                for item in value:
                    if isinstance(item, (dict, list)):
                        lines.append(f"{pad}-")
                        if isinstance(item, dict):
                            lines.append(_dump_yaml_subset(item, indent + 1).rstrip("\n"))
                        else:
                            for nested in item:
                                lines.append(f"{pad}  - {nested}")
                    else:
                        lines.append(f"{pad}  - {item}")
        elif value is None:
            lines.append(f"{pad}{key}: null")
        elif isinstance(value, bool):
            lines.append(f"{pad}{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{pad}{key}: {value}")
    return "\n".join(lines) + "\n"
