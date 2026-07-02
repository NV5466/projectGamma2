from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Literal, Tuple

import numpy as np


SourceMode = Literal["current", "voltage"]


@dataclass(frozen=True)
class InductiveFeatures:
    source_event_count: int
    fit_gain_k: float
    fit_r2: float
    wc2_score: float
    lag_s: float
    lag_us: float
    source_peak_z: float
    victim_peak_z: float
    polarity: int
    ring_frequency_hz: float
    ring_decay_alpha_per_s: float
    ring_q_estimate: float
    ring_score: float
    residual_rms: float
    source_feature_rms: float
    victim_rms: float


def _rms(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    return float(np.sqrt(np.mean(x * x) + 1e-18))


def _robust_z_peak(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med))) + 1e-12
    return float(np.max(np.abs(x - med)) / (1.4826 * mad))


def central_diff(y: np.ndarray, dt: float) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    out = np.empty_like(y)
    out[1:-1] = (y[2:] - y[:-2]) / (2.0 * dt)
    out[0] = (y[1] - y[0]) / dt
    out[-1] = (y[-1] - y[-2]) / dt
    return out


def _event_window_indices(
    feature: np.ndarray,
    sample_rate_hz: float,
    *,
    pre_s: float = 350e-6,
    post_s: float = 2_500e-6,
) -> Tuple[int, int, int]:
    idx = int(np.argmax(np.abs(feature - np.median(feature))))
    pre = int(round(pre_s * sample_rate_hz))
    post = int(round(post_s * sample_rate_hz))
    start = max(0, idx - pre)
    stop = min(len(feature), idx + post)
    return idx, start, stop


def _count_source_events(feature: np.ndarray, sample_rate_hz: float) -> int:
    """Count dominant source edge impulses.

    This is intentionally simple and inspectable. It is not a bounce classifier.
    It only rejects cases where this seed sees many strong source impulses.
    """
    x = np.abs(feature - np.median(feature))
    if len(x) < 5:
        return 0

    threshold = np.median(x) + 8.0 * (1.4826 * np.median(np.abs(x - np.median(x))) + 1e-12)
    threshold = max(threshold, 0.35 * float(np.max(x)))
    above = x > threshold

    # Merge impulses separated by less than 75 us.
    min_gap = max(1, int(round(75e-6 * sample_rate_hz)))
    events = 0
    last = -10**9
    for i, val in enumerate(above):
        if val and i - last > min_gap:
            events += 1
            last = i
        elif val:
            last = i
    return int(events)


