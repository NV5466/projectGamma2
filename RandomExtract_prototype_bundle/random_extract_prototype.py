
#!/usr/bin/env python3
"""
RandomExtract prototype for Gamma / ElectroStat.

Purpose
-------
Given already-aligned repeated captures, remove the WaveCompare 2 collective
waveform and analyze the residuals in two complementary spaces:

1. Piecewise-linear residual geometry:
      delta_y[k, n] = residual[k, n+1] - residual[k, n]

2. Residual FFT structure:
      R[k, f] = FFT(residual[k, n])

The module detects residual spectral peaks per capture, groups nearby peaks into
frequency tracks across capture index, and classifies persistent, intermittent,
phase-coherent, asynchronous, and growing narrowbands.

Input convention
----------------
captures.shape == (capture_count, sample_count)

CSV CLI convention:
- First column: time in seconds
- Remaining columns: one capture per column
- All captures must already be aligned to the same event/sample grid

This is a prototype, not a final diagnostic decision engine. It preserves the
residuals and reports evidence without declaring a physical fault mechanism.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.ndimage import median_filter
from scipy.signal import find_peaks, get_window
from scipy.stats import theilslopes


_EPS = np.finfo(float).eps


@dataclass
class PeakObservation:
    capture_index: int
    frequency_hz: float
    amplitude: float
    phase_rad: float
    prominence: float
    local_floor: float


@dataclass
class FrequencyTrack:
    track_id: int
    center_frequency_hz: float
    occupancy: float
    capture_count: int
    observation_count: int
    median_amplitude: float
    amplitude_mad: float
    frequency_mad_hz: float
    phase_coherence: float
    axial_phase_coherence: float
    complex_axis_r2: float
    amplitude_slope_per_capture: float
    relative_growth_over_run: float
    signed_amplitude_slope_per_capture: float
    signed_relative_change_over_run: float
    first_capture: int
    last_capture: int
    classification: str


@dataclass
class CaptureMetrics:
    capture_index: int
    residual_rms: float
    vector_roughness_rms: float
    spectral_flatness: float
    crest_factor: float
    peak_count: int


@dataclass
class RandomExtractResult:
    sample_rate_hz: float
    time_s: np.ndarray
    baseline: np.ndarray
    residuals: np.ndarray
    delta_y: np.ndarray
    frequencies_hz: np.ndarray
    complex_spectra: np.ndarray
    amplitude_spectra: np.ndarray
    observations: list[PeakObservation]
    tracks: list[FrequencyTrack]
    capture_metrics: list[CaptureMetrics]
    pointwise_residual_median: np.ndarray
    pointwise_residual_mad: np.ndarray
    pointwise_vector_median: np.ndarray
    pointwise_vector_mad: np.ndarray


def robust_mad(values: np.ndarray, axis=None) -> np.ndarray:
    """Median absolute deviation without Gaussian scaling."""
    med = np.median(values, axis=axis, keepdims=True)
    mad = np.median(np.abs(values - med), axis=axis)
    return mad


def _validate_inputs(
    captures: np.ndarray,
    sample_rate_hz: float,
    baseline: Optional[np.ndarray],
) -> tuple[np.ndarray, Optional[np.ndarray]]:
    captures = np.asarray(captures, dtype=float)

    if captures.ndim != 2:
        raise ValueError("captures must be a 2D array shaped (capture_count, sample_count)")
    if captures.shape[0] < 3:
        raise ValueError("at least 3 aligned captures are required")
    if captures.shape[1] < 16:
        raise ValueError("at least 16 samples per capture are required")
    if not np.isfinite(captures).all():
        raise ValueError("captures contain NaN or infinite values")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive and finite")

    if baseline is not None:
        baseline = np.asarray(baseline, dtype=float)
        if baseline.ndim != 1 or baseline.shape[0] != captures.shape[1]:
            raise ValueError("baseline must be 1D with the same sample count as captures")
        if not np.isfinite(baseline).all():
            raise ValueError("baseline contains NaN or infinite values")

    return captures, baseline


def build_wc2_baseline(captures: np.ndarray, method: str = "median") -> np.ndarray:
    """
    Build a simple robust collective waveform.

    In production, pass the actual WaveCompare 2 waveform through `baseline=...`.
    This fallback exists so the prototype can run independently.
    """
    if method == "median":
        return np.median(captures, axis=0)
    if method == "trimmed_mean":
        sorted_values = np.sort(captures, axis=0)
        trim = max(1, int(round(0.1 * captures.shape[0])))
        if 2 * trim >= captures.shape[0]:
            return np.mean(captures, axis=0)
        return np.mean(sorted_values[trim:-trim], axis=0)
    raise ValueError("baseline method must be 'median' or 'trimmed_mean'")


def _amplitude_spectrum(
    residuals: np.ndarray,
    sample_rate_hz: float,
    window_name: str,
    detrend: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return frequencies, complex one-sided spectra, and amplitude spectra."""
    x = residuals.copy()
    if detrend:
        x -= np.mean(x, axis=1, keepdims=True)

    window = get_window(window_name, x.shape[1], fftbins=True)
    coherent_gain = np.sum(window) / x.shape[1]
    if coherent_gain <= 0:
        raise ValueError("selected window has invalid coherent gain")

    spectrum = np.fft.rfft(x * window[None, :], axis=1)
    amplitude = np.abs(spectrum) * (2.0 / (x.shape[1] * coherent_gain))

    # DC and Nyquist do not receive the one-sided doubling.
    amplitude[:, 0] *= 0.5
    if x.shape[1] % 2 == 0:
        amplitude[:, -1] *= 0.5

    frequencies = np.fft.rfftfreq(x.shape[1], d=1.0 / sample_rate_hz)
    return frequencies, spectrum, amplitude


