from __future__ import annotations

from typing import Any

from .report_format import (
    bullets,
    fmt_event_linked,
    fmt_number,
    fmt_optional,
    fmt_peak_list,
    fmt_percent,
    fmt_window,
    kv_block,
    section,
    title,
    wrapped_line,
)


def render_text_report(document: dict[str, Any], width: int = 100) -> str:
    lines: list[str] = []
    capture = document["capture"]

    title(lines, f"ElectroStat Report: {capture['capture_name']}", width)
    kv_block(
        lines,
        [
            ("Source file", capture["source_file"]),
            ("Instrument", capture["instrument"]),
            ("System", capture["system"]),
            ("Event", capture["event"]),
            ("Time column", capture["time_column"]),
            ("Channels analyzed", capture["channels_analyzed"]),
            ("Estimated sample rate", fmt_optional(capture["sample_rate_hz"], " Hz")),
            ("Estimated sample interval", fmt_optional(capture["sample_interval_s"], " s")),
            ("Time-step jitter ratio", fmt_percent(capture["time_jitter_ratio"])),
        ],
        width,
    )

    section(lines, "Limitations and Warnings", width)
    warnings = document["warnings"]
    bullets(lines, warnings or ["No major automatic warnings were generated."], width)

    section(lines, "Channel Roles", width)
    for role in document["channel_roles"]:
        lines.append(role["channel"])
        kv_block(
            lines,
            [
                ("Line identity", role["line_identity"]),
                ("Role", role["role"]),
                ("Signal type", role["signal_type"]),
                ("Voltage class", role["voltage_class"]),
                ("Measurement reference", role["measurement_reference"]),
                ("Problem observed", role["problem_observed"]),
            ],
            width,
            indent=2,
        )

    section(lines, "Event Timeline", width)
    timeline = document["timeline"]
    if timeline:
        for event in timeline:
            detail = f" - {event['detail']}" if event["detail"] else ""
            wrapped_line(lines, f"{event['time_s']:.6g} s: {event['role']} {event['channel']} {event['label']}{detail}", width, prefix="- ")
    else:
        bullets(lines, ["No role-aware timeline events were detected. Add channel roles/signal types to enable routing."], width)

    section(lines, "Analysis Windows", width)
    if document["windows"]:
        for window in document["windows"]:
            lines.append(window["name"])
            kv_block(
                lines,
                [
                    ("Start", f"{window['start_s']:.6g} s"),
                    ("End", f"{window['end_s']:.6g} s"),
                    ("Duration", f"{window['duration_s'] * 1000:.6g} ms"),
                    ("Anchor channel", window["anchor_channel"]),
                    ("Anchor event", window["anchor_event"]),
                    ("Generated from", window["generated_from"]),
                    ("Purpose", window["purpose"]),
                    ("Applicable channels", ", ".join(window["applicable_channels"])),
                    ("Recommended analyses", ", ".join(window["recommended_analyses"])),
                ],
                width,
                indent=2,
            )
    else:
        bullets(lines, ["No first-class analysis windows were generated."], width)

    section(lines, "Role-Aware Interpretation", width)
    any_observations = False
    for channel in document["channels"]:
        if not channel["observations"] and not channel["routed_analyses"]:
            continue
        any_observations = True
        lines.append(f"{channel['channel']}: {channel['line_identity']}")
        kv_block(
            lines,
            [
                ("Route", f"{channel['role']} / {channel['signal_type']}"),
                ("Routed analyses", ", ".join(channel["routed_analyses"]) if channel["routed_analyses"] else "none"),
            ],
            width,
            indent=2,
        )
        bullets(lines, channel["observations"], width, indent=2)
        if channel["relationships"]:
            bullets(lines, channel["relationships"], width, indent=2)
        if channel["role"] in {"command_or_trigger", "output_or_consequence"} or channel["signal_type"] in {"digital_like_voltage", "digital_logic_state"}:
            bullets(lines, ["PSD on digital-like state lines is secondary; edge timing and state duration are primary evidence."], width, indent=2)
        lines.append("")
    if not any_observations:
        bullets(lines, ["No role-aware observations were generated."], width)

    section(lines, "Channel Measurements", width)
    for channel in document["channels"]:
        lines.append(f"{channel['channel']}: {channel['line_identity']}")
        kv_block(lines, [("Role", channel["role"]), ("Manual event window", fmt_window(channel["event_window"]))], width, indent=2)
        if channel["quality_warnings"]:
            bullets(lines, [f"Warning: {warning}" for warning in channel["quality_warnings"]], width, indent=2)
        kv_block(lines, [(key, fmt_number(value)) for key, value in channel["stats"].items()], width, indent=2)
        freqs = channel["global_psd_overview_peaks_hz"]
        freq_text = ", ".join(f"{freq:.6g} Hz" for freq in freqs) if freqs else "not available"
        psd_label = "Global PSD overview"
        if channel["signal_type"] in {"digital_like_voltage", "digital_logic_state"}:
            psd_label = "Global PSD overview (secondary)"
        kv_block(lines, [(psd_label, freq_text)], width, indent=2)
        if channel["windowed_results"]:
            lines.append("  Windowed spectral results:")
            for item in channel["windowed_results"]:
                lines.append(f"    {item['window_name']}")
                kv_block(
                    lines,
                    [
                        ("Purpose", item["purpose"]),
                        ("Baseline window", item.get("baseline_window", "none")),
                        ("Stable peaks", fmt_peak_list(item["stable_peaks_hz"])),
                        ("Event-linked peaks", fmt_event_linked(item["event_linked_peaks"])),
                        ("Amplitude-sensitive", fmt_peak_list(item["amplitude_sensitive_peaks_hz"])),
                        ("Window-specific", fmt_peak_list(item["window_specific_peaks_hz"])),
                        ("Summary", item["summary"]),
                    ],
                    width,
                    indent=6,
                )
        if channel["artifacts"]:
            kv_block(lines, [(f"{name} plot", path) for name, path in channel["artifacts"].items()], width, indent=2)
        lines.append("")

    section(lines, "Interpretation Boundary", width)
    bullets(lines, document["interpretation_boundary"], width)
    return "\n".join(lines).rstrip() + "\n"
