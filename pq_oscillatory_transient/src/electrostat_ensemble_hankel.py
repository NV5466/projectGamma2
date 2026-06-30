from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
import argparse
import json

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from scipy.ndimage import binary_closing, binary_dilation


@dataclass
class EnsembleHankelConfig:
    # Residual event detection
    residual_sigma: float = 8.0
    derivative_sigma: float = 10.0
    derivative_gate_sigma: float = 5.0
    merge_gap_s: float = 120e-6
    event_padding_s: float = 30e-6
    min_event_width_s: float = 20e-6
    max_event_width_s: float = 8e-3
    analysis_post_peak_s: float = 2e-3

    # Matrix pencil
    pencil_rows_fraction: float = 0.45
    max_model_order: int = 6
    min_model_order: int = 1
    svd_relative_floor: float = 0.02

    # Accepted modes
    max_reconstruction_nrmse: float = 0.35
    stable_growth_tolerance_per_s: float = 100.0
    min_mode_amplitude_fraction: float = 0.08
    oscillatory_min_frequency_hz: float = 200.0

    # Cross-capture pole clustering
    cluster_frequency_relative_tolerance: float = 0.08
    cluster_decay_relative_tolerance: float = 0.35
    cluster_min_events: int = 2


def _validate(time_s: np.ndarray, captures: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    time_s = np.asarray(time_s, dtype=float)
    captures = np.asarray(captures, dtype=float)
    if time_s.ndim != 1 or captures.ndim != 2:
        raise ValueError("time_s must be 1D and captures must be 2D.")
    if captures.shape[1] != time_s.size:
        raise ValueError("Each capture must have the same sample count as time_s.")
    if captures.shape[0] < 2 or time_s.size < 64:
        raise ValueError("Need at least two captures and 64 samples.")
    if not np.all(np.isfinite(time_s)) or not np.all(np.isfinite(captures)):
        raise ValueError("Inputs must contain finite values only.")
    steps = np.diff(time_s)
    dt = float(np.median(steps))
    if dt <= 0 or np.max(np.abs(steps - dt)) > 0.01 * dt:
        raise ValueError("This seed requires uniformly sampled, increasing time data.")
    return time_s, captures, dt


def build_explicit_reference(captures: np.ndarray, method: str = "median") -> np.ndarray:
    captures = np.asarray(captures, dtype=float)
    if captures.ndim != 2:
        raise ValueError("captures must be 2D.")
    if method == "median":
        return np.median(captures, axis=0)
    if method == "mean":
        return np.mean(captures, axis=0)
    raise ValueError("method must be 'median' or 'mean'.")


def _robust_sigma(x: np.ndarray, trim_quantile: float = 0.80) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    center = float(np.median(x))
    deviation = np.abs(x - center)
    trimmed = x[deviation <= np.quantile(deviation, trim_quantile)]
    if trimmed.size < 8:
        trimmed = x
    center = float(np.median(trimmed))
    mad = float(np.median(np.abs(trimmed - center)))
    return center, max(1.4826 * mad, np.finfo(float).eps)


def _segments(mask: np.ndarray) -> list[tuple[int, int]]:
    edges = np.diff(mask.astype(np.int8), prepend=0, append=0)
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def detect_residual_event_windows(
    time_s: np.ndarray,
    residual: np.ndarray,
    config: EnsembleHankelConfig,
) -> tuple[pd.DataFrame, dict[int, np.ndarray]]:
    dt = float(np.median(np.diff(time_s)))
    fs = 1.0 / dt
    residual_center, residual_sigma = _robust_sigma(residual)
    derivative = np.gradient(residual, dt)
    derivative_center, derivative_sigma = _robust_sigma(derivative)

    activity = np.abs(residual - residual_center) > config.residual_sigma * residual_sigma
    activity |= (
        (np.abs(derivative - derivative_center) > config.derivative_sigma * derivative_sigma)
        & (np.abs(residual - residual_center) > config.derivative_gate_sigma * residual_sigma)
    )

    pad = max(1, int(round(config.event_padding_s * fs)))
    activity = binary_dilation(activity, structure=np.ones(2 * pad + 1, dtype=bool))
    merge = max(1, int(round(config.merge_gap_s * fs)))
    activity = binary_closing(activity, structure=np.ones(merge, dtype=bool))

    analysis_samples = max(32, int(round(config.analysis_post_peak_s * fs)))
    rows: list[dict] = []
    windows: dict[int, np.ndarray] = {}
    event_id = 0

    for start, stop in _segments(activity):
        width_s = (stop - start) * dt
        if not (config.min_event_width_s <= width_s <= config.max_event_width_s):
            continue
        peak = start + int(np.argmax(np.abs(residual[start:stop])))
        analysis_stop = peak + analysis_samples
        if analysis_stop > residual.size:
            continue

        event_id += 1
        window = residual[peak:analysis_stop].copy()
        tail = max(4, window.size // 10)
        window -= np.median(window[-tail:])
        rows.append({
            "event_id": event_id,
            "segment_start_time_s": float(time_s[start]),
            "event_peak_time_s": float(time_s[peak]),
            "segment_end_time_s": float(time_s[stop - 1]),
            "segment_width_us": width_s * 1e6,
            "peak_abs_v": float(np.max(np.abs(residual[start:stop]))),
            "analysis_start_index": int(peak),
            "analysis_stop_index": int(analysis_stop),
            "residual_noise_sigma_v": residual_sigma,
        })
        windows[event_id] = window

    return pd.DataFrame(rows), windows


def hankel_pair(signal: np.ndarray, rows: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    signal = np.asarray(signal, dtype=np.complex128)
    if signal.size < 8:
        raise ValueError("A matrix-pencil window needs at least eight samples.")
    rows = signal.size // 2 if rows is None else int(rows)
    rows = max(2, min(rows, signal.size - 2))
    windows = sliding_window_view(signal, rows + 1)
    return windows[:, :rows].T.copy(), windows[:, 1:].T.copy()


def _select_order(s: np.ndarray, config: EnsembleHankelConfig) -> int:
    maximum = min(config.max_model_order, max(1, s.size - 1))
    if maximum <= 1:
        return 1
    eligible = np.flatnonzero(s[:maximum] / s[0] >= config.svd_relative_floor)
    search_count = int(eligible[-1]) + 1 if eligible.size else 1
    gaps = s[:maximum] / np.maximum(s[1:maximum + 1], np.finfo(float).eps)
    order = int(np.argmax(gaps[:search_count])) + 1
    return max(config.min_model_order, min(order, maximum))


def matrix_pencil_modes(
    signal: np.ndarray,
    sample_interval_s: float,
    config: EnsembleHankelConfig,
    model_order: int | None = None,
) -> tuple[pd.DataFrame, dict]:
    signal = np.asarray(signal, dtype=np.complex128)
    rows = int(round(config.pencil_rows_fraction * signal.size))
    h0, h1 = hankel_pair(signal, rows)
    u, s, vh = np.linalg.svd(h0, full_matrices=False)
    order = model_order or _select_order(s, config)
    order = max(1, min(order, s.size))

    ur = u[:, :order]
    vr = vh.conj().T[:, :order]
    shift = ur.conj().T @ h1 @ vr @ np.diag(1.0 / s[:order])
    z = np.linalg.eigvals(shift)
    z = z[np.isfinite(z) & (np.abs(z) > 1e-12)]
    p = np.log(z) / sample_interval_s

    k = np.arange(signal.size)
    vandermonde = np.column_stack([pole ** k for pole in z])
    amplitudes, *_ = np.linalg.lstsq(vandermonde, signal, rcond=None)
    reconstruction = vandermonde @ amplitudes
    denominator = max(np.linalg.norm(signal - np.mean(signal)), np.finfo(float).eps)
    nrmse = float(np.linalg.norm(signal - reconstruction) / denominator)
    maximum_amplitude = max(float(np.max(np.abs(amplitudes))), np.finfo(float).eps)

    mode_rows = []
    for mode_index, (zp, pp, amplitude) in enumerate(zip(z, p, amplitudes), start=1):
        decay = -float(pp.real)
        angular_frequency = abs(float(pp.imag))
        frequency_hz = angular_frequency / (2.0 * np.pi)
        natural_frequency = float(np.hypot(decay, angular_frequency))
        mode_rows.append({
            "mode_index": mode_index,
            "discrete_pole_real": float(zp.real),
            "discrete_pole_imag": float(zp.imag),
            "continuous_pole_real_per_s": float(pp.real),
            "continuous_pole_imag_rad_per_s": float(pp.imag),
            "decay_rate_per_s": decay,
            "frequency_hz": frequency_hz,
            "time_constant_ms": 1000.0 / decay if decay > 0 else np.nan,
            "damping_ratio": decay / natural_frequency if natural_frequency > 0 else np.nan,
            "amplitude_abs": float(abs(amplitude)),
            "amplitude_phase_rad": float(np.angle(amplitude)),
            "amplitude_fraction": float(abs(amplitude) / maximum_amplitude),
            "model_order": order,
            "reconstruction_nrmse": nrmse,
        })

    return pd.DataFrame(mode_rows), {
        "singular_values": s,
        "selected_model_order": order,
        "reconstruction": reconstruction,
        "reconstruction_nrmse": nrmse,
    }


def _collapse_real_signal_modes(raw_modes: pd.DataFrame, config: EnsembleHankelConfig) -> pd.DataFrame:
    if raw_modes.empty:
        return raw_modes.copy()
    threshold = 2.0 * np.pi * config.oscillatory_min_frequency_hz
    accepted: list[dict] = []

    for _, mode in raw_modes.iterrows():
        if mode["amplitude_fraction"] < config.min_mode_amplitude_fraction:
            continue
        if mode["reconstruction_nrmse"] > config.max_reconstruction_nrmse:
            continue
        if mode["continuous_pole_real_per_s"] > config.stable_growth_tolerance_per_s:
            continue

        row = mode.to_dict()
        imaginary = row["continuous_pole_imag_rad_per_s"]
        if abs(imaginary) < threshold:
            row["mode_type"] = "real_decay"
            accepted.append(row)
        elif imaginary > 0:
            row["mode_type"] = "oscillatory"
            row["amplitude_abs"] *= 2.0
            accepted.append(row)

    return pd.DataFrame(accepted)


def _cluster_modes(
    modes: pd.DataFrame,
    config: EnsembleHankelConfig,
    total_capture_count: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if modes.empty:
        return modes.copy(), pd.DataFrame()

    clustered = modes.copy()
    clustered["cluster_id"] = -1
    clusters: list[dict] = []
    next_id = 0

    for mode_type in ("oscillatory", "real_decay"):
        indices = list(clustered.index[clustered["mode_type"] == mode_type])
        indices.sort(key=lambda i: clustered.loc[i, "frequency_hz"] if mode_type == "oscillatory" else clustered.loc[i, "decay_rate_per_s"])

        for index in indices:
            frequency = float(clustered.loc[index, "frequency_hz"])
            decay = float(clustered.loc[index, "decay_rate_per_s"])
            best = None
            best_distance = np.inf

            for cluster in clusters:
                if cluster["mode_type"] != mode_type:
                    continue
                center_frequency = float(np.median(cluster["frequencies"])) if mode_type == "oscillatory" else 0.0
                center_decay = float(np.median(cluster["decays"]))
                frequency_distance = abs(frequency - center_frequency) / max(center_frequency, np.finfo(float).eps) if mode_type == "oscillatory" else 0.0
                decay_distance = abs(decay - center_decay) / max(center_decay, np.finfo(float).eps)
                distance = frequency_distance + decay_distance
                if (
                    frequency_distance <= config.cluster_frequency_relative_tolerance
                    and decay_distance <= config.cluster_decay_relative_tolerance
                    and distance < best_distance
                ):
                    best = cluster
                    best_distance = distance

            if best is None:
                next_id += 1
                best = {"cluster_id": next_id, "mode_type": mode_type, "frequencies": [], "decays": [], "indices": []}
                clusters.append(best)

            best["frequencies"].append(frequency)
            best["decays"].append(decay)
            best["indices"].append(index)
            clustered.loc[index, "cluster_id"] = best["cluster_id"]

    summaries = []
    for cluster in clusters:
        subset = clustered.loc[cluster["indices"]]
        unique_events = subset[["capture_id", "event_id"]].drop_duplicates()
        unique_capture_count = int(subset["capture_id"].nunique())
        summaries.append({
            "cluster_id": cluster["cluster_id"],
            "mode_type": cluster["mode_type"],
            "event_count": int(unique_events.shape[0]),
            "unique_capture_count": unique_capture_count,
            "occurrence_rate": unique_capture_count / total_capture_count,
            "median_frequency_hz": float(np.median(subset["frequency_hz"])),
            "frequency_std_hz": float(np.std(subset["frequency_hz"])),
            "median_decay_rate_per_s": float(np.median(subset["decay_rate_per_s"])),
            "decay_rate_std_per_s": float(np.std(subset["decay_rate_per_s"])),
            "median_time_constant_ms": float(np.nanmedian(subset["time_constant_ms"])),
            "median_reconstruction_nrmse": float(np.median(subset["reconstruction_nrmse"])),
            "capture_ids": ",".join(map(str, sorted(subset["capture_id"].astype(int).unique()))),
        })

    summary = pd.DataFrame(summaries)
    if not summary.empty:
        summary = summary.sort_values(["mode_type", "event_count"], ascending=[True, False]).reset_index(drop=True)
    return clustered, summary


def _stacked_matrix_pencil(
    signals: Sequence[np.ndarray],
    sample_interval_s: float,
    config: EnsembleHankelConfig,
    model_order: int,
) -> np.ndarray:
    if not signals:
        return np.array([], dtype=np.complex128)
    common_length = min(signal.size for signal in signals)
    rows = int(round(config.pencil_rows_fraction * common_length))
    h0_blocks, h1_blocks = [], []

    for signal in signals:
        normalized = np.asarray(signal[:common_length], dtype=np.complex128)
        norm = float(np.linalg.norm(normalized))
        if norm > 0:
            normalized /= norm
        h0, h1 = hankel_pair(normalized, rows)
        h0_blocks.append(h0)
        h1_blocks.append(h1)

    h0 = np.hstack(h0_blocks)
    h1 = np.hstack(h1_blocks)
    u, s, vh = np.linalg.svd(h0, full_matrices=False)
    order = max(1, min(model_order, s.size))
    ur = u[:, :order]
    vr = vh.conj().T[:, :order]
    shift = ur.conj().T @ h1 @ vr @ np.diag(1.0 / s[:order])
    return np.log(np.linalg.eigvals(shift)) / sample_interval_s


def analyze_measurement_ensemble(
    time_s: np.ndarray,
    captures: np.ndarray,
    reference_waveform: np.ndarray | None = None,
    config: EnsembleHankelConfig | None = None,
) -> dict:
    config = config or EnsembleHankelConfig()
    time_s, captures, dt = _validate(time_s, captures)

    if reference_waveform is None:
        reference_waveform = build_explicit_reference(captures, "median")
        reference_source = "pointwise_median"
    else:
        reference_waveform = np.asarray(reference_waveform, dtype=float)
        if reference_waveform.shape != time_s.shape:
            raise ValueError("reference_waveform must match time_s.")
        reference_source = "supplied_explicit_waveform"

    residuals = captures - reference_waveform
    event_tables, mode_tables = [], []
    event_windows: dict[tuple[int, int], np.ndarray] = {}

    for capture_id, residual in enumerate(residuals):
        events, windows = detect_residual_event_windows(time_s, residual, config)
        if events.empty:
            continue
        events["capture_id"] = capture_id
        event_tables.append(events)

        for event_id, window in windows.items():
            event_windows[(capture_id, event_id)] = window
            raw_modes, _ = matrix_pencil_modes(window, dt, config)
            accepted = _collapse_real_signal_modes(raw_modes, config)
            if accepted.empty:
                continue
            metadata = events.loc[events["event_id"] == event_id].iloc[0]
            accepted["capture_id"] = capture_id
            accepted["event_id"] = event_id
            accepted["event_peak_time_s"] = float(metadata["event_peak_time_s"])
            accepted["event_peak_abs_v"] = float(metadata["peak_abs_v"])
            accepted["event_segment_width_us"] = float(metadata["segment_width_us"])
            mode_tables.append(accepted)

    events = pd.concat(event_tables, ignore_index=True) if event_tables else pd.DataFrame()
    modes = pd.concat(mode_tables, ignore_index=True) if mode_tables else pd.DataFrame()
    if modes.empty:
        return {"reference_waveform": reference_waveform, "reference_source": reference_source, "residuals": residuals, "events": events, "modes": modes, "clusters": pd.DataFrame()}

    modes, clusters = _cluster_modes(modes, config, captures.shape[0])
    clusters["stacked_frequency_hz"] = np.nan
    clusters["stacked_decay_rate_per_s"] = np.nan
    clusters["stacked_time_constant_ms"] = np.nan

    for cluster_index, cluster in clusters.iterrows():
        if cluster["event_count"] < config.cluster_min_events:
            continue
        subset = modes[modes["cluster_id"] == cluster["cluster_id"]]
        keys = list(dict.fromkeys(zip(subset["capture_id"].astype(int), subset["event_id"].astype(int))))
        poles = _stacked_matrix_pencil(
            [event_windows[key] for key in keys],
            dt,
            config,
            2 if cluster["mode_type"] == "oscillatory" else 1,
        )
        if poles.size == 0:
            continue

        if cluster["mode_type"] == "oscillatory":
            candidates = poles[poles.imag > 0]
            candidates = candidates if candidates.size else poles
            target = float(cluster["median_frequency_hz"])
            selected = candidates[np.argmin(np.abs(np.abs(candidates.imag) / (2.0 * np.pi) - target))]
        else:
            selected = poles[np.argmin(np.abs(poles.imag))]

        decay = -float(selected.real)
        clusters.loc[cluster_index, "stacked_frequency_hz"] = abs(float(selected.imag)) / (2.0 * np.pi)
        clusters.loc[cluster_index, "stacked_decay_rate_per_s"] = decay
        clusters.loc[cluster_index, "stacked_time_constant_ms"] = 1000.0 / decay if decay > 0 else np.nan

    return {"reference_waveform": reference_waveform, "reference_source": reference_source, "residuals": residuals, "events": events, "modes": modes, "clusters": clusters}


def load_aligned_capture_csvs(
    paths: Sequence[str | Path],
    time_column: str = "time_s",
    value_column: str = "voltage_v",
) -> tuple[np.ndarray, np.ndarray]:
    if len(paths) < 2:
        raise ValueError("Provide at least two capture CSV files.")
    reference_time = None
    captures = []
    for path in paths:
        data = pd.read_csv(path)
        if time_column not in data.columns or value_column not in data.columns:
            raise ValueError(f"{path} must contain {time_column!r} and {value_column!r}.")
        time_s = data[time_column].to_numpy(dtype=float)
        values = data[value_column].to_numpy(dtype=float)
        if reference_time is None:
            reference_time = time_s
        elif not np.allclose(time_s, reference_time, rtol=0.0, atol=1e-12):
            raise ValueError("All captures must share the same aligned time vector.")
        captures.append(values)
    return reference_time, np.vstack(captures)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Hankel/matrix-pencil poles across aligned ElectroStat captures.")
    parser.add_argument("captures", nargs="+", help="Aligned capture CSV files containing time_s and voltage_v.")
    parser.add_argument("--reference", help="Optional explicit WaveCompare 2 reference CSV.")
    parser.add_argument("--output-prefix", default="electrostat_ensemble")
    args = parser.parse_args()

    time_s, captures = load_aligned_capture_csvs(args.captures)
    reference = None
    if args.reference:
        reference = pd.read_csv(args.reference)["voltage_v"].to_numpy(dtype=float)

    result = analyze_measurement_ensemble(time_s, captures, reference)
    prefix = Path(args.output_prefix)
    result["events"].to_csv(f"{prefix}_events.csv", index=False)
    result["modes"].to_csv(f"{prefix}_individual_modes.csv", index=False)
    result["clusters"].to_csv(f"{prefix}_clusters.csv", index=False)
    pd.DataFrame({"time_s": time_s, "reference_voltage_v": result["reference_waveform"]}).to_csv(f"{prefix}_reference.csv", index=False)
    print(json.dumps({
        "reference_source": result["reference_source"],
        "capture_count": int(captures.shape[0]),
        "event_count": int(len(result["events"])),
        "accepted_mode_count": int(len(result["modes"])),
        "cluster_count": int(len(result["clusters"])),
    }, indent=2))


if __name__ == "__main__":
    main()