def _best_lag_fit(
    x: np.ndarray,
    y: np.ndarray,
    sample_rate_hz: float,
    *,
    max_lag_s: float = 150e-6,
) -> Tuple[float, float, float, float]:
    """Fit y ~= k*x after searching small lags.

    Returns:
        best_k, best_r2, best_lag_s, wc2_score
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    x = x - np.mean(x)
    y = y - np.mean(y)

    max_lag = int(round(max_lag_s * sample_rate_hz))
    if max_lag < 1:
        max_lag = 1

    best_k = 0.0
    best_r2 = -np.inf
    best_lag = 0
    best_wc2 = 0.0
    best_score = -np.inf

    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            xs = x[-lag:]
            ys = y[: len(xs)]
        elif lag > 0:
            xs = x[: -lag]
            ys = y[lag:]
        else:
            xs = x
            ys = y

        denom = float(np.dot(xs, xs)) + 1e-18
        k = float(np.dot(xs, ys) / denom)
        pred = k * xs
        sse = float(np.sum((ys - pred) ** 2))
        sst = float(np.sum((ys - np.mean(ys)) ** 2)) + 1e-18
        r2 = 1.0 - sse / sst

        corr_num = float(np.dot(xs, ys))
        corr_den = float(np.sqrt(np.dot(xs, xs) * np.dot(ys, ys)) + 1e-18)
        corr = corr_num / corr_den
        wc2 = corr * corr

        score = r2 + 0.25 * wc2
        if score > best_score:
            best_score = score
            best_k = k
            best_r2 = r2
            best_lag = lag
            best_wc2 = wc2

    return (
        float(best_k),
        float(max(-1.0, min(1.0, best_r2))),
        float(best_lag / sample_rate_hz),
        float(best_wc2),
    )


def _ringdown_estimate(y: np.ndarray, sample_rate_hz: float) -> Tuple[float, float, float, float]:
    """Estimate ring frequency/decay/Q from the post-event tail.

    This is intentionally lightweight, NumPy-only, and used as secondary evidence.
    """
    y = np.asarray(y, dtype=float)
    if len(y) < 32 or _rms(y) <= 1e-12:
        return 0.0, 0.0, 0.0, 0.0

    tail = y - np.mean(y)
    window = np.hanning(len(tail))
    spec = np.abs(np.fft.rfft(tail * window))
    freqs = np.fft.rfftfreq(len(tail), d=1.0 / sample_rate_hz)

    if len(spec) < 3:
        return 0.0, 0.0, 0.0, 0.0

    valid = freqs > 500.0
    if not np.any(valid):
        return 0.0, 0.0, 0.0, 0.0

    idx_valid = np.where(valid)[0]
    peak_idx = int(idx_valid[np.argmax(spec[idx_valid])])
    ring_freq = float(freqs[peak_idx])
    spectral_score = float(spec[peak_idx] / (np.sum(spec[idx_valid]) + 1e-18))

    chunks = np.array_split(np.abs(tail), 4)
    env = np.array([_rms(c) for c in chunks], dtype=float) + 1e-12
    times = np.array([(i + 0.5) * len(tail) / 4.0 / sample_rate_hz for i in range(4)])
    slope, _intercept = np.polyfit(times, np.log(env), 1)
    alpha = float(max(0.0, -slope))
    omega = 2.0 * np.pi * ring_freq
    q = float(omega / (2.0 * alpha)) if alpha > 1e-9 else 0.0

    ring_score = float(np.clip(4.0 * spectral_score, 0.0, 1.0))
    return ring_freq, alpha, q, ring_score


def extract_features(
    time_s: np.ndarray,
    source: np.ndarray,
    victim: np.ndarray,
    *,
    source_mode: SourceMode = "current",
    max_lag_s: float = 150e-6,
) -> InductiveFeatures:
    """Extract relay-coil inductive kick features from two synced waveforms."""
    time_s = np.asarray(time_s, dtype=float)
    source = np.asarray(source, dtype=float)
    victim = np.asarray(victim, dtype=float)

    if len(time_s) != len(source) or len(source) != len(victim):
        raise ValueError("time_s, source, and victim must have the same length")
    if len(time_s) < 16:
        raise ValueError("waveform is too short")

    dt = float(np.median(np.diff(time_s)))
    if dt <= 0:
        raise ValueError("time_s must be strictly increasing")
    fs = 1.0 / dt

    if source_mode == "current":
        source_feature = central_diff(source, dt)
    elif source_mode == "voltage":
        source_feature = source.copy()
    else:
        raise ValueError(f"unsupported source_mode={source_mode!r}")

    event_idx, start, stop = _event_window_indices(source_feature, fs)
    xw = source_feature[start:stop]
    yw = victim[start:stop]

    k, r2, lag_s, wc2 = _best_lag_fit(xw, yw, fs, max_lag_s=max_lag_s)

    # Align roughly for residual RMS only; exact diagnostic uses best-fit scores above.
    residual = yw - k * (xw - np.mean(xw))

    ring_start = min(len(victim), event_idx + int(round(150e-6 * fs)))
    ring_stop = min(len(victim), event_idx + int(round(4_000e-6 * fs)))
    ring_freq, ring_alpha, ring_q, ring_score = _ringdown_estimate(victim[ring_start:ring_stop], fs)

    polarity = int(np.sign(k)) if abs(k) > 1e-18 else 0

    return InductiveFeatures(
        source_event_count=_count_source_events(source_feature, fs),
        fit_gain_k=float(k),
        fit_r2=float(r2),
        wc2_score=float(wc2),
        lag_s=float(lag_s),
        lag_us=float(lag_s * 1e6),
        source_peak_z=_robust_z_peak(source_feature),
        victim_peak_z=_robust_z_peak(victim),
        polarity=polarity,
        ring_frequency_hz=float(ring_freq),
        ring_decay_alpha_per_s=float(ring_alpha),
        ring_q_estimate=float(ring_q),
        ring_score=float(ring_score),
        residual_rms=_rms(residual),
        source_feature_rms=_rms(xw),
        victim_rms=_rms(yw),
    )


def features_to_dict(features: InductiveFeatures) -> Dict[str, float]:
    return asdict(features)
