from __future__ import annotations

import numpy as np
from scipy import signal

from .event_windows import build_windows
from .models import AnalogChannel, AnalysisResult, Capture, TimelineEvent
from .spectral_analysis import channel_windowed_results


def analyze_capture(capture: Capture, event_window: tuple[float, float] | None = None) -> tuple[list[AnalysisResult], list[str]]:
    warnings = capture_warnings(capture)
    results_by_channel: dict[str, AnalysisResult] = {}

    for channel in capture.channels:
        time_s, values = _windowed(channel.time_s, channel.values, event_window)
        stats = basic_stats(values)
        quality = channel_quality_warnings(channel, capture)
        if len(time_s) < 2:
            quality.append("Event window contains too few samples for reliable analysis.")
        freqs = dominant_frequencies(values, capture.sample_rate_hz)
        results_by_channel[channel.channel_id] = AnalysisResult(
            channel_id=channel.channel_id,
            stats=stats,
            quality_warnings=quality,
            dominant_frequencies_hz=freqs,
            event_window=event_window if len(time_s) else None,
        )

    route_role_aware_analysis(capture, results_by_channel)
    results = [results_by_channel[channel.channel_id] for channel in capture.channels]
    timeline_events = timeline_from_results(results)
    capture.analysis_windows = build_windows(capture, timeline_events)
    for channel in capture.channels:
        results_by_channel[channel.channel_id].windowed_results = channel_windowed_results(
            capture, channel, capture.analysis_windows
        )
    return results, warnings


def timeline_from_results(results: list[AnalysisResult]) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    for result in results:
        events.extend(result.events)
    return sorted(events, key=lambda event: (event.time_s, event.channel_id, event.label))


def basic_stats(values: np.ndarray) -> dict[str, float]:
    clean = values[np.isfinite(values)]
    if len(clean) == 0:
        return {}

    mean = float(np.mean(clean))
    rms = float(np.sqrt(np.mean(np.square(clean))))
    ac = clean - mean
    rms_ac = float(np.sqrt(np.mean(np.square(ac))))
    return {
        "count": float(len(clean)),
        "mean": mean,
        "min": float(np.min(clean)),
        "max": float(np.max(clean)),
        "std": float(np.std(clean)),
        "rms": rms,
        "rms_ac": rms_ac,
        "peak_to_peak": float(np.ptp(clean)),
    }


def capture_warnings(capture: Capture) -> list[str]:
    warnings: list[str] = []
    if capture.sample_rate_hz is None:
        warnings.append("Sample rate could not be estimated.")
    elif capture.sample_rate_hz <= 0:
        warnings.append("Sample rate estimate is invalid.")

    if capture.time_jitter_ratio is not None and capture.time_jitter_ratio > 0.01:
        warnings.append(
            f"Time step variation is high ({capture.time_jitter_ratio:.2%}); spectral analysis may be unreliable."
        )

    if capture.channels:
        duration = float(capture.channels[0].time_s[-1] - capture.channels[0].time_s[0])
        if duration <= 0:
            warnings.append("Capture duration is invalid.")
        elif duration < 0.001:
            warnings.append("Capture window is very short; low-frequency analysis will be limited.")
    return warnings


def channel_quality_warnings(channel: AnalogChannel, capture: Capture) -> list[str]:
    warnings: list[str] = []
    values = channel.values
    signal_type = channel.metadata.signal_type if channel.metadata else "unknown"
    finite = values[np.isfinite(values)]
    if len(finite) != len(values):
        warnings.append("Channel contains missing or non-finite samples.")
    if len(finite) < 8:
        warnings.append("Channel has too few samples for reliable analysis.")
        return warnings

    vmin = float(np.min(finite))
    vmax = float(np.max(finite))
    flat_min = float(np.mean(np.isclose(finite, vmin)))
    flat_max = float(np.mean(np.isclose(finite, vmax)))
    if flat_min > 0.01 or flat_max > 0.01:
        if signal_type in {"digital_like_voltage", "digital_logic_state"}:
            warnings.append("Samples sit near stable rails/states; expected for digital-like state behavior.")
        else:
            warnings.append("Many samples sit exactly at the channel min/max; check for analog clipping or quantization.")

    if capture.sample_rate_hz:
        duration = float(channel.time_s[-1] - channel.time_s[0])
        resolution = 1.0 / duration if duration > 0 else float("inf")
        if resolution > 10:
            warnings.append(f"Frequency resolution is coarse (~{resolution:.2f} Hz bins).")

    return warnings