def _spectral_flatness(amplitude: np.ndarray) -> float:
    power = np.square(np.maximum(amplitude, _EPS))
    return float(np.exp(np.mean(np.log(power))) / np.mean(power))


def _detect_peaks_for_capture(
    capture_index: int,
    frequencies_hz: np.ndarray,
    amplitude: np.ndarray,
    complex_spectrum: np.ndarray,
    min_frequency_hz: float,
    max_frequency_hz: Optional[float],
    floor_kernel_bins: int,
    threshold_ratio: float,
    min_prominence_ratio: float,
    min_peak_spacing_hz: float,
) -> list[PeakObservation]:
    if floor_kernel_bins < 3:
        floor_kernel_bins = 3
    if floor_kernel_bins % 2 == 0:
        floor_kernel_bins += 1

    local_floor = median_filter(amplitude, size=floor_kernel_bins, mode="nearest")
    excess = amplitude - local_floor

    valid = frequencies_hz >= min_frequency_hz
    if max_frequency_hz is not None:
        valid &= frequencies_hz <= max_frequency_hz

    valid_indices = np.flatnonzero(valid)
    if valid_indices.size == 0:
        return []

    bin_width = frequencies_hz[1] - frequencies_hz[0]
    min_distance_bins = max(1, int(round(min_peak_spacing_hz / max(bin_width, _EPS))))

    # Dynamic prominence: based on the median local floor in the selected band.
    selected_floor = local_floor[valid]
    global_floor = float(np.median(selected_floor))
    min_prominence = max(global_floor * min_prominence_ratio, _EPS)

    peak_indices, properties = find_peaks(
        excess,
        distance=min_distance_bins,
        prominence=min_prominence,
    )

    observations: list[PeakObservation] = []
    for idx, prominence in zip(peak_indices, properties["prominences"]):
        if not valid[idx]:
            continue
        floor = float(local_floor[idx])
        amp = float(amplitude[idx])
        if amp < max(floor * threshold_ratio, _EPS):
            continue
        observations.append(
            PeakObservation(
                capture_index=capture_index,
                frequency_hz=float(frequencies_hz[idx]),
                amplitude=amp,
                phase_rad=float(np.angle(complex_spectrum[idx])),
                prominence=float(prominence),
                local_floor=floor,
            )
        )
    return observations


