from __future__ import annotations

from typing import Any

from .models import Capture, TimelineEvent


def build_windows(capture: Capture, timeline: list[TimelineEvent]) -> list[dict[str, Any]]:
    if not capture.channels:
        return []

    capture_start = float(capture.channels[0].time_s[0])
    capture_end = float(capture.channels[0].time_s[-1])
    roles = channels_by_role(capture)
    windows: list[dict[str, Any]] = []

    command_rise = first_event(timeline, "command_or_trigger", "rose")
    command_fall = first_event(timeline, "command_or_trigger", "fell")
    source_start = first_event(timeline, "suspected_source")
    reference_start = first_event(timeline, "reference_or_common")
    chatter_start = first_event(timeline, "victim_signal", "transitioned/chattered")
    dropout_start = first_event(timeline, "victim_signal", "dropout detected")
    fault_assert = first_event(timeline, "output_or_consequence", "asserted")

    command_start_s = command_rise.time_s if command_rise else capture_start
    command_end_s = command_fall.time_s if command_fall else capture_end

    if command_rise and command_start_s > capture_start:
        windows.append(
            make_window(
                "baseline_pre_command",
                capture_start,
                command_start_s,
                command_rise.channel_id,
                "before_command_rise",
                "Idle noise floor and baseline spectral reference before the command event.",
                "detected event",
                all_channels(capture),
                ["baseline_RMS", "baseline_PSD", "noise_floor"],
            )
        )

    if command_rise and command_fall:
        windows.append(
            make_window(
                "command_active",
                command_rise.time_s,
                command_fall.time_s,
                command_rise.channel_id,
                "command_rise_to_fall",
                "Main event window anchored to command active state.",
                "detected event",
                roles["suspected_source"] + roles["reference_or_common"] + roles["victim_signal"],
                ["event_RMS", "event_PSD", "baseline_vs_event_PSD", "sequence_timing"],
            )
        )

    if source_start:
        windows.append(
            make_window(
                "source_activity",
                source_start.time_s,
                command_end_s,
                source_start.channel_id,
                source_start.label,
                "Suspected source activity interval for source RMS, PSD, and transient energy checks.",
                "detected event",
                [source_start.channel_id] + roles["victim_signal"] + roles["reference_or_common"],
                ["source_RMS", "source_PSD", "transient_energy", "baseline_vs_event_PSD"],
            )
        )

    if reference_start:
        windows.append(
            make_window(
                "reference_disturbance",
                reference_start.time_s,
                command_end_s,
                reference_start.channel_id,
                reference_start.label,
                "Reference/common movement interval for common/reference noise analysis.",
                "detected event",
                [reference_start.channel_id] + roles["victim_signal"] + roles["suspected_source"],
                ["reference_RMS", "reference_PSD", "overlap_check", "baseline_vs_event_PSD"],
            )
        )

    if chatter_start:
        chatter_end = event_detail_until(chatter_start) or chatter_start.time_s
        windows.append(
            make_window(
                "victim_chatter",
                chatter_start.time_s,
                chatter_end,
                chatter_start.channel_id,
                chatter_start.label,
                "Victim instability/chatter interval for edge density and state stability checks.",
                "detected event",
                [chatter_start.channel_id] + roles["reference_or_common"] + roles["suspected_source"],
                ["edge_density", "chatter_detection", "state_stability"],
            )
        )

    if dropout_start:
        dropout_end = event_detail_until(dropout_start) or dropout_start.time_s
        windows.append(
            make_window(
                "victim_dropout",
                dropout_start.time_s,
                dropout_end,
                dropout_start.channel_id,
                dropout_start.label,
                "Victim dropout interval for dropout and consequence timing checks.",
                "detected event",
                [dropout_start.channel_id] + roles["output_or_consequence"],
                ["dropout_detection", "delay_to_output", "state_stability"],
            )
        )

    post_start_candidates = [event.time_s for event in [command_fall, fault_assert] if event is not None]
    if post_start_candidates:
        post_start = max(post_start_candidates)
        if post_start < capture_end:
            anchor = command_fall or fault_assert
            windows.append(
                make_window(
                    "post_event_recovery",
                    post_start,
                    capture_end,
                    anchor.channel_id,
                    "after_command_or_fault",
                    "Post-event recovery/stability interval after command fall or fault assertion.",
                    "detected event",
                    all_channels(capture),
                    ["recovery_stability", "post_event_RMS", "post_event_PSD"],
                )
            )

    return [window for window in windows if window["duration_s"] > 0]


def make_window(
    name: str,
    start_s: float,
    end_s: float,
    anchor_channel: str,
    anchor_event: str,
    purpose: str,
    generated_from: str,
    applicable_channels: list[str],
    recommended_analyses: list[str],
) -> dict[str, Any]:
    return {
        "name": name,
        "start_s": float(start_s),
        "end_s": float(end_s),
        "duration_s": float(end_s - start_s),
        "anchor_channel": anchor_channel,
        "anchor_event": anchor_event,
        "purpose": purpose,
        "generated_from": generated_from,
        "applicable_channels": sorted(dict.fromkeys(applicable_channels)),
        "recommended_analyses": recommended_analyses,
    }


def channels_by_role(capture: Capture) -> dict[str, list[str]]:
    roles = {
        "victim_signal": [],
        "suspected_source": [],
        "reference_or_common": [],
        "command_or_trigger": [],
        "output_or_consequence": [],
        "unknown": [],
    }
    for channel in capture.channels:
        role = channel.metadata.role if channel.metadata else "unknown"
        roles.setdefault(role, []).append(channel.channel_id)
    return roles


def all_channels(capture: Capture) -> list[str]:
    return [channel.channel_id for channel in capture.channels]


def first_event(timeline: list[TimelineEvent], role: str, label: str | None = None) -> TimelineEvent | None:
    matches = [event for event in timeline if event.role == role and (label is None or event.label == label)]
    return min(matches, key=lambda event: event.time_s) if matches else None


def event_detail_until(event: TimelineEvent) -> float | None:
    marker_options = ("until ", "low until ")
    for marker in marker_options:
        if marker in event.detail:
            value = event.detail.split(marker, 1)[1].split(" ", 1)[0]
            try:
                return float(value)
            except ValueError:
                return None
    return None
