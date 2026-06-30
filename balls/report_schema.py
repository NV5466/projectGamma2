from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import AnalysisResult, Capture, TimelineEvent


REPORT_SCHEMA_VERSION = "electrostat.report.v2"


def build_report_document(
    capture: Capture,
    results: list[AnalysisResult],
    warnings: list[str],
    output_dir: Path,
) -> dict[str, Any]:
    metadata = capture.metadata
    unknown_roles = any((channel.metadata is None or channel.metadata.role == "unknown") for channel in capture.channels)

    role_rows: list[dict[str, str]] = []
    for channel in capture.channels:
        meta = channel.metadata
        role_rows.append(
            {
                "channel": channel.channel_id,
                "line_identity": meta.line_identity if meta and meta.line_identity else "not supplied",
                "role": meta.role if meta else "unknown",
                "signal_type": meta.signal_type if meta else "unknown",
                "voltage_class": meta.voltage_class if meta else "unknown",
                "measurement_reference": meta.measurement_reference if meta else "unknown",
                "problem_observed": meta.problem_observed if meta else "unknown",
            }
        )

    timeline_events = timeline(results)
    windows = capture.analysis_windows

    channel_results: list[dict[str, Any]] = []
    for result in results:
        channel = next(ch for ch in capture.channels if ch.channel_id == result.channel_id)
        meta = channel.metadata
        artifacts: dict[str, str] = {}
        for artifact_name, artifact_path in result.artifacts.items():
            artifacts[artifact_name] = artifact_path.relative_to(output_dir).as_posix()

        channel_results.append(
            {
                "channel": channel.channel_id,
                "line_identity": meta.line_identity if meta and meta.line_identity else channel.channel_id,
                "role": meta.role if meta else "unknown",
                "signal_type": meta.signal_type if meta else "unknown",
                "routed_analyses": result.routed_analyses,
                "observations": result.observations,
                "relationships": result.relationships,
                "quality_warnings": result.quality_warnings,
                "stats": result.stats,
                "global_psd_overview_peaks_hz": result.dominant_frequencies_hz,
                "dominant_frequencies_hz": result.dominant_frequencies_hz,
                "windowed_results": result.windowed_results,
                "artifacts": artifacts,
                "event_window": list(result.event_window) if result.event_window else None,
            }
        )

    limitation_warnings = list(warnings)
    if unknown_roles:
        limitation_warnings.append(
            "One or more channels lack known roles; source-victim and causal timeline conclusions are restricted."
        )

    return {
        "schema": REPORT_SCHEMA_VERSION,
        "capture": {
            "capture_name": metadata.capture_name,
            "source_file": str(capture.source_path),
            "instrument": metadata.instrument,
            "system": metadata.system,
            "event": metadata.event,
            "time_column": capture.time_column,
            "channels_analyzed": len(capture.channels),
            "sample_rate_hz": capture.sample_rate_hz,
            "sample_interval_s": capture.sample_interval_s,
            "time_jitter_ratio": capture.time_jitter_ratio,
        },
        "warnings": limitation_warnings,
        "channel_roles": role_rows,
        "windows": windows,
        "timeline": [
            {
                "time_s": event.time_s,
                "channel": event.channel_id,
                "role": event.role,
                "label": event.label,
                "detail": event.detail,
            }
            for event in timeline_events
        ],
        "channels": channel_results,
        "interpretation_boundary": [
            "This report is deterministic first-pass analysis. It can identify observed signal behavior, data-quality limits, and timing/spectral clues, but it does not claim root cause.",
            "The user-supplied metadata defines line identity and role. Waveform shape may support behavior observations, but ElectroStat does not infer physical line identity from shape alone.",
        ],
    }


def timeline(results: list[AnalysisResult]) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    for result in results:
        events.extend(result.events)
    return sorted(events, key=lambda event: (event.time_s, event.channel_id, event.label))