def _circular_coherence(phases: Iterable[float]) -> float:
    phase_array = np.asarray(list(phases), dtype=float)
    if phase_array.size == 0:
        return 0.0
    return float(np.abs(np.mean(np.exp(1j * phase_array))))


def _cluster_peak_observations(
    observations: list[PeakObservation],
    capture_count: int,
    frequencies_hz: np.ndarray,
    complex_spectra: np.ndarray,
    baseline_complex_spectrum: np.ndarray,
    tolerance_hz: float,
    phase_coherence_threshold: float,
    persistent_occupancy: float,
    intermittent_occupancy: float,
    growth_threshold: float,
) -> list[FrequencyTrack]:
    """
    Cluster observations by frequency using a robust centroid assignment.

    Each observation joins the closest existing cluster whose median frequency
    lies within tolerance_hz. Otherwise, it starts a new cluster.
    """
    if not observations:
        return []

    clusters: list[list[PeakObservation]] = []
    for obs in sorted(observations, key=lambda item: item.frequency_hz):
        best_cluster_index = None
        best_distance = float("inf")

        for cluster_index, cluster in enumerate(clusters):
            center = float(np.median([item.frequency_hz for item in cluster]))
            distance = abs(obs.frequency_hz - center)
            if distance <= tolerance_hz and distance < best_distance:
                best_cluster_index = cluster_index
                best_distance = distance

        if best_cluster_index is None:
            clusters.append([obs])
        else:
            clusters[best_cluster_index].append(obs)

    tracks: list[FrequencyTrack] = []
    for track_id, cluster in enumerate(clusters):
        # Keep at most the strongest observation from each capture in a track.
        strongest_by_capture: dict[int, PeakObservation] = {}
        for obs in cluster:
            current = strongest_by_capture.get(obs.capture_index)
            if current is None or obs.amplitude > current.amplitude:
                strongest_by_capture[obs.capture_index] = obs

        selected = sorted(strongest_by_capture.values(), key=lambda item: item.capture_index)
        capture_indices = np.asarray([item.capture_index for item in selected], dtype=float)
        frequencies = np.asarray([item.frequency_hz for item in selected], dtype=float)
        amplitudes = np.asarray([item.amplitude for item in selected], dtype=float)
        phases = np.asarray([item.phase_rad for item in selected], dtype=float)

        occupancy = len(selected) / capture_count
        center_frequency = float(np.median(frequencies))
        frequency_mad = float(robust_mad(frequencies))
        median_amplitude = float(np.median(amplitudes))
        amplitude_mad = float(robust_mad(amplitudes))
        phase_coherence = _circular_coherence(phases)
        axial_phase_coherence = float(np.abs(np.mean(np.exp(2j * phases)))) if phases.size else 0.0

        if len(selected) >= 3 and np.ptp(capture_indices) > 0:
            slope = float(theilslopes(amplitudes, capture_indices)[0])
            span = float(np.ptp(capture_indices))
            relative_growth = float((slope * span) / max(median_amplitude, _EPS))
        else:
            slope = 0.0
            relative_growth = 0.0

        # Examine the complete complex coefficient trajectory at the track's
        # center frequency, including captures where no peak crossed threshold.
        bin_index = int(np.argmin(np.abs(frequencies_hz - center_frequency)))
        z_all = complex_spectra[:, bin_index]
        z_center = (
            np.median(z_all.real)
            + 1j * np.median(z_all.imag)
        )
        centered = z_all - z_center
        points = np.column_stack([centered.real, centered.imag])

        if np.allclose(points, 0.0):
            complex_axis_r2 = 0.0
            principal_axis = 1.0 + 0.0j
        else:
            _, singular_values, vectors_t = np.linalg.svd(points, full_matrices=False)
            energy = float(np.sum(np.square(singular_values)))
            complex_axis_r2 = (
                float(np.square(singular_values[0]) / energy) if energy > 0 else 0.0
            )
            principal_axis = complex(vectors_t[0, 0], vectors_t[0, 1])

        baseline_z = baseline_complex_spectrum[bin_index]
        if abs(baseline_z) > _EPS:
            reference_axis = baseline_z / abs(baseline_z)
            # Align the PCA axis to the baseline component so signed change means
            # below/above the WC2 component rather than an arbitrary SVD sign.
            if np.real(principal_axis * np.conj(reference_axis)) < 0:
                principal_axis *= -1.0
        else:
            reference_axis = principal_axis

        signed_projection = np.real(z_all * np.conj(reference_axis))
        all_capture_indices = np.arange(capture_count, dtype=float)
        if capture_count >= 3:
            signed_slope = float(theilslopes(signed_projection, all_capture_indices)[0])
            signed_span = float(capture_count - 1)
            signed_scale = float(np.quantile(np.abs(signed_projection), 0.75))
            signed_relative_change = float(
                (signed_slope * signed_span) / max(signed_scale, _EPS)
            )
        else:
            signed_slope = 0.0
            signed_relative_change = 0.0

        if occupancy >= persistent_occupancy:
            if phase_coherence >= phase_coherence_threshold:
                classification = "persistent phase-coherent narrowband"
            elif (
                axial_phase_coherence >= phase_coherence_threshold
                and complex_axis_r2 >= 0.85
            ):
                classification = "persistent phase-axis narrowband"
            else:
                classification = "persistent asynchronous narrowband"
        elif occupancy >= intermittent_occupancy:
            classification = "intermittent narrowband"
        else:
            classification = "sparse peak cluster"

        trajectory_is_ordered = complex_axis_r2 >= 0.80
        if trajectory_is_ordered and signed_relative_change >= growth_threshold:
            classification += " with growth"
        elif trajectory_is_ordered and signed_relative_change <= -growth_threshold:
            classification += " with decay"

        tracks.append(
            FrequencyTrack(
                track_id=track_id,
                center_frequency_hz=center_frequency,
                occupancy=float(occupancy),
                capture_count=len(selected),
                observation_count=len(cluster),
                median_amplitude=median_amplitude,
                amplitude_mad=amplitude_mad,
                frequency_mad_hz=frequency_mad,
                phase_coherence=phase_coherence,
                axial_phase_coherence=axial_phase_coherence,
                complex_axis_r2=complex_axis_r2,
                amplitude_slope_per_capture=slope,
                relative_growth_over_run=relative_growth,
                signed_amplitude_slope_per_capture=signed_slope,
                signed_relative_change_over_run=signed_relative_change,
                first_capture=int(np.min(capture_indices)),
                last_capture=int(np.max(capture_indices)),
                classification=classification,
            )
        )

    return sorted(
        tracks,
        key=lambda track: (track.occupancy, track.median_amplitude),
        reverse=True,
    )


