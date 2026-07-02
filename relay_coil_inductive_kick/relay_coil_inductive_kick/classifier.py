from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Literal

import numpy as np

from .features import InductiveFeatures, extract_features, features_to_dict


SourceMode = Literal["current", "voltage"]


@dataclass(frozen=True)
class InductiveKickDecision:
    label: str
    is_relay_coil_inductive_kick: bool
    confidence: float
    reason: str
    features: Dict[str, float]


def _clip01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


def score_features(
    f: InductiveFeatures,
    *,
    source_event_count_max: int = 3,
    fit_r2_min: float = 0.55,
    abs_lag_us_max: float = 150.0,
    wc2_min: float = 0.45,
) -> tuple[float, list[str], list[str]]:
    """Return confidence, positive reasons, rejection reasons."""
    positives: list[str] = []
    rejects: list[str] = []

    if f.source_event_count <= source_event_count_max:
        source_event_score = 1.0
        positives.append("single/few dominant source event(s)")
    else:
        source_event_score = 0.0
        rejects.append(f"source_event_count={f.source_event_count} exceeds {source_event_count_max}")

    fit_score = _clip01((f.fit_r2 - 0.15) / (0.85 - 0.15))
    if f.fit_r2 >= fit_r2_min:
        positives.append(f"unknown-gain source fit passed R2={f.fit_r2:.3f}")
    else:
        rejects.append(f"fit R2={f.fit_r2:.3f} below {fit_r2_min:.3f}")

    lag_score = _clip01(1.0 - abs(f.lag_us) / max(abs_lag_us_max, 1e-9))
    if abs(f.lag_us) <= abs_lag_us_max:
        positives.append(f"source/victim lag {f.lag_us:.1f} us within window")
    else:
        rejects.append(f"lag {f.lag_us:.1f} us outside +/-{abs_lag_us_max:.1f} us")

    wc2_score = _clip01((f.wc2_score - 0.10) / (0.90 - 0.10))
    if f.wc2_score >= wc2_min:
        positives.append(f"WC2/correlation support {f.wc2_score:.3f}")
    else:
        rejects.append(f"WC2/correlation {f.wc2_score:.3f} below {wc2_min:.3f}")

    peak_score = _clip01(min(f.source_peak_z, f.victim_peak_z) / 20.0)
    if f.source_peak_z > 3.0 and f.victim_peak_z > 3.0:
        positives.append("source and victim both have strong transient peaks")
    else:
        rejects.append(
            f"weak transient evidence source_z={f.source_peak_z:.2f}, victim_z={f.victim_peak_z:.2f}"
        )

    ring_score = _clip01(f.ring_score)
    if ring_score > 0.25:
        positives.append("ringdown tail supports kick but is not primary evidence")

    confidence = (
        0.28 * fit_score
        + 0.22 * wc2_score
        + 0.20 * lag_score
        + 0.18 * source_event_score
        + 0.07 * peak_score
        + 0.05 * ring_score
    )

    hard_pass = (
        f.source_event_count <= source_event_count_max
        and f.fit_r2 >= fit_r2_min
        and abs(f.lag_us) <= abs_lag_us_max
        and f.wc2_score >= wc2_min
        and f.source_peak_z > 3.0
        and f.victim_peak_z > 3.0
    )

    # Hard failures cap confidence so ringing cannot rescue a non-causal transient.
    if not hard_pass:
        confidence = min(confidence, 0.69)

    return float(confidence), positives, rejects


def classify_inductive_kick(
    time_s: np.ndarray,
    source: np.ndarray,
    victim: np.ndarray,
    *,
    source_mode: SourceMode = "current",
    confidence_min: float = 0.70,
    source_event_count_max: int = 3,
    fit_r2_min: float = 0.55,
    abs_lag_us_max: float = 150.0,
    wc2_min: float = 0.45,
) -> InductiveKickDecision:
    """Classify whether a two-channel event is relay-coil inductive kickback.

    The class is defined by one source-locked coil-current-collapse event explaining
    the victim transient through unknown-gain dI/dt or coil-voltage coupling.
    Damped ringing is secondary support only.
    """
    f = extract_features(
        time_s,
        source,
        victim,
        source_mode=source_mode,
        max_lag_s=abs_lag_us_max * 1e-6,
    )
    confidence, positives, rejects = score_features(
        f,
        source_event_count_max=source_event_count_max,
        fit_r2_min=fit_r2_min,
        abs_lag_us_max=abs_lag_us_max,
        wc2_min=wc2_min,
    )
    is_positive = confidence >= confidence_min and len(rejects) == 0

    if is_positive:
        reason = "positive: " + "; ".join(positives)
    else:
        reason = "reject: " + "; ".join(rejects[:4])

    return InductiveKickDecision(
        label="relay_coil_inductive_kick" if is_positive else "not_relay_coil_inductive_kick",
        is_relay_coil_inductive_kick=bool(is_positive),
        confidence=float(confidence),
        reason=reason,
        features=features_to_dict(f),
    )


def decision_to_dict(decision: InductiveKickDecision) -> Dict[str, object]:
    return asdict(decision)
