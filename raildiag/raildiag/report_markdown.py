from __future__ import annotations

from typing import Any

from .report_format import fmt_event_linked, fmt_peak_list


def render_markdown_report(document: dict[str, Any]) -> str:
    lines: list[str] = []
    capture = document["capture"]

    lines.append(f"# ElectroStat Report: {capture['capture_name']}")
    lines.append("")
    lines.append("## Capture")
    lines.append(f"- Source file: `{capture['source_file']}`")
    lines.append(f"- Instrument: {capture['instrument']}")
    lines.append(f"- System: {capture['system']}")
    lines.append(f"- Event: {capture['event']}")
    lines.append(f"- Time column: `{capture['time_column']}`")
    lines.append(f"- Channels analyzed: {capture['channels_analyzed']}")
    if capture["sample_rate_hz"]:
        lines.append(f"- Estimated sample rate: {capture['sample_rate_hz']:.6g} Hz")
    if capture["sample_interval_s"]:
        lines.append(f"- Estimated sample interval: {capture['sample_interval_s']:.6g} s")
    if capture["time_jitter_ratio"] is not None:
        lines.append(f"- Time-step jitter ratio: {capture['time_jitter_ratio']:.3%}")
    lines.append("")

    lines.append("## Limitations and Warnings")
    for warning in document["warnings"] or ["No major automatic warnings were generated."]:
        lines.append(f"- {warning}")
    lines.append("")

    lines.append("## Channel Roles")
    for role in document["channel_roles"]:
        lines.append(f"### {role['channel']}")
        lines.append(f"- Line identity: {role['line_identity']}")
        lines.append(f"- Role: {role['role']}")
        lines.append(f"- Signal type: {role['signal_type']}")
        lines.append(f"- Voltage class: {role['voltage_class']}")
        lines.append(f"- Measurement reference: {role['measurement_reference']}")
        lines.append(f"- Problem observed: {role['problem_observed']}")
        lines.append("")
    lines.append("")

    lines.append("## Event Timeline")
    if document["timeline"]:
        for event in document["timeline"]:
            detail = f" - {event['detail']}" if event["detail"] else ""
            lines.append(f"- {event['time_s']:.6g} s: {event['role']} {event['channel']} {event['label']}{detail}")
    else:
        lines.append("- No role-aware timeline events were detected. Add channel roles/signal types to enable routing.")
    lines.append("")

    lines.append("## Analysis Windows")
    if document["windows"]:
        for window in document["windows"]:
            lines.append(f"### {window['name']}")
            lines.append(f"- Start: {window['start_s']:.6g} s")
            lines.append(f"- End: {window['end_s']:.6g} s")
            lines.append(f"- Duration: {window['duration_s'] * 1000:.6g} ms")
            lines.append(f"- Anchor channel: {window['anchor_channel']}")
            lines.append(f"- Anchor event: {window['anchor_event']}")
            lines.append(f"- Generated from: {window['generated_from']}")
            lines.append(f"- Purpose: {window['purpose']}")
            lines.append(f"- Applicable channels: {', '.join(window['applicable_channels'])}")
            lines.append(f"- Recommended analyses: {', '.join(window['recommended_analyses'])}")
            lines.append("")
    else:
        lines.append("- No first-class analysis windows were generated.")
    lines.append("")

    lines.append("## Role-Aware Interpretation")
    any_observations = False
    for channel in document["channels"]:
        if not channel["observations"] and not channel["routed_analyses"]:
            continue
        any_observations = True
        lines.append(f"### {channel['channel']}: {channel['line_identity']}")
        lines.append(f"- Route: {channel['role']} / {channel['signal_type']}")
        if channel["routed_analyses"]:
            lines.append(f"- Routed analyses: {', '.join(channel['routed_analyses'])}")
        for observation in channel["observations"]:
            lines.append(f"- {observation}")
        for relationship in channel["relationships"]:
            lines.append(f"- {relationship}")
        if channel["role"] in {"command_or_trigger", "output_or_consequence"} or channel["signal_type"] in {"digital_like_voltage", "digital_logic_state"}:
            lines.append("- PSD on digital-like state lines is secondary; edge timing and state duration are primary evidence.")
        lines.append("")
    if not any_observations:
        lines.append("- No role-aware observations were generated.")
    lines.append("")

    lines.append("## Channel Results")
    for channel in document["channels"]:
        lines.append(f"### {channel['channel']}: {channel['line_identity']}")
        lines.append(f"- Role: {channel['role']}")
        if channel["event_window"]:
            lines.append(f"- Event window: {channel['event_window'][0]:.6g}s to {channel['event_window'][1]:.6g}s")
        for warning in channel["quality_warnings"]:
            lines.append(f"- Warning: {warning}")
        lines.append("")
        for key, value in channel["stats"].items():
            lines.append(f"- {key}: {value:.0f}" if key == "count" else f"- {key}: {value:.6g}")
        lines.append("")
        if channel["global_psd_overview_peaks_hz"]:
            joined = ", ".join(f"{freq:.6g} Hz" for freq in channel["global_psd_overview_peaks_hz"])
            lines.append(f"- Global PSD overview peaks: {joined}")
        else:
            lines.append("- Global PSD overview peaks: not available.")
        if channel["windowed_results"]:
            lines.append("- Windowed spectral results:")
            for item in channel["windowed_results"]:
                lines.append(f"  - {item['window_name']}: {item['summary']}")
                lines.append(f"    - Stable peaks: {fmt_peak_list(item['stable_peaks_hz'])}")
                lines.append(f"    - Event-linked peaks: {fmt_event_linked(item['event_linked_peaks'])}")
        for artifact_name, artifact_path in channel["artifacts"].items():
            lines.append(f"- {artifact_name.title()} plot: [{artifact_path}]({artifact_path})")
        lines.append("")

    lines.append("## Interpretation Boundary")
    for item in document["interpretation_boundary"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)