def dominant_frequencies(values: np.ndarray, sample_rate_hz: float | None, limit: int = 5) -> list[float]:
    if sample_rate_hz is None or sample_rate_hz <= 0 or len(values) < 16:
        return []

    clean = values[np.isfinite(values)]
    if len(clean) < 16:
        return []

    detrended = signal.detrend(clean)
    freqs, psd = signal.welch(detrended, fs=sample_rate_hz, nperseg=min(2048, len(detrended)))
    if len(freqs) < 2:
        return []

    psd = psd.copy()
    psd[0] = 0
    peak_indices, _ = signal.find_peaks(psd)
    if len(peak_indices) == 0:
        return []

    top = peak_indices[np.argsort(psd[peak_indices])[-limit:]][::-1]
    return [float(freqs[i]) for i in top]


def route_role_aware_analysis(capture: Capture, results_by_channel: dict[str, AnalysisResult]) -> None:
    command_windows: list[tuple[float, float, str]] = []
    victim_events: list[TimelineEvent] = []

    for channel in capture.channels:
        metadata = channel.metadata
        result = results_by_channel[channel.channel_id]
        role = metadata.role if metadata else "unknown"
        signal_type = metadata.signal_type if metadata else "unknown"

        if role == "unknown":
            result.routed_analyses.extend(["basic_stats", "waveform_plot", "PSD_plot"])
            result.observations.append("Role is unknown; analysis is limited to generic waveform/statistical evidence.")
            continue

        if role == "command_or_trigger":
            result.routed_analyses.extend(["threshold_edges", "command_active_window", "pulse_duration"])
            digital = digital_timing(channel)
            _add_digital_observations(result, digital, "command")
            for start, end in digital["active_intervals"]:
                command_windows.append((start, end, channel.channel_id))
                result.observations.append(f"Command active window detected from {start:.6g} s to {end:.6g} s ({(end - start) * 1000:.3g} ms).")
                result.events.append(TimelineEvent(start, channel.channel_id, role, "rose", "command active began"))
                result.events.append(TimelineEvent(end, channel.channel_id, role, "fell", "command active ended"))

        elif role == "output_or_consequence":
            result.routed_analyses.extend(["threshold_edges", "state_change_timing", "fault_assertion_time"])
            digital = digital_timing(channel)
            _add_digital_observations(result, digital, "output/consequence")
            first_rise = _first_edge(digital, "rising")
            if first_rise is not None:
                result.observations.append(f"Output/consequence asserted at {first_rise:.6g} s.")
                result.events.append(TimelineEvent(first_rise, channel.channel_id, role, "asserted", "output/fault state changed high"))

        elif role == "victim_signal" and signal_type in {"digital_like_voltage", "digital_logic_state"}:
            result.routed_analyses.extend(["threshold_edges", "chatter_detection", "dropout_detection", "state_stability"])
            digital = digital_timing(channel)
            _add_digital_observations(result, digital, "victim")
            chatter = chatter_windows(digital["edges"])
            for start, end, count in chatter:
                result.observations.append(f"Victim chatter/instability detected from {start:.6g} s to {end:.6g} s ({count} edges).")
                event = TimelineEvent(start, channel.channel_id, role, "transitioned/chattered", f"unstable until {end:.6g} s")
                result.events.append(event)
                victim_events.append(event)
            dropouts = dropout_windows(digital, command_windows)
            for start, end in dropouts:
                result.observations.append(f"Victim dropout/low-state interval detected from {start:.6g} s to {end:.6g} s.")
                event = TimelineEvent(start, channel.channel_id, role, "dropout detected", f"low until {end:.6g} s")
                result.events.append(event)
                victim_events.append(event)

        elif role == "victim_signal":
            result.routed_analyses.extend(["RMS_noise", "peak_to_peak_noise", "PSD", "transient_screen"])
            result.observations.append("Victim analog channel kept on noise/transient/spectral route.")

        elif role == "suspected_source":
            result.routed_analyses.extend(["activity_onset", "event_window_RMS", "event_window_PSD", "transient_energy"])
            onset = activity_onset(channel, command_windows)
            if onset is not None:
                result.observations.append(f"Suspected source activity began around {onset:.6g} s.")
                result.events.append(TimelineEvent(onset, channel.channel_id, role, "activity began", "source activity threshold crossed"))
            _add_event_window_spectrum(result, channel, capture, command_windows)

        elif role == "reference_or_common":
            result.routed_analyses.extend(["reference_movement", "RMS_noise", "event_window_PSD", "overlap_check"])
            onset = activity_onset(channel, command_windows)
            if onset is not None:
                result.observations.append(f"Reference/common movement began around {onset:.6g} s.")
                result.events.append(TimelineEvent(onset, channel.channel_id, role, "disturbance began", "reference/common movement threshold crossed"))
            _add_event_window_spectrum(result, channel, capture, command_windows)

        else:
            result.routed_analyses.extend(["basic_stats", "waveform_plot", "PSD_plot"])
            result.observations.append(f"Role '{role}' is recognized but not yet mapped to a stronger analysis route.")

    _add_cross_role_observations(results_by_channel, command_windows, victim_events)


