from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

from .models import AnalysisResult, Capture


def write_plots(capture: Capture, results: list[AnalysisResult], output_dir: Path) -> None:
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    for result in results:
        channel = next(ch for ch in capture.channels if ch.channel_id == result.channel_id)
        safe_name = _safe_filename(channel.channel_id)

        waveform_path = plots_dir / f"{safe_name}_waveform.png"
        _plot_waveform(channel.time_s, channel.values, channel.channel_id, waveform_path)
        result.artifacts["waveform"] = waveform_path

        if capture.sample_rate_hz and capture.sample_rate_hz > 0 and len(channel.values) >= 16:
            psd_path = plots_dir / f"{safe_name}_psd.png"
            _plot_psd(channel.values, capture.sample_rate_hz, channel.channel_id, psd_path)
            result.artifacts["psd"] = psd_path


def _plot_waveform(time_s: np.ndarray, values: np.ndarray, title: str, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(time_s, values, linewidth=0.8)
    ax.set_title(f"{title} waveform")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Value")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _plot_psd(values: np.ndarray, sample_rate_hz: float, title: str, path: Path) -> None:
    clean = values[np.isfinite(values)]
    detrended = signal.detrend(clean)
    freqs, psd = signal.welch(detrended, fs=sample_rate_hz, nperseg=min(2048, len(detrended)))

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.semilogy(freqs, psd)
    ax.set_title(f"{title} PSD")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Power spectral density")
    ax.grid(True, which="both", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)
