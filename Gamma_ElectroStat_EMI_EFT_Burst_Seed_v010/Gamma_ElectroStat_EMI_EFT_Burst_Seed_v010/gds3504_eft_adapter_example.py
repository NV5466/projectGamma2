
"""Minimal Gamma / WaveCompare-facing adapter for the EMI EFT burst seed."""

from __future__ import annotations

import numpy as np

from gamma_emi_eft_burst_seed_v010 import (
    EFTAcquisitionMetadata,
    EFTConfig,
    analyze_emi_eft_burst,
)


def analyze_gds3504_eft(
    detail_time_s: np.ndarray,
    detail_captures_v: np.ndarray,
    *,
    overview_time_s: np.ndarray | None = None,
    overview_waveform_v: np.ndarray | None = None,
):
    """Analyze real-time GDS-3504 captures without calculating SNR.

    ``detail_captures_v`` may be:
        - repeated triggered captures of one pulse, or
        - pulse-local windows exported from segmented acquisition.

    ``overview_waveform_v`` is optional and is used only for pulse-train and
    burst timing. It may have a lower sample rate than the detail captures.
    """
    metadata = EFTAcquisitionMetadata(
        scope_model="GW Instek GDS-3504",
        probe_model="ENTER_ACTUAL_PROBE_MODEL",
        analog_bandwidth_hz=500e6,
        probe_bandwidth_hz=None,  # Enter the actual probe bandwidth.
        bandwidth_limit_hz=None,  # Enter enabled scope limit, if any.
        adc_bits=8,
        vertical_min_v=None,      # Enter export/acquisition rails when known.
        vertical_max_v=None,
        input_impedance_ohm=1e6, # Change to 50 ohm if used.
        coupling="DC",
        acquisition_mode="real_time",
        averaging_count=1,
        notes=("Replace placeholder probe and vertical-range metadata.",),
    )

    result = analyze_emi_eft_burst(
        detail_time_s,
        detail_captures_v,
        metadata,
        overview_time_s=overview_time_s,
        overview_waveform_v=overview_waveform_v,
        config=EFTConfig(),
    )
    return result
