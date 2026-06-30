
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from scipy.ndimage import binary_closing, binary_dilation


@dataclass
class SharpEventConfig:
    expected_f_min_hz: float = 45.0
    expected_f_max_hz: float = 70.0

    # Persistent harmonics belong to the baseline, not the event list.
    baseline_harmonics: tuple[int, ...] = (1, 3, 5, 7)

    residual_sigma: float = 5.0
    derivative_sigma: float = 6.0
    derivative_residual_gate_sigma: float = 1.5

    smooth_window_s: float = 35e-6
    smooth_polyorder: int = 3

    merge_gap_s: float = 80e-6
    event_padding_s: float = 45e-6
    min_event_width_s: float = 15e-6
    max_event_width_s: float = 5e-3

    zero_cross_exclusion_fraction: float = 0.10

    # Notch classification
    notch_max_width_s: float = 1.5e-3
    notch_min_inward_fraction: float = 0.45
    notch_phase_tolerance_deg: float = 12.0
    min_grid_events: int = 4
    min_grid_concentration: float = 0.55


def _robust_sigma(x: np.ndarray, trim_quantile: float = 0.80) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return 0.0, np.finfo(float).eps

    med = float(np.median(x))
    centered = np.abs(x - med)
    cutoff = float(np.quantile(centered, trim_quantile))
    trimmed = x[centered <= cutoff]
    if trimmed.size < 8:
        trimmed = x

    med = float(np.median(trimmed))
    mad = float(np.median(np.abs(trimmed - med)))
    sigma = max(1.4826 * mad, np.finfo(float).eps)
    return med, sigma


def _estimate_fundamental_fft(
    t: np.ndarray,
    v: np.ndarray,
    f_min: float,
    f_max: float,
) -> float:
    dt = float(np.median(np.diff(t)))
    n = len(v)

    centered = v - np.mean(v)
    spectrum = np.fft.rfft(centered * np.hanning(n))
    freqs = np.fft.rfftfreq(n, dt)

    band = (freqs >= f_min) & (freqs <= f_max)
    if not np.any(band):
        raise ValueError("No FFT bins fall inside the requested fundamental band.")

    band_indices = np.flatnonzero(band)
    peak_index = int(band_indices[np.argmax(np.abs(spectrum[band]))])

    if 0 < peak_index < len(spectrum) - 1:
        y0, y1, y2 = np.log(
            np.abs(spectrum[peak_index - 1:peak_index + 2]) + 1e-30
        )
        denom = y0 - 2.0 * y1 + y2
        delta = 0.5 * (y0 - y2) / denom if abs(denom) > 1e-30 else 0.0
    else:
        delta = 0.0

    return float((peak_index + delta) / (n * dt))


def _fit_harmonic_baseline(
    t: np.ndarray,
    v: np.ndarray,
    f0_hz: float,
    harmonics: tuple[int, ...],
) -> tuple[np.ndarray, dict[str, float]]:
    columns = [np.ones_like(t)]
    column_names = ["dc"]

    for h in harmonics:
        w = 2.0 * np.pi * h * f0_hz
        columns.append(np.sin(w * t))
        columns.append(np.cos(w * t))
        column_names.extend([f"sin_{h}", f"cos_{h}"])

    design = np.column_stack(columns)
    coeff, *_ = np.linalg.lstsq(design, v, rcond=None)
    fitted = design @ coeff

    lookup = dict(zip(column_names, coeff))
    sin_1 = float(lookup.get("sin_1", 0.0))
    cos_1 = float(lookup.get("cos_1", 0.0))

    return fitted, {
        "frequency_hz": float(f0_hz),
        "fundamental_amplitude": float(np.hypot(sin_1, cos_1)),
        "fundamental_phase_rad": float(np.arctan2(cos_1, sin_1)),
        "dc_offset": float(coeff[0]),
    }


def _segments(mask: np.ndarray) -> list[tuple[int, int]]:
    edges = np.diff(mask.astype(np.int8), prepend=0, append=0)
    starts = np.flatnonzero(edges == 1)
    stops = np.flatnonzero(edges == -1)
    return list(zip(starts, stops))


def _phase_deg(time_s: float, f0_hz: float, phase_rad: float) -> float:
    return float(
        (
            360.0 * f0_hz * time_s
            + math.degrees(phase_rad)
        )
        % 360.0
    )


