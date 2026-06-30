"""Minimal GDS-3504 + oscilloscope current-probe adapter example."""

from __future__ import annotations
import numpy as np
from gamma_current_inrush_seed_v010 import (
    CaptureContext, CurrentProbeMetadata, InrushConfig,
    analyze_current_inrush,
)


def analyze_gds3504_current_inrush(
    time_s: np.ndarray,
    captures_a: np.ndarray,
    capture_ids: list[str],
    *,
    transition_marker_time_s: float,
):
    contexts = [
        CaptureContext(
            capture_id=capture_id,
            transition_expected=True,
            transition_validated=True,
            transition_completed=True,
            event_marker_time_s=transition_marker_time_s,
            operating_state="ENTER_OPERATING_STATE",
            load_state="ENTER_LOAD_STATE",
            phase_or_conductor_id="ENTER_PHASE_OR_CONDUCTOR",
        )
        for capture_id in capture_ids
    ]
    probe = CurrentProbeMetadata(
        probe_model="ENTER_PROBE_MODEL",
        amperes_per_volt=1.0,
        bandwidth_hz=None,
        current_limit_a=None,
        ac_dc_capable=True,
        phase_or_conductor_id="ENTER_PHASE_OR_CONDUCTOR",
        scope_model="GW Instek GDS-3504",
        scope_bandwidth_hz=500e6,
        acquisition_mode="real_time",
    )
    config = InrushConfig(
        line_frequency_hz=60.0,
        # For inverter-fed current, set line_frequency_hz=None and provide
        # envelope_window_s explicitly.
    )
    return analyze_current_inrush(time_s, captures_a, contexts, probe, config)