def digital_timing(channel: AnalogChannel) -> dict[str, object]:
    time_s = channel.time_s
    values = channel.values
    finite = values[np.isfinite(values)]
    if len(finite) < 2:
        return {"threshold": None, "edges": [], "active_intervals": []}

    low = float(np.percentile(finite, 5))
    high = float(np.percentile(finite, 95))
    threshold = (low + high) / 2.0
    states = values >= threshold
    transitions = np.flatnonzero(states[1:] != states[:-1]) + 1

    edges: list[tuple[float, str]] = []
    for index in transitions:
        edge = "rising" if states[index] else "falling"
        edges.append((float(time_s[index]), edge))

    active_intervals: list[tuple[float, float]] = []
    start: float | None = float(time_s[0]) if states[0] else None
    for edge_time, edge in edges:
        if edge == "rising":
            start = edge_time
        elif start is not None:
            active_intervals.append((start, edge_time))
            start = None
    if start is not None:
        active_intervals.append((start, float(time_s[-1])))

    return {"threshold": threshold, "edges": edges, "active_intervals": active_intervals}


def chatter_windows(edges: list[tuple[float, str]], max_span_s: float = 0.02, min_edges: int = 3) -> list[tuple[float, float, int]]:
    windows: list[tuple[float, float, int]] = []
    i = 0
    while i < len(edges):
        j = i
        while j + 1 < len(edges) and edges[j + 1][0] - edges[i][0] <= max_span_s:
            j += 1
        count = j - i + 1
        if count >= min_edges:
            windows.append((edges[i][0], edges[j][0], count))
            i = j + 1
        else:
            i += 1
    return windows


def dropout_windows(digital: dict[str, object], command_windows: list[tuple[float, float, str]]) -> list[tuple[float, float]]:
    intervals = digital["active_intervals"]
    if not isinstance(intervals, list):
        return []
    edges = digital["edges"]
    if not isinstance(edges, list):
        return []

    if not command_windows:
        return []

    low_intervals: list[tuple[float, float]] = []
    active = [(float(start), float(end)) for start, end in intervals]
    if not active:
        return []
    first_high_start = min(start for start, _ in active)
    for command_start, command_end, _ in command_windows:
        cursor = command_start
        for high_start, high_end in active:
            if high_end <= command_start or high_start >= command_end:
                continue
            if high_start > cursor:
                low_intervals.append((cursor, min(high_start, command_end)))
            cursor = max(cursor, high_end)
        if cursor < command_end:
            low_intervals.append((cursor, command_end))

    filtered: list[tuple[float, float]] = []
    for start, end in low_intervals:
        duration = end - start
        if end <= first_high_start:
            continue
        if 0.001 <= duration <= 0.1:
            filtered.append((start, end))
    return filtered