def analyze_random_extract(
    captures: np.ndarray,
    sample_rate_hz: float,
    *,
    baseline: Optional[np.ndarray] = None,
    baseline_method: str = "median",
    window_name: str = "hann",
    detrend: bool = True,
    min_frequency_hz: float = 1.0,
    max_frequency_hz: Optional[float] = None,
    floor_kernel_bins: int = 31,
    threshold_ratio: float = 4.0,
    min_prominence_ratio: float = 2.0,
    min_peak_spacing_hz: float = 1.0,
    track_tolerance_hz: Optional[float] = None,
    phase_coherence_threshold: float = 0.7,
    persistent_occupancy: float = 0.6,
    intermittent_occupancy: float = 0.2,
    growth_threshold: float = 0.35,
) -> RandomExtractResult:
    captures, baseline = _validate_inputs(captures, sample_rate_hz, baseline)

    if baseline is None:
        baseline = build_wc2_baseline(captures, method=baseline_method)

    residuals = captures - baseline[None, :]
    delta_y = np.diff(residuals, axis=1)
    time_s = np.arange(captures.shape[1], dtype=float) / sample_rate_hz

    frequencies_hz, complex_spectra, amplitude_spectra = _amplitude_spectrum(
        residuals,
        sample_rate_hz,
        window_name,
        detrend,
    )
    _, baseline_complex_matrix, _ = _amplitude_spectrum(
        baseline[None, :],
        sample_rate_hz,
        window_name,
        detrend,
    )
    baseline_complex_spectrum = baseline_complex_matrix[0]

    bin_width = frequencies_hz[1] - frequencies_hz[0]
    if track_tolerance_hz is None:
        track_tolerance_hz = max(2.0 * bin_width, min_peak_spacing_hz)

    observations: list[PeakObservation] = []
    capture_metrics: list[CaptureMetrics] = []

    for capture_index in range(captures.shape[0]):
        obs = _detect_peaks_for_capture(
            capture_index=capture_index,
            frequencies_hz=frequencies_hz,
            amplitude=amplitude_spectra[capture_index],
            complex_spectrum=complex_spectra[capture_index],
            min_frequency_hz=min_frequency_hz,
            max_frequency_hz=max_frequency_hz,
            floor_kernel_bins=floor_kernel_bins,
            threshold_ratio=threshold_ratio,
            min_prominence_ratio=min_prominence_ratio,
            min_peak_spacing_hz=min_peak_spacing_hz,
        )
        observations.extend(obs)

        residual = residuals[capture_index]
        residual_rms = float(np.sqrt(np.mean(np.square(residual))))
        roughness = float(np.sqrt(np.mean(np.square(delta_y[capture_index]))))
        crest = float(np.max(np.abs(residual)) / max(residual_rms, _EPS))
        flatness = _spectral_flatness(amplitude_spectra[capture_index, 1:])

        capture_metrics.append(
            CaptureMetrics(
                capture_index=capture_index,
                residual_rms=residual_rms,
                vector_roughness_rms=roughness,
                spectral_flatness=flatness,
                crest_factor=crest,
                peak_count=len(obs),
            )
        )

    tracks = _cluster_peak_observations(
        observations=observations,
        capture_count=captures.shape[0],
        frequencies_hz=frequencies_hz,
        complex_spectra=complex_spectra,
        baseline_complex_spectrum=baseline_complex_spectrum,
        tolerance_hz=track_tolerance_hz,
        phase_coherence_threshold=phase_coherence_threshold,
        persistent_occupancy=persistent_occupancy,
        intermittent_occupancy=intermittent_occupancy,
        growth_threshold=growth_threshold,
    )

    return RandomExtractResult(
        sample_rate_hz=float(sample_rate_hz),
        time_s=time_s,
        baseline=baseline,
        residuals=residuals,
        delta_y=delta_y,
        frequencies_hz=frequencies_hz,
        complex_spectra=complex_spectra,
        amplitude_spectra=amplitude_spectra,
        observations=observations,
        tracks=tracks,
        capture_metrics=capture_metrics,
        pointwise_residual_median=np.median(residuals, axis=0),
        pointwise_residual_mad=robust_mad(residuals, axis=0),
        pointwise_vector_median=np.median(delta_y, axis=0),
        pointwise_vector_mad=robust_mad(delta_y, axis=0),
    )


