from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np


@dataclass
class CaptureRecord:
    sample_rate_hz: float
    primary: np.ndarray
    secondary: np.ndarray | None = None
    references: dict[str, np.ndarray] = field(default_factory=dict)
    time_s: np.ndarray | None = None
    capture_id: str | None = None
    truth_label: str | None = None
    primary_label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tertiary: np.ndarray | None = None

    def validate(self) -> None:
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if self.primary is None:
            raise ValueError("primary is required")
        self.primary = np.asarray(self.primary, dtype=float)
        if self.primary.ndim != 1:
            raise ValueError("primary must be a 1D waveform")
        if len(self.primary) < 8:
            raise ValueError("primary waveform is too short")
        if not np.all(np.isfinite(self.primary)):
            raise ValueError("primary contains non-finite values")

        if self.secondary is not None and "secondary" not in self.references:
            self.references["secondary"] = np.asarray(self.secondary, dtype=float)
        if not self.references:
            raise ValueError("at least one reference waveform is required")

        normalized_refs: dict[str, np.ndarray] = {}
        for label, wave in self.references.items():
            if not label:
                raise ValueError("reference labels must be non-empty")
            arr = np.asarray(wave, dtype=float)
            if arr.ndim != 1:
                raise ValueError(f"reference {label!r} must be a 1D waveform")
            if len(arr) != len(self.primary):
                raise ValueError(f"reference {label!r} length must match primary length")
            if not np.all(np.isfinite(arr)):
                raise ValueError(f"reference {label!r} contains non-finite values")
            normalized_refs[str(label)] = arr
        self.references = normalized_refs

        if self.time_s is None:
            self.time_s = np.arange(len(self.primary), dtype=float) / self.sample_rate_hz
        else:
            self.time_s = np.asarray(self.time_s, dtype=float)
        if self.time_s.ndim != 1:
            raise ValueError("time_s must be 1D")
        if len(self.time_s) != len(self.primary):
            raise ValueError("time_s must match primary length")


@dataclass
class EventEvidence:
    time_s: float | None = None
    start_s: float | None = None
    end_s: float | None = None
    event_type: str | None = None
    amplitude: float | None = None
    description: str | None = None


@dataclass
class ReferenceResult:
    reference_label: str
    matched: bool
    confidence: float
    relationship: dict[str, Any] = field(default_factory=dict)
    features: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    rejections: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.reference_label:
            raise ValueError("reference_label is required")
        if not isinstance(self.matched, bool):
            raise ValueError("matched must be bool")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("confidence must be in [0, 1]")
        if not isinstance(self.features, dict):
            raise ValueError("features must be dict")
        if not isinstance(self.evidence, list):
            raise ValueError("evidence must be list")
        if not isinstance(self.rejections, list):
            raise ValueError("rejections must be list")


@dataclass
class SignatureResult:
    signature_id: str
    matched: bool
    confidence: float
    best_reference: str | None = None
    reference_results: list[ReferenceResult] = field(default_factory=list)
    primary_events: list[EventEvidence] = field(default_factory=list)
    relationship: dict[str, Any] = field(default_factory=dict)
    features: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    rejections: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.signature_id:
            raise ValueError("signature_id is required")
        if not isinstance(self.matched, bool):
            raise ValueError("matched must be bool")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("confidence must be in [0, 1]")
        if not isinstance(self.features, dict):
            raise ValueError("features must be dict")
        if not isinstance(self.evidence, list):
            raise ValueError("evidence must be list")
        if not isinstance(self.rejections, list):
            raise ValueError("rejections must be list")
        if not isinstance(self.errors, list):
            raise ValueError("errors must be list")
        for ref_result in self.reference_results:
            ref_result.validate()

    def to_flat_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_count"] = len(self.evidence)
        data["rejection_count"] = len(self.rejections)
        data["error_count"] = len(self.errors)
        data["reference_count"] = len(self.reference_results)
        data["evidence_text"] = " | ".join(map(str, self.evidence))
        data["rejection_text"] = " | ".join(map(str, self.rejections))
        data["error_text"] = " | ".join(map(str, self.errors))
        return data