def activity_onset(channel: AnalogChannel, command_windows: list[tuple[float, float, str]]) -> float | None:
    time_s = channel.time_s
    values = channel.values
    if len(values) < 16:
        return None

    if command_windows:
        search_start = min(start for start, _, _ in command_windows)
        pre_mask = time_s < search_start
        search_mask = time_s >= search_start
    else:
        pre_end = time_s[0] + 0.1 * (time_s[-1] - time_s[0])
        pre_mask = time_s <= pre_end
        search_mask = time_s > pre_end

    baseline_values = values[pre_mask]
    search_indices = np.flatnonzero(search_mask)
    if len(baseline_values) < 8 or len(search_indices) == 0:
        return None

    baseline = float(np.median(baseline_values))
    deviations = np.abs(values - baseline)
    base_dev = deviations[pre_mask]
    noise = float(np.median(base_dev) + 6.0 * np.median(np.abs(base_dev - np.median(base_dev))))
    floor = max(noise, 0.05 * float(np.ptp(values)))

    window = max(3, min(200, len(values) // 500))
    kernel = np.ones(window) / window
    smooth = np.convolve(deviations, kernel, mode="same")
    for index in search_indices:
        if smooth[index] > floor:
            return float(time_s[index])
    return None


def _add_digital_observations(result: AnalysisResult, digital: dict[str, object], label: str) -> None:
    threshold = digital["threshold"]
    edges = digital["edges"]
    intervals = digital["active_intervals"]
    if isinstance(threshold, float):
        result.observations.append(f"{label.title()} threshold set at {threshold:.6g} from channel percentiles.")
    if isinstance(edges, list) and edges:
        first = ", ".join(f"{edge} at {time:.6g} s" for time, edge in edges[:6])
        result.observations.append(f"Detected {len(edges)} threshold edges: {first}.")
    if isinstance(intervals, list) and intervals:
        start, end = intervals[0]
        result.observations.append(f"First high/active interval: {start:.6g} s to {end:.6g} s ({(end - start) * 1000:.3g} ms).")


def _add_event_window_spectrum(
    result: AnalysisResult,
    channel: AnalogChannel,
    capture: Capture,
    command_windows: list[tuple[float, float, str]],
) -> None:
    if not command_windows or capture.sample_rate_hz is None:
        return
    start, end, command_channel = command_windows[0]
    mask = (channel.time_s >= start) & (channel.time_s <= end)
    values = channel.values[mask]
    freqs = dominant_frequencies(values, capture.sample_rate_hz, limit=3)
    if freqs:
        joined = ", ".join(f"{freq:.6g} Hz" for freq in freqs)
        result.observations.append(f"During {command_channel} active window, strongest PSD peaks are near {joined}.")


def _add_cross_role_observations(
    results_by_channel: dict[str, AnalysisResult],
    command_windows: list[tuple[float, float, str]],
    victim_events: list[TimelineEvent],
) -> None:
    if not command_windows:
        return
    command_start, command_end, _ = command_windows[0]
    command_events = [
        event
        for result in results_by_channel.values()
        for event in result.events
        if event.role == "command_or_trigger" and event.label == "rose"
    ]
    first_command = min(command_events, key=lambda event: event.time_s) if command_events else None

    source_events = [
        event
        for result in results_by_channel.values()
        for event in result.events
        if event.role == "suspected_source"
    ]
    if first_command and source_events:
        first_source = min(source_events, key=lambda event: event.time_s)
        delta_ms = (first_source.time_s - first_command.time_s) * 1000.0
        for result in results_by_channel.values():
            if any(event.role == "suspected_source" for event in result.events):
                result.relationships.append(
                    f"{first_source.channel_id} source activity began {delta_ms:.3g} ms after {first_command.channel_id} command rose."
                )

    reference_events = [
        event
        for result in results_by_channel.values()
        for event in result.events
        if event.role == "reference_or_common" and command_start <= event.time_s <= command_end
    ]
    if reference_events and victim_events:
        first_reference = min(reference_events, key=lambda event: event.time_s)
        if first_command:
            delta_ms = (first_reference.time_s - first_command.time_s) * 1000.0
            for result in results_by_channel.values():
                if any(event.role == "reference_or_common" for event in result.events):
                    result.relationships.append(
                        f"Reference/common disturbance began {delta_ms:.3g} ms after {first_command.channel_id} command rose."
                    )
        for result in results_by_channel.values():
            if any(event.role == "reference_or_common" for event in result.events):
                result.relationships.append(
                    "Reference/common movement overlaps the command window and victim disturbance; common-mode or shared-reference disturbance remains possible."
                )
                for victim_event in victim_events:
                    if first_reference.time_s <= victim_event.time_s <= command_end:
                        result.relationships.append(
                            f"Reference/common disturbance overlaps victim event '{victim_event.label}' at {victim_event.time_s:.6g} s."
                        )
                        break

    output_events = [
        event
        for result in results_by_channel.values()
        for event in result.events
        if event.role == "output_or_consequence"
    ]
    if victim_events and output_events:
        dropout_events = [event for event in victim_events if "dropout" in event.label]
        first_victim = min(dropout_events or victim_events, key=lambda event: event.time_s)
        first_output = min(output_events, key=lambda event: event.time_s)
        if first_output.time_s >= first_victim.time_s:
            delay_ms = (first_output.time_s - first_victim.time_s) * 1000.0
            for result in results_by_channel.values():
                if any(event.role == "output_or_consequence" for event in result.events):
                    if dropout_events:
                        result.relationships.append(
                            f"Fault output asserted {delay_ms:.3g} ms after victim dropout began."
                        )
                    else:
                        result.relationships.append(
                            f"Output/consequence event occurred {delay_ms:.3g} ms after first relevant victim event."
                        )
    if source_events and reference_events and victim_events:
        for result in results_by_channel.values():
            if result.relationships:
                result.relationships.append(
                    "Evidence supports an event-aligned relationship, but does not prove root cause."
                )


def _first_edge(digital: dict[str, object], edge_name: str) -> float | None:
    edges = digital["edges"]
    if not isinstance(edges, list):
        return None
    for time_s, edge in edges:
        if edge == edge_name:
            return float(time_s)
    return None


def _windowed(time_s: np.ndarray, values: np.ndarray, event_window: tuple[float, float] | None) -> tuple[np.ndarray, np.ndarray]:
    if event_window is None:
        return time_s, values

    start, end = event_window
    mask = (time_s >= start) & (time_s <= end)
    return time_s[mask], values[mask]