def export_result(result: RandomExtractResult, output_dir: Path) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame([asdict(track) for track in result.tracks]).to_csv(
        output_dir / "frequency_tracks.csv", index=False
    )
    pd.DataFrame([asdict(metric) for metric in result.capture_metrics]).to_csv(
        output_dir / "capture_metrics.csv", index=False
    )
    pd.DataFrame([asdict(obs) for obs in result.observations]).to_csv(
        output_dir / "peak_observations.csv", index=False
    )

    pointwise = pd.DataFrame(
        {
            "time_s": result.time_s,
            "residual_median": result.pointwise_residual_median,
            "residual_mad": result.pointwise_residual_mad,
        }
    )
    pointwise.to_csv(output_dir / "pointwise_residual_geometry.csv", index=False)

    vector_time_s = result.time_s[:-1] + 0.5 / result.sample_rate_hz
    vector_df = pd.DataFrame(
        {
            "time_s": vector_time_s,
            "vector_median_delta_y": result.pointwise_vector_median,
            "vector_mad_delta_y": result.pointwise_vector_mad,
        }
    )
    vector_df.to_csv(output_dir / "pointwise_vector_geometry.csv", index=False)

    np.savez_compressed(
        output_dir / "random_extract_arrays.npz",
        sample_rate_hz=result.sample_rate_hz,
        time_s=result.time_s,
        baseline=result.baseline,
        residuals=result.residuals,
        delta_y=result.delta_y,
        frequencies_hz=result.frequencies_hz,
        complex_spectra=result.complex_spectra,
        amplitude_spectra=result.amplitude_spectra,
    )

    summary = {
        "sample_rate_hz": result.sample_rate_hz,
        "capture_count": int(result.residuals.shape[0]),
        "sample_count": int(result.residuals.shape[1]),
        "track_count": len(result.tracks),
        "tracks": [asdict(track) for track in result.tracks],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Chart 1: residual frequency matrix, capture index vs frequency.
    plt.figure(figsize=(11, 6))
    positive = np.maximum(result.amplitude_spectra, _EPS)
    db = 20.0 * np.log10(positive)
    plt.imshow(
        db,
        aspect="auto",
        origin="lower",
        extent=[
            result.frequencies_hz[0],
            result.frequencies_hz[-1],
            0,
            result.residuals.shape[0] - 1,
        ],
    )
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Capture index")
    plt.title("RandomExtract residual FFT magnitude by capture")
    plt.colorbar(label="Amplitude (dB, relative)")
    plt.tight_layout()
    plt.savefig(output_dir / "capture_frequency_matrix.png", dpi=180)
    plt.close()

    # Chart 2: residual overlay.
    plt.figure(figsize=(11, 6))
    for residual in result.residuals:
        plt.plot(result.time_s, residual, alpha=0.35)
    plt.xlabel("Time (s)")
    plt.ylabel("Residual amplitude")
    plt.title("WaveCompare 2 removed from each aligned capture")
    plt.tight_layout()
    plt.savefig(output_dir / "residual_overlay.png", dpi=180)
    plt.close()

    # Chart 3: pointwise residual and vector spread.
    plt.figure(figsize=(11, 6))
    plt.plot(result.time_s, result.pointwise_residual_mad, label="Residual MAD")
    plt.plot(vector_time_s, result.pointwise_vector_mad, label="Vector delta MAD")
    plt.xlabel("Time (s)")
    plt.ylabel("Robust spread")
    plt.title("RandomExtract pointwise residual geometry")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "pointwise_geometry.png", dpi=180)
    plt.close()


