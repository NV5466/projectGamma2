from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import (
    ALLOWED_CHANNEL_ROLES,
    ALLOWED_MEASUREMENT_REFERENCES,
    ALLOWED_PROBLEMS,
    ALLOWED_SIGNAL_TYPES,
    ALLOWED_VOLTAGE_CLASSES,
    CaptureMetadata,
    ChannelMetadata,
)


def load_metadata(path: Path | None, fallback_capture_name: str) -> CaptureMetadata:
    if path is None:
        return CaptureMetadata(capture_name=fallback_capture_name)

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    capture_raw: dict[str, Any] = raw.get("capture", {}) or {}
    channels_raw: dict[str, Any] = raw.get("channels", {}) or {}

    channels: dict[str, ChannelMetadata] = {}
    for channel_id, values in channels_raw.items():
        values = values or {}
        channels[str(channel_id)] = ChannelMetadata(
            channel_id=str(channel_id),
            line_identity=str(values.get("line_identity", values.get("signal_name", ""))),
            signal_name=str(values.get("signal_name", "")),
            role=str(values.get("role", "unknown")),
            signal_type=str(values.get("signal_type", "unknown")),
            probe_class=str(values.get("probe_class", "unknown")),
            attenuation=str(values.get("attenuation", "unknown")),
            coupling=str(values.get("coupling", "unknown")),
            voltage_class=str(values.get("voltage_class", "unknown")),
            measurement_reference=str(values.get("measurement_reference", "unknown")),
            problem_observed=str(values.get("problem_observed", "unknown")),
            event_context=str(values.get("event_context", capture_raw.get("event", "unknown"))),
            notes=str(values.get("notes", "")),
        )

    return CaptureMetadata(
        capture_name=str(capture_raw.get("capture_name", fallback_capture_name)),
        instrument=str(capture_raw.get("instrument", "unknown")),
        system=str(capture_raw.get("system", "unknown")),
        event=str(capture_raw.get("event", "unknown")),
        known_good_available=bool(capture_raw.get("known_good_available", False)),
        notes=str(capture_raw.get("notes", "")),
        channels=channels,
    )


def metadata_warnings(metadata: CaptureMetadata) -> list[str]:
    warnings: list[str] = []

    if metadata.instrument == "unknown":
        warnings.append("Instrument is unknown.")
    if metadata.system == "unknown":
        warnings.append("System under test is unknown.")
    if metadata.event == "unknown":
        warnings.append("Captured event is unknown.")

    for channel_id, channel in metadata.channels.items():
        if not channel.line_identity:
            warnings.append(f"{channel_id}: line identity is not supplied; physical/electrical identity will not be inferred.")
        if channel.role == "unknown":
            warnings.append(f"{channel_id}: channel role is unknown.")
        elif channel.role not in ALLOWED_CHANNEL_ROLES:
            warnings.append(f"{channel_id}: channel role '{channel.role}' is not recognized; role-aware conclusions may be limited.")
        if channel.signal_type == "unknown":
            warnings.append(f"{channel_id}: signal type is unknown.")
        elif channel.signal_type not in ALLOWED_SIGNAL_TYPES:
            warnings.append(f"{channel_id}: signal type '{channel.signal_type}' is not recognized; routing may be limited.")
        if channel.voltage_class == "unknown":
            warnings.append(f"{channel_id}: voltage class is unknown.")
        elif channel.voltage_class not in ALLOWED_VOLTAGE_CLASSES:
            warnings.append(f"{channel_id}: voltage class '{channel.voltage_class}' is not in the dropdown set.")
        if channel.probe_class == "unknown":
            warnings.append(f"{channel_id}: probe class is unknown.")
        if channel.measurement_reference == "unknown":
            warnings.append(f"{channel_id}: measurement reference is unknown.")
        elif channel.measurement_reference not in ALLOWED_MEASUREMENT_REFERENCES:
            warnings.append(f"{channel_id}: measurement reference '{channel.measurement_reference}' is not in the dropdown set.")
        if channel.problem_observed not in ALLOWED_PROBLEMS:
            warnings.append(f"{channel_id}: problem observed '{channel.problem_observed}' is not in the dropdown set.")
        if "high" in channel.voltage_class.lower() and channel.probe_class.lower() == "passive":
            warnings.append(
                f"{channel_id}: high-voltage measurement with passive probe metadata; verify setup safety."
            )

    return warnings
