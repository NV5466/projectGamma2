from __future__ import annotations

from typing import Any

import numpy as np
from scipy import signal

from .models import Capture


def channel_windowed_results(capture: Capture, channel: Any, windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    meta = channel.metadata
    signal_type = meta.signal_type if meta else "unknown"
    role = meta.role if meta else "unknown"
    if signal_type in {"digital_like_voltage", "digital_logic_state"}:
        return []
    if role == "unknown" or capture.sample_rate_hz is None:
        return []

    baseline = next((window for window in windows if window["name"] == "baseline_pre_command"), None)
    results: list[dict[str, Any]] = []
    for window in windows:
        if channel.channel_id not in window["applicable_channels"]:
            continue
        if window["name"] == "baseline_pre_command":
            continue
        if not any("PSD" in item for item in window["recommended_analyses"]):
            continue
        summary = spectral_window_summary(capture, channel, window, baseline)
        if summary is not None:
            results.append(summary)
    return results


def spectral_window_summary(
    capture: Capture,
    channel: Any,
    window: dict[str, Any],
    baseline: dict[str, Any] | None,
) -> dict[str, Any] | None:
    fs = capture.sample_rate_hz
    if fs is None:
        return None
    event_bank = window_bank_peaks(channel.time_s, channel.values, fs, window["start_s"], window["end_s"])
    if not event_bank:
        return None
    baseline_bank = window_bank_peaks(channel.time_s, channel.values, fs, baseline["start_s"], baseline["end_s"]) if baseline else {}

    grouped = group_peak_presence(event_bank)
    stable = [item["frequency_hz"] for item in grouped if item["reasonable_window_count"] >= 3]
    amplitude_sensitive = [
        item["frequency_hz"]
        for item in grouped
        if item["reasonable_window_count"] >= 3 and item["amplitude_spread_db"] is not None and item["amplitude_spread_db"] > 6.0
    ]
    window_specific = [item["frequency_hz"] for item in grouped if item["reasonable_window_count"] <= 1]
    event_linked = event_linked_peaks(grouped, event_bank, baseline_bank)

    if stable:
        first = preferred_spectral_peak(stable, event_linked)
        summary = f"Window-local spectral component near {first:.6g} Hz is present across multiple window estimates."
        if event_linked:
            preferred = preferred_event_linked_peak(event_linked)
            group = nearest_group(grouped, preferred["frequency_hz"])
            reasonable_windows = [name for name in group["windows"] if name != "boxcar"] if group else []
            window_text = ", ".join(reasonable_windows) if reasonable_windows else "several non-rectangular windows"
            summary = (
                f"Event-linked spectral component near {preferred['frequency_hz']:.6g} Hz grows relative to baseline "
                f"and appears in {window_text}. Frequency presence is stronger than amplitude precision."
            )
    else:
        summary = "No stable event-window spectral peak survived the window-bank check."

    return {
        "window_name": window["name"],
        "purpose": window["purpose"],
        "baseline_window": baseline["name"] if baseline else None,
        "event_window_bank": event_bank,
        "baseline_window_bank": baseline_bank,
        "stable_peaks_hz": stable[:5],
        "amplitude_sensitive_peaks_hz": amplitude_sensitive[:5],
        "window_specific_peaks_hz": window_specific[:5],
        "event_linked_peaks": event_linked[:5],
        "summary": summary,
    }


def window_bank_peaks(time_s: np.ndarray, values: np.ndarray, sample_rate_hz: float, start_s: float, end_s: float) -> dict[str, list[dict[str, float]]]:
    mask = (time_s >= start_s) & (time_s <= end_s)
    segment = values[mask]
    segment = segment[np.isfinite(segment)]
    if len(segment) < 16:
        return {}
    segment = signal.detrend(segment)
    windows: dict[str, Any] = {
        "hann": "hann",
        "flattop": "flattop",
        "blackmanharris": "blackmanharris",
        "tukey": ("tukey", 0.25),
        "boxcar": "boxcar",
    }
    bank: dict[str, list[dict[str, float]]] = {}
    for name, scipy_window in windows.items():
        nperseg = min(2048, len(segment))
        freqs, psd = signal.welch(segment, fs=sample_rate_hz, window=scipy_window, nperseg=nperseg)
        peaks = top_psd_peaks(freqs, psd, limit=6)
        if peaks:
            bank[name] = peaks
    return bank


def top_psd_peaks(freqs: np.ndarray, psd: np.ndarray, limit: int) -> list[dict[str, float]]:
    if len(freqs) < 2:
        return []
    psd = psd.copy()
    psd[0] = 0
    peak_indices, _ = signal.find_peaks(psd)
    if len(peak_indices) == 0:
        return []
    top = peak_indices[np.argsort(psd[peak_indices])[-limit:]][::-1]
    return [{"frequency_hz": float(freqs[i]), "power": float(psd[i])} for i in top]


def group_peak_presence(bank: dict[str, list[dict[str, float]]]) -> list[dict[str, Any]]:
    reasonable = {"hann", "flattop", "blackmanharris", "tukey"}
    all_peaks: list[tuple[str, float, float]] = []
    for window_name, peaks in bank.items():
        for peak in peaks:
            all_peaks.append((window_name, peak["frequency_hz"], peak["power"]))
    if not all_peaks:
        return []

    tolerance_hz = 125.0
    groups: list[list[tuple[str, float, float]]] = []
    for peak in sorted(all_peaks, key=lambda item: item[1]):
        for group in groups:
            center = float(np.median([item[1] for item in group]))
            if abs(peak[1] - center) <= tolerance_hz:
                group.append(peak)
                break
        else:
            groups.append([peak])

    grouped: list[dict[str, Any]] = []
    for group in groups:
        window_names = sorted({item[0] for item in group})
        powers = [item[2] for item in group if item[2] > 0]
        spread_db = None
        if len(powers) >= 2:
            spread_db = 10.0 * np.log10(max(powers) / max(min(powers), 1e-300))
        grouped.append(
            {
                "frequency_hz": float(np.median([item[1] for item in group])),
                "windows": window_names,
                "reasonable_window_count": len([name for name in window_names if name in reasonable]),
                "amplitude_spread_db": float(spread_db) if spread_db is not None else None,
            }
        )
    return sorted(grouped, key=lambda item: item["reasonable_window_count"], reverse=True)


def event_linked_peaks(grouped: list[dict[str, Any]], event_bank: dict[str, list[dict[str, float]]], baseline_bank: dict[str, list[dict[str, float]]]) -> list[dict[str, float]]:
    event_hann = event_bank.get("hann", [])
    baseline_hann = baseline_bank.get("hann", [])
    linked: list[dict[str, float]] = []
    for item in grouped:
        freq = item["frequency_hz"]
        event_power = nearest_power(event_hann, freq)
        baseline_power = nearest_power(baseline_hann, freq)
        if event_power is None:
            continue
        ratio_db = 120.0 if baseline_power is None or baseline_power <= 0 else 10.0 * np.log10(max(event_power, 1e-300) / max(baseline_power, 1e-300))
        if ratio_db >= 6.0 and item["reasonable_window_count"] >= 2:
            linked.append({"frequency_hz": float(freq), "growth_db": float(ratio_db)})
    return sorted(linked, key=lambda item: item["growth_db"], reverse=True)


def preferred_event_linked_peak(peaks: list[dict[str, float]]) -> dict[str, float]:
    high_frequency = [peak for peak in peaks if peak["frequency_hz"] >= 1000.0]
    candidates = high_frequency or peaks
    return sorted(candidates, key=lambda item: item["growth_db"], reverse=True)[0]


def preferred_spectral_peak(stable: list[float], event_linked: list[dict[str, float]]) -> float:
    if event_linked:
        return preferred_event_linked_peak(event_linked)["frequency_hz"]
    high_frequency = [freq for freq in stable if freq >= 1000.0]
    return high_frequency[0] if high_frequency else stable[0]


def nearest_group(grouped: list[dict[str, Any]], freq_hz: float) -> dict[str, Any] | None:
    if not grouped:
        return None
    nearest = min(grouped, key=lambda item: abs(item["frequency_hz"] - freq_hz))
    return nearest if abs(nearest["frequency_hz"] - freq_hz) <= 125.0 else None


def nearest_power(peaks: list[dict[str, float]], freq_hz: float) -> float | None:
    if not peaks:
        return None
    nearest = min(peaks, key=lambda peak: abs(peak["frequency_hz"] - freq_hz))
    if abs(nearest["frequency_hz"] - freq_hz) > 125.0:
        return None
    return nearest["power"]