def load_capture_csv(path: Path) -> tuple[np.ndarray, np.ndarray, float]:
    frame = pd.read_csv(path)
    if frame.shape[1] < 4:
        raise ValueError(
            "CSV must contain a time column and at least three aligned capture columns"
        )

    time_s = frame.iloc[:, 0].to_numpy(dtype=float)
    captures = frame.iloc[:, 1:].to_numpy(dtype=float).T

    dt = np.diff(time_s)
    if np.any(dt <= 0):
        raise ValueError("time column must be strictly increasing")
    median_dt = float(np.median(dt))
    if np.max(np.abs(dt - median_dt)) > max(1e-9, 1e-3 * median_dt):
        raise ValueError("time samples must be uniformly spaced")

    sample_rate_hz = 1.0 / median_dt
    return time_s, captures, sample_rate_hz


def generate_demo(
    capture_count: int = 48,
    sample_rate_hz: float = 4096.0,
    duration_s: float = 1.0,
    seed: int = 7,
) -> tuple[np.ndarray, np.ndarray, float]:
    rng = np.random.default_rng(seed)
    sample_count = int(round(sample_rate_hz * duration_s))
    t = np.arange(sample_count) / sample_rate_hz

    # Repeatable WaveCompare-like machine response.
    base = (
        2.2 * (t >= 0.12)
        - 0.8 * (t >= 0.48)
        + 0.5 * np.exp(-18.0 * np.maximum(t - 0.12, 0.0)) * (t >= 0.12)
        + 0.18 * np.exp(-25.0 * np.maximum(t - 0.48, 0.0))
        * np.sin(2.0 * np.pi * 95.0 * np.maximum(t - 0.48, 0.0))
        * (t >= 0.48)
    )

    captures = []
    for k in range(capture_count):
        random_phase_60 = rng.uniform(-np.pi, np.pi)
        asynchronous_60 = 0.07 * np.sin(2.0 * np.pi * 60.0 * t + random_phase_60)

        growth = 0.015 + 0.12 * (k / max(capture_count - 1, 1))
        growing_310 = growth * np.sin(2.0 * np.pi * 310.0 * t + 0.3)

        white = rng.normal(0.0, 0.018, size=sample_count)

        impulse = np.zeros_like(t)
        if k in {9, 10, 27, 41}:
            center = int(round((0.70 + rng.normal(0.0, 0.0015)) * sample_rate_hz))
            width = 4
            start = max(0, center - width)
            stop = min(sample_count, center + width + 1)
            impulse[start:stop] += np.hanning(stop - start) * rng.uniform(0.18, 0.32)

        captures.append(base + asynchronous_60 + growing_310 + white + impulse)

    return t, np.asarray(captures), sample_rate_hz


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the RandomExtract prototype")
    parser.add_argument("--input-csv", type=Path, help="Time column + aligned capture columns")
    parser.add_argument("--baseline-csv", type=Path, help="Optional one-column WC2 waveform")
    parser.add_argument("--output-dir", type=Path, default=Path("random_extract_output"))
    parser.add_argument("--demo", action="store_true", help="Run the included synthetic test")
    parser.add_argument("--min-frequency-hz", type=float, default=1.0)
    parser.add_argument("--max-frequency-hz", type=float)
    parser.add_argument("--threshold-ratio", type=float, default=4.0)
    parser.add_argument("--track-tolerance-hz", type=float)
    return parser


