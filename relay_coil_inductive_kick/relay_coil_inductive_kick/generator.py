from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Literal, Optional, Tuple

import numpy as np


SourceMode = Literal["current", "voltage"]


@dataclass(frozen=True)
class InductiveCaseMetadata:
    """Ground-truth metadata for one synthetic inductive kick case."""

    label: str
    sample_rate_hz: float
    duration_s: float
    source_mode: SourceMode
    event_time_s: float
    tau_s: float
    coupling_k: float
    lag_s: float
    polarity: int
    noise_rms: float
    ring_frequency_hz: float
    ring_alpha_per_s: float
    ring_amplitude: float
    has_ringdown: bool


def _central_diff(y: np.ndarray, dt: float) -> np.ndarray:
    out = np.empty_like(y, dtype=float)
    out[1:-1] = (y[2:] - y[:-2]) / (2.0 * dt)
    out[0] = (y[1] - y[0]) / dt
    out[-1] = (y[-1] - y[-2]) / dt
    return out


def _shift_by_seconds(x: np.ndarray, lag_s: float, sample_rate_hz: float) -> np.ndarray:
    """Fractional shift using interpolation. Positive lag delays x."""
    n = len(x)
    t = np.arange(n) / sample_rate_hz
    return np.interp(t - lag_s, t, x, left=0.0, right=0.0)


def generate_inductive_case(
    *,
    seed: Optional[int] = None,
    sample_rate_hz: float = 250_000.0,
    duration_s: float = 0.020,
    source_mode: SourceMode = "current",
    ringdown_probability: float = 0.75,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, InductiveCaseMetadata]:
    """Generate one two-channel relay-coil inductive kick case.

    Returns:
        time_s, source_ch, victim_ch, metadata

    Source channel meanings:
        source_mode="current": source_ch is coil current proxy, so classifier uses dI/dt.
        source_mode="voltage": source_ch is coil voltage proxy, so classifier fits victim ~= k*source.

    The generator intentionally creates only Class A true inductive cases.
    Negative classes belong to their own seeds and should be invoked by the
    boundary harness rather than being duplicated here.
    """
    rng = np.random.default_rng(seed)
    n = int(round(sample_rate_hz * duration_s))
    dt = 1.0 / sample_rate_hz
    t = np.arange(n, dtype=float) * dt

    event_time_s = float(rng.uniform(0.004, 0.011))
    tau_s = float(10 ** rng.uniform(np.log10(60e-6), np.log10(900e-6)))
    i0 = float(rng.uniform(0.08, 1.5))
    coupling_k = float(rng.uniform(8e-5, 9e-4))
    polarity = int(rng.choice([-1, 1]))
    lag_s = float(rng.uniform(-25e-6, 65e-6))
    noise_rms = float(10 ** rng.uniform(np.log10(0.0010), np.log10(0.015)))

    u = (t >= event_time_s).astype(float)
    decay = np.exp(-(t - event_time_s) / tau_s) * u

    # Current before event is near I0; after event decays.
    current = i0 * (1.0 - u) + i0 * decay
    current += rng.normal(0.0, noise_rms * 0.05, size=n)

    di_dt = _central_diff(current, dt)
    di_dt_feature = _shift_by_seconds(di_dt, lag_s, sample_rate_hz)

    has_ringdown = bool(rng.random() < ringdown_probability)
    ring_frequency_hz = float(rng.uniform(3_000.0, 75_000.0))
    ring_alpha_per_s = float(rng.uniform(4_000.0, 45_000.0))
    ring_amplitude = float(rng.uniform(0.005, 0.08) if has_ringdown else 0.0)
    phi = float(rng.uniform(-np.pi, np.pi))

    tail_t = np.maximum(t - (event_time_s + max(lag_s, 0.0)), 0.0)
    ring = (
        ring_amplitude
        * np.exp(-ring_alpha_per_s * tail_t)
        * np.cos(2.0 * np.pi * ring_frequency_hz * tail_t + phi)
        * (tail_t > 0.0)
    )

    victim = polarity * coupling_k * di_dt_feature + ring
    victim += rng.normal(0.0, noise_rms, size=n)

    if source_mode == "current":
        source = current
    elif source_mode == "voltage":
        # Coil voltage proxy is proportional to dI/dt plus measurement noise.
        source = polarity * di_dt + rng.normal(0.0, max(np.std(di_dt) * 0.01, 1e-9), size=n)
        source = source / (np.percentile(np.abs(source), 99) + 1e-12)
    else:
        raise ValueError(f"unsupported source_mode={source_mode!r}")

    meta = InductiveCaseMetadata(
        label="relay_coil_inductive_kick",
        sample_rate_hz=float(sample_rate_hz),
        duration_s=float(duration_s),
        source_mode=source_mode,
        event_time_s=event_time_s,
        tau_s=tau_s,
        coupling_k=coupling_k,
        lag_s=lag_s,
        polarity=polarity,
        noise_rms=noise_rms,
        ring_frequency_hz=ring_frequency_hz,
        ring_alpha_per_s=ring_alpha_per_s,
        ring_amplitude=ring_amplitude,
        has_ringdown=has_ringdown,
    )
    return t, source.astype(float), victim.astype(float), meta


def generate_inductive_cases(
    n: int,
    *,
    seed: int = 5466,
    sample_rate_hz: float = 250_000.0,
    duration_s: float = 0.020,
    source_mode: SourceMode = "current",
) -> List[Tuple[np.ndarray, np.ndarray, np.ndarray, InductiveCaseMetadata]]:
    """Generate a reproducible list of Class A inductive cases."""
    rng = np.random.default_rng(seed)
    cases = []
    for _ in range(n):
        case_seed = int(rng.integers(0, 2**31 - 1))
        cases.append(
            generate_inductive_case(
                seed=case_seed,
                sample_rate_hz=sample_rate_hz,
                duration_s=duration_s,
                source_mode=source_mode,
            )
        )
    return cases


def metadata_to_dict(meta: InductiveCaseMetadata) -> Dict[str, object]:
    return asdict(meta)
