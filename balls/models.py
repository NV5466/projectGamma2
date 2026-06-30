from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


ALLOWED_CHANNEL_ROLES = {
    "victim_signal",
    "suspected_source",
    "reference_or_common",
    "command_or_trigger",
    "output_or_consequence",
    "unknown",
}

ALLOWED_SIGNAL_TYPES = {
    "analog_voltage",
    "analog_current",
    "digital_like_voltage",
    "digital_logic_state",
    "power_waveform",
    "reference_or_ground",
    "unknown",
}

ALLOWED_VOLTAGE_CLASSES = {
    "5V_logic",
    "24VDC",
    "low_voltage_dc",
    "120VAC_control",
    "480VAC_power",
    "not_applicable",
    "unknown",
}

ALLOWED_MEASUREMENT_REFERENCES = {
    "signal_to_common",
    "common_to_chassis",
    "line_to_line",
    "line_to_ground",
    "current_clamp",
    "logic_state",
    "unknown",
}

ALLOWED_PROBLEMS = {
    "noise",
    "chatter",
    "dropout",
    "late_transition",
    "missing_transition",
    "weak_signal",
    "transient",
    "sag_swell",
    "harmonic_distortion",
    "unknown",
}


@dataclass
class ChannelMetadata:
    channel_id: str
    line_identity: str = ""
    signal_name: str = ""
    role: str = "unknown"
    signal_type: str = "unknown"
    probe_class: str = "unknown"
    attenuation: str = "unknown"
    coupling: str = "unknown"
    voltage_class: str = "unknown"
    measurement_reference: str = "unknown"
    problem_observed: str = "unknown"
    event_context: str = "unknown"
    notes: str = ""


@dataclass
class CaptureMetadata:
    capture_name: str
    instrument: str = "unknown"
    system: str = "unknown"
    event: str = "unknown"
    known_good_available: bool = False
    channels: dict[str, ChannelMetadata] = field(default_factory=dict)
    notes: str = ""


@dataclass
class AnalogChannel:
    channel_id: str
    time_s: np.ndarray
    values: np.ndarray
    units: str = "V"
    metadata: ChannelMetadata | None = None


@dataclass
class Capture:
    source_path: Path
    time_column: str
    channels: list[AnalogChannel]
    metadata: CaptureMetadata
    sample_rate_hz: float | None
    sample_interval_s: float | None
    time_jitter_ratio: float | None
    analysis_windows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AnalysisResult:
    channel_id: str
    stats: dict[str, float]
    quality_warnings: list[str]
    dominant_frequencies_hz: list[float]
    routed_analyses: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    events: list["TimelineEvent"] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    windowed_results: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, Path] = field(default_factory=dict)
    event_window: tuple[float, float] | None = None


@dataclass
class TimelineEvent:
    time_s: float
    channel_id: str
    role: str
    label: str
    detail: str = ""


@dataclass
class Report:
    capture: Capture
    results: list[AnalysisResult]
    warnings: list[str]
    output_dir: Path
    text_path: Path
    json_path: Path
    markdown_path: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)