def main() -> None:
    args = _build_parser().parse_args()

    if args.demo:
        time_s, captures, sample_rate_hz = generate_demo()
        baseline = None
    elif args.input_csv:
        time_s, captures, sample_rate_hz = load_capture_csv(args.input_csv)
        baseline = None
        if args.baseline_csv:
            baseline_frame = pd.read_csv(args.baseline_csv)
            baseline = baseline_frame.iloc[:, -1].to_numpy(dtype=float)
    else:
        raise SystemExit("Use --demo or provide --input-csv")

    result = analyze_random_extract(
        captures,
        sample_rate_hz,
        baseline=baseline,
        min_frequency_hz=args.min_frequency_hz,
        max_frequency_hz=args.max_frequency_hz,
        threshold_ratio=args.threshold_ratio,
        track_tolerance_hz=args.track_tolerance_hz,
    )
    export_result(result, args.output_dir)

    print(f"RandomExtract complete: {len(result.tracks)} frequency tracks")
    for track in result.tracks[:10]:
        print(
            f"{track.center_frequency_hz:9.3f} Hz | "
            f"occupancy={track.occupancy:5.1%} | "
            f"phase_coherence={track.phase_coherence:5.3f} | "
            f"axis_r2={track.complex_axis_r2:5.3f} | "
            f"signed_change={track.signed_relative_change_over_run:+6.2f} | "
            f"{track.classification}"
        )
    print(f"Outputs written to: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
