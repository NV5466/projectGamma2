
#!/usr/bin/env python3
"""
Controlled validation of the RandomExtract + multi-spectral common-mode classifier.

The synthetic paired captures contain:
- 60 Hz same-polarity proportional common-mode disturbance
- 180 Hz opposite-polarity differential disturbance
- 310 Hz channel-1-local disturbance
- independent broadband noise

The known repeatable waveform is supplied exactly as the WC2 baseline so this
test isolates the multi-spectral classifier from baseline-estimation error.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import argparse
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import find_peaks, get_window


@dataclass
class ClassificationRow:
    frequency_hz: float
    mean_amplitude_ch1: float
    mean_amplitude_ch2: float
    median_gain_ch2_over_ch1: float
    gain_relative_mad: float
    coherence: float
    phase_difference_deg: float
    occupancy_ch1: float
    occupancy_ch2: float
    classification: str


def classify_pair(
    ch1: np.ndarray,
    ch2: np.ndarray,
    wc2_1: np.ndarray,
    wc2_2: np.ndarray,
    sample_rate_hz: float,
    max_frequency_hz: float = 800.0,
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    if ch1.shape != ch2.shape:
        raise ValueError("channel capture matrices must have identical shape")
    if ch1.ndim != 2:
        raise ValueError("channels must be shaped (capture_count, sample_count)")
    if wc2_1.shape != (ch1.shape[1],) or wc2_2.shape != (ch2.shape[1],):
        raise ValueError("WC2 waveforms must match the sample count")

    r1 = ch1 - wc2_1[None, :]
    r2 = ch2 - wc2_2[None, :]

    n = ch1.shape[1]
    window = get_window("hann", n, fftbins=True)
    coherent_gain = np.sum(window) / n

    R1 = np.fft.rfft(
        (r1 - np.mean(r1, axis=1, keepdims=True)) * window[None, :],
        axis=1,
    )
    R2 = np.fft.rfft(
        (r2 - np.mean(r2, axis=1, keepdims=True)) * window[None, :],
        axis=1,
    )
    frequency_hz = np.fft.rfftfreq(n, d=1.0 / sample_rate_hz)

    A1 = np.abs(R1) * 2.0 / (n * coherent_gain)
    A2 = np.abs(R2) * 2.0 / (n * coherent_gain)
    A1[:, 0] *= 0.5
    A2[:, 0] *= 0.5
    if n % 2 == 0:
        A1[:, -1] *= 0.5
        A2[:, -1] *= 0.5

    S11 = np.mean(np.abs(R1) ** 2, axis=0)
    S22 = np.mean(np.abs(R2) ** 2, axis=0)
    S12 = np.mean(np.conj(R1) * R2, axis=0)

    coherence = np.abs(S12) ** 2 / np.maximum(
        S11 * S22,
        np.finfo(float).eps,
    )
    phase_difference_deg = np.rad2deg(np.angle(S12))

    mean_a1 = np.mean(A1, axis=0)
    mean_a2 = np.mean(A2, axis=0)
    combined = np.maximum(mean_a1, mean_a2)

    band = (frequency_hz >= 5.0) & (frequency_hz <= max_frequency_hz)
    band_indices = np.flatnonzero(band)
    noise_floor = float(np.median(combined[band]))

    local_peaks, _ = find_peaks(
        combined[band],
        height=12.0 * noise_floor,
        prominence=8.0 * noise_floor,
        distance=max(1, int(round(8.0 / (frequency_hz[1] - frequency_hz[0])))),
    )
    candidate_indices = band_indices[local_peaks]

    floor1 = np.median(A1[:, band], axis=1)
    floor2 = np.median(A2[:, band], axis=1)

    rows: list[ClassificationRow] = []

    for index in candidate_indices:
        occupancy1 = float(np.mean(A1[:, index] > 8.0 * floor1))
        occupancy2 = float(np.mean(A2[:, index] > 8.0 * floor2))

        valid = A1[:, index] > 8.0 * floor1
        ratios = A2[valid, index] / np.maximum(
            A1[valid, index],
            np.finfo(float).eps,
        )
        if ratios.size:
            gain = float(np.median(ratios))
            gain_relative_mad = float(
                np.median(np.abs(ratios - gain))
                / max(gain, np.finfo(float).eps)
            )
        else:
            gain = float("nan")
            gain_relative_mad = float("nan")

        coh = float(coherence[index])
        phase = float(phase_difference_deg[index])
        absolute_wrapped_phase = abs(((phase + 180.0) % 360.0) - 180.0)

        if (
            coh >= 0.85
            and absolute_wrapped_phase <= 20.0
            and occupancy1 >= 0.5
            and occupancy2 >= 0.5
        ):
            label = "common-mode"
        elif (
            coh >= 0.85
            and abs(absolute_wrapped_phase - 180.0) <= 20.0
            and occupancy1 >= 0.5
            and occupancy2 >= 0.5
        ):
            label = "differential / opposite-polarity"
        elif occupancy1 >= 0.5 and occupancy2 < 0.25:
            label = "channel 1 local"
        elif occupancy2 >= 0.5 and occupancy1 < 0.25:
            label = "channel 2 local"
        elif coh >= 0.85:
            label = "shared, non-common phase relation"
        else:
            label = "unclassified residual"

        rows.append(
            ClassificationRow(
                frequency_hz=float(frequency_hz[index]),
                mean_amplitude_ch1=float(mean_a1[index]),
                mean_amplitude_ch2=float(mean_a2[index]),
                median_gain_ch2_over_ch1=gain,
                gain_relative_mad=gain_relative_mad,
                coherence=coh,
                phase_difference_deg=phase,
                occupancy_ch1=occupancy1,
                occupancy_ch2=occupancy2,
                classification=label,
            )
        )

    frame = pd.DataFrame([asdict(row) for row in rows]).sort_values("frequency_hz")
    arrays = {
        "residual_ch1": r1,
        "residual_ch2": r2,
        "frequency_hz": frequency_hz,
        "complex_fft_ch1": R1,
        "complex_fft_ch2": R2,
        "amplitude_ch1": A1,
        "amplitude_ch2": A2,
        "mean_amplitude_ch1": mean_a1,
        "mean_amplitude_ch2": mean_a2,
        "coherence": coherence,
        "phase_difference_deg": phase_difference_deg,
    }
    return frame, arrays


def make_demo(
    capture_count: int = 64,
    sample_rate_hz: float = 4096.0,
    duration_s: float = 1.0,
    seed: int = 20260626,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = int(round(sample_rate_hz * duration_s))
    t = np.arange(n) / sample_rate_hz

    base1 = (
        1.6 * (t >= 0.10)
        - 0.55 * (t >= 0.52)
        + 0.20 * np.exp(-22 * np.maximum(t - 0.10, 0)) * (t >= 0.10)
    )
    base2 = (
        1.1 * (t >= 0.10)
        - 0.38 * (t >= 0.52)
        + 0.12 * np.exp(-20 * np.maximum(t - 0.10, 0)) * (t >= 0.10)
    )

    ch1 = np.empty((capture_count, n))
    ch2 = np.empty((capture_count, n))

    for k in range(capture_count):
        phi60 = rng.uniform(-np.pi, np.pi)
        amp60 = 0.075 * (1.0 + rng.normal(0, 0.06))
        common1 = amp60 * np.sin(2 * np.pi * 60.0 * t + phi60)
        common2 = (
            0.72
            * amp60
            * (1.0 + rng.normal(0, 0.025))
            * np.sin(
                2 * np.pi * 60.0 * t
                + phi60
                + rng.normal(0, np.deg2rad(2.0))
            )
        )

        phi180 = rng.uniform(-np.pi, np.pi)
        amp180 = 0.050 * (1.0 + rng.normal(0, 0.05))
        diff1 = amp180 * np.sin(2 * np.pi * 180.0 * t + phi180)
        diff2 = (
            0.90
            * amp180
            * np.sin(
                2 * np.pi * 180.0 * t
                + phi180
                + np.pi
                + rng.normal(0, np.deg2rad(2.0))
            )
        )

        phi310 = rng.uniform(-np.pi, np.pi)
        local1 = 0.060 * np.sin(2 * np.pi * 310.0 * t + phi310)

        ch1[k] = base1 + common1 + diff1 + local1 + rng.normal(0, 0.014, n)
        ch2[k] = base2 + common2 + diff2 + rng.normal(0, 0.014, n)

    return t, ch1, ch2, base1, base2


def export(
    frame: pd.DataFrame,
    arrays: dict[str, np.ndarray],
    time_s: np.ndarray,
    sample_rate_hz: float,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_dir / "common_mode_classification.csv", index=False)

    np.savez_compressed(
        output_dir / "common_mode_test_arrays.npz",
        time_s=time_s,
        sample_rate_hz=sample_rate_hz,
        **arrays,
    )

    frequency_hz = arrays["frequency_hz"]

    plt.figure(figsize=(11, 6))
    plt.plot(frequency_hz, arrays["mean_amplitude_ch1"], label="Channel 1")
    plt.plot(frequency_hz, arrays["mean_amplitude_ch2"], label="Channel 2")
    plt.xlim(0, 800)
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Mean residual FFT amplitude")
    plt.title("Residual spectra after WC2 removal")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "mean_residual_spectra.png", dpi=180)
    plt.close()

    plt.figure(figsize=(11, 6))
    plt.plot(frequency_hz, arrays["coherence"])
    plt.xlim(0, 800)
    plt.ylim(0, 1.05)
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Magnitude-squared coherence")
    plt.title("Cross-capture multi-spectral coherence")
    plt.tight_layout()
    plt.savefig(output_dir / "multispectral_coherence.png", dpi=180)
    plt.close()

    plt.figure(figsize=(11, 6))
    plt.plot(frequency_hz, arrays["phase_difference_deg"])
    plt.xlim(0, 800)
    plt.ylim(-190, 190)
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Channel 2 minus channel 1 phase (degrees)")
    plt.title("Cross-spectrum phase difference")
    plt.tight_layout()
    plt.savefig(output_dir / "cross_spectrum_phase.png", dpi=180)
    plt.close()

    summary = {
        "known_injections": {
            "60 Hz": "same-polarity proportional common-mode",
            "180 Hz": "opposite-polarity differential",
            "310 Hz": "channel 1 local",
        },
        "results": frame.to_dict(orient="records"),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("common_mode_multispectral_output"),
    )
    args = parser.parse_args()

    sample_rate_hz = 4096.0
    t, ch1, ch2, wc2_1, wc2_2 = make_demo(sample_rate_hz=sample_rate_hz)
    frame, arrays = classify_pair(
        ch1,
        ch2,
        wc2_1,
        wc2_2,
        sample_rate_hz,
    )
    export(frame, arrays, t, sample_rate_hz, args.output_dir)
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