def detect_sharp_events(
    t: np.ndarray,
    voltage: np.ndarray,
    config: SharpEventConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    cfg = config or SharpEventConfig()

    t = np.asarray(t, dtype=float)
    voltage = np.asarray(voltage, dtype=float)

    if t.ndim != 1 or voltage.ndim != 1 or len(t) != len(voltage):
        raise ValueError("t and voltage must be equal-length 1D arrays.")
    if len(t) < 64:
        raise ValueError("Need at least 64 samples.")
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(voltage)):
        raise ValueError("t and voltage must contain finite values only.")

    dt_values = np.diff(t)
    dt = float(np.median(dt_values))
    if dt <= 0:
        raise ValueError("Time must be strictly increasing.")
    if np.max(np.abs(dt_values - dt)) > 0.01 * dt:
        raise ValueError("This seed assumes uniformly sampled data.")

    fs = 1.0 / dt

    f0 = _estimate_fundamental_fft(
        t,
        voltage,
        cfg.expected_f_min_hz,
        cfg.expected_f_max_hz,
    )
    baseline, fit = _fit_harmonic_baseline(
        t,
        voltage,
        f0,
        cfg.baseline_harmonics,
    )

    window = max(5, int(round(cfg.smooth_window_s * fs)))
    if window % 2 == 0:
        window += 1
    if window >= len(voltage):
        window = len(voltage) - 1 if len(voltage) % 2 == 0 else len(voltage)
    if window <= cfg.smooth_polyorder:
        window = cfg.smooth_polyorder + 3
        if window % 2 == 0:
            window += 1

    smooth_voltage = savgol_filter(
        voltage,
        window_length=window,
        polyorder=cfg.smooth_polyorder,
        mode="interp",
    )
    smooth_baseline = savgol_filter(
        baseline,
        window_length=window,
        polyorder=cfg.smooth_polyorder,
        mode="interp",
    )

    residual = smooth_voltage - smooth_baseline
    derivative_residual = np.gradient(residual, dt)

    residual_center, residual_robust_sigma = _robust_sigma(residual)
    derivative_center, derivative_robust_sigma = _robust_sigma(derivative_residual)

    residual_threshold = cfg.residual_sigma * residual_robust_sigma
    derivative_threshold = cfg.derivative_sigma * derivative_robust_sigma
    derivative_gate = (
        cfg.derivative_residual_gate_sigma * residual_robust_sigma
    )

    residual_activity = (
        np.abs(residual - residual_center) > residual_threshold
    )
    derivative_activity = (
        (np.abs(derivative_residual - derivative_center) > derivative_threshold)
        & (np.abs(residual - residual_center) > derivative_gate)
    )

    activity = residual_activity | derivative_activity

    pad_samples = max(1, int(round(cfg.event_padding_s * fs)))
    activity = binary_dilation(
        activity,
        structure=np.ones(2 * pad_samples + 1, dtype=bool),
    )

    merge_samples = max(1, int(round(cfg.merge_gap_s * fs)))
    activity = binary_closing(
        activity,
        structure=np.ones(merge_samples, dtype=bool),
    )

    rows: list[dict] = []

    for event_id, (start, stop) in enumerate(_segments(activity), start=1):
        if stop <= start:
            continue

        width_s = (stop - start) * dt
        if not (cfg.min_event_width_s <= width_s <= cfg.max_event_width_s):
            continue

        sl = slice(start, stop)
        local_r = residual[sl]
        local_abs = np.abs(local_r)

        peak_rel = int(np.argmax(local_abs))
        peak_index = start + peak_rel
        peak_time_s = float(t[peak_index])

        fundamental_at_peak = (
            fit["fundamental_amplitude"]
            * np.sin(
                2.0 * np.pi * fit["frequency_hz"] * peak_time_s
                + fit["fundamental_phase_rad"]
            )
        )

        # Positive inward signal means the measured waveform moved toward zero.
        baseline_sign = np.sign(smooth_baseline[sl])
        inward_signal = -baseline_sign * local_r
        inward_area = float(np.trapezoid(np.maximum(inward_signal, 0.0), t[sl]))
        total_abs_area = float(np.trapezoid(np.abs(local_r), t[sl]))
        inward_fraction = (
            inward_area / total_abs_area
            if total_abs_area > np.finfo(float).eps
            else 0.0
        )

        positive_area = float(np.trapezoid(np.maximum(local_r, 0.0), t[sl]))
        negative_area = float(np.trapezoid(np.maximum(-local_r, 0.0), t[sl]))
        signed_area = float(np.trapezoid(local_r, t[sl]))

        local_d = derivative_residual[sl]
        derivative_bipolar = bool(np.any(local_d > 0) and np.any(local_d < 0))

        # Residual sign changes help distinguish a single-polarity impulse
        # from an oscillatory event later.
        signs = np.sign(local_r)
        signs = signs[signs != 0]
        sign_changes = (
            int(np.sum(signs[1:] != signs[:-1]))
            if signs.size > 1
            else 0
        )

        away_from_zero = bool(
            abs(fundamental_at_peak)
            >= cfg.zero_cross_exclusion_fraction
            * fit["fundamental_amplitude"]
        )

        rows.append(
            {
                "event_id": event_id,
                "start_time_s": float(t[start]),
                "peak_time_s": peak_time_s,
                "end_time_s": float(t[stop - 1]),
                "width_us": width_s * 1e6,
                "phase_deg": _phase_deg(
                    peak_time_s,
                    fit["frequency_hz"],
                    fit["fundamental_phase_rad"],
                ),
                "signed_peak_v": float(local_r[peak_rel]),
                "peak_abs_v": float(local_abs[peak_rel]),
                "signed_area_v_us": signed_area * 1e6,
                "absolute_area_v_us": total_abs_area * 1e6,
                "positive_area_v_us": positive_area * 1e6,
                "negative_area_v_us": negative_area * 1e6,
                "inward_fraction": inward_fraction,
                "max_abs_dvdt_v_per_s": float(np.max(np.abs(local_d))),
                "derivative_bipolar": derivative_bipolar,
                "residual_sign_changes": sign_changes,
                "away_from_zero_crossing": away_from_zero,
            }
        )

    events = pd.DataFrame(rows)

    grid_offset_deg = float("nan")
    grid_concentration = 0.0

    if not events.empty:
        short_inward = events[
            (events["width_us"] <= cfg.notch_max_width_s * 1e6)
            & (events["inward_fraction"] >= cfg.notch_min_inward_fraction)
            & events["away_from_zero_crossing"]
        ].copy()

        if len(short_inward) >= cfg.min_grid_events:
            phases = short_inward["phase_deg"].to_numpy(dtype=float)
            weights = np.maximum(
                short_inward["absolute_area_v_us"].to_numpy(dtype=float),
                np.finfo(float).eps,
            )

            phasor = np.sum(
                weights * np.exp(1j * 2.0 * np.pi * phases / 60.0)
            )
            grid_concentration = float(
                np.abs(phasor) / np.sum(weights)
            )
            grid_offset_deg = float(
                (
                    np.angle(phasor) % (2.0 * np.pi)
                )
                * 60.0
                / (2.0 * np.pi)
            )

    if not events.empty:
        events["commutation_grid_offset_deg"] = grid_offset_deg
        events["commutation_grid_concentration"] = grid_concentration

        if np.isfinite(grid_offset_deg):
            signed_grid_error = (
                (events["phase_deg"] - grid_offset_deg + 30.0) % 60.0
            ) - 30.0
            events["phase_grid_error_deg"] = np.abs(signed_grid_error)
        else:
            events["phase_grid_error_deg"] = np.nan

        notch_mask = (
            (events["width_us"] <= cfg.notch_max_width_s * 1e6)
            & (events["inward_fraction"] >= cfg.notch_min_inward_fraction)
            & events["away_from_zero_crossing"]
            & events["derivative_bipolar"]
            & (events["phase_grid_error_deg"] <= cfg.notch_phase_tolerance_deg)
            & (grid_concentration >= cfg.min_grid_concentration)
        )

        events["event_class"] = np.where(
            notch_mask,
            "commutation_notch",
            "singular_event",
        )

    if events.empty:
        counts = pd.DataFrame(
            [{
                "total_events": 0,
                "commutation_notches": 0,
                "singular_events": 0,
                "events_per_second": 0.0,
                "notches_per_cycle": 0.0,
                "grid_offset_deg_mod_60": np.nan,
                "grid_concentration": 0.0,
            }]
        )
    else:
        notch_count = int(np.sum(events["event_class"] == "commutation_notch"))
        singular_count = int(np.sum(events["event_class"] == "singular_event"))
        duration_s = float(t[-1] - t[0])
        cycles = duration_s * fit["frequency_hz"]

        counts = pd.DataFrame(
            [{
                "total_events": int(len(events)),
                "commutation_notches": notch_count,
                "singular_events": singular_count,
                "events_per_second": len(events) / duration_s,
                "notches_per_cycle": notch_count / cycles if cycles > 0 else 0.0,
                "grid_offset_deg_mod_60": grid_offset_deg,
                "grid_concentration": grid_concentration,
            }]
        )

    diagnostics = {
        "baseline": baseline,
        "smooth_voltage": smooth_voltage,
        "smooth_baseline": smooth_baseline,
        "residual": residual,
        "derivative_residual": derivative_residual,
        "activity_mask": activity,
        "fit": fit,
        "sampling_rate_hz": fs,
        "residual_threshold_v": residual_threshold,
        "derivative_threshold_v_per_s": derivative_threshold,
        "grid_offset_deg_mod_60": grid_offset_deg,
        "grid_concentration": grid_concentration,
    }

    return events, counts, diagnostics


if __name__ == "__main__":
    # Expected CSV columns:
    #   time_s
    #   voltage_v
    data = pd.read_csv("capture.csv")

    events, counts, diagnostics = detect_sharp_events(
        data["time_s"].to_numpy(),
        data["voltage_v"].to_numpy(),
    )

    events.to_csv("sharp_events.csv", index=False)
    counts.to_csv("sharp_event_counts.csv", index=False)

    print(diagnostics["fit"])
    print(counts)
    print(events)
