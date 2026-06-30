"""
Reference integration contract for the PWM/VFD damping head.

The classifier remains unchanged. This file contains the final decision
contract that sits after the three physical damping estimators.
"""

from dataclasses import dataclass
from math import pi, sqrt
from typing import Optional


@dataclass
class DampingEstimate:
    candidate_alpha_per_s: float
    dominant_frequency_hz: float
    candidate_damping_ratio: float
    candidate_quality_factor: float
    accepted_alpha_per_s: Optional[float]
    accepted_damping_ratio: Optional[float]
    accepted_quality_factor: Optional[float]
    lower_bound_per_s: Optional[float]
    upper_bound_per_s: Optional[float]
    status: str


def derive_damping_quantities(alpha_per_s: float, frequency_hz: float):
    omega_d = 2.0 * pi * frequency_hz
    omega_n = sqrt(omega_d * omega_d + alpha_per_s * alpha_per_s)
    zeta = alpha_per_s / omega_n
    quality_factor = omega_n / (2.0 * alpha_per_s)
    return zeta, quality_factor


def accept_stationary_single_mode(
    base_high_confidence: bool,
    event_frequency_mad_fraction: float,
    event_shift_mad_samples: float,
    secondary_peak_ratio: float,
) -> bool:
    return (
        base_high_confidence
        and event_frequency_mad_fraction <= 0.010
        and event_shift_mad_samples <= 0.5
        and secondary_peak_ratio <= 0.10
    )


def finalize_damping(
    candidate_alpha_per_s: float,
    dominant_frequency_hz: float,
    base_high_confidence: bool,
    event_frequency_mad_fraction: float,
    event_shift_mad_samples: float,
    secondary_peak_ratio: float,
) -> DampingEstimate:
    zeta, q = derive_damping_quantities(
        candidate_alpha_per_s,
        dominant_frequency_hz,
    )

    accepted = accept_stationary_single_mode(
        base_high_confidence,
        event_frequency_mad_fraction,
        event_shift_mad_samples,
        secondary_peak_ratio,
    )

    if not accepted:
        return DampingEstimate(
            candidate_alpha_per_s=candidate_alpha_per_s,
            dominant_frequency_hz=dominant_frequency_hz,
            candidate_damping_ratio=zeta,
            candidate_quality_factor=q,
            accepted_alpha_per_s=None,
            accepted_damping_ratio=None,
            accepted_quality_factor=None,
            lower_bound_per_s=None,
            upper_bound_per_s=None,
            status="candidate_only_nonstationary",
        )

    return DampingEstimate(
        candidate_alpha_per_s=candidate_alpha_per_s,
        dominant_frequency_hz=dominant_frequency_hz,
        candidate_damping_ratio=zeta,
        candidate_quality_factor=q,
        accepted_alpha_per_s=candidate_alpha_per_s,
        accepted_damping_ratio=zeta,
        accepted_quality_factor=q,
        lower_bound_per_s=0.50 * candidate_alpha_per_s,
        upper_bound_per_s=1.50 * candidate_alpha_per_s,
        status="accepted_stationary_single_mode",
    )
