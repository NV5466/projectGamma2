"""Minimal GDS-3504 adapter example for relay/contact bounce."""

from __future__ import annotations

import numpy as np

from gamma_relay_contact_bounce_seed_v010 import (
    RelayBounceConfig,
    RelayCaptureContext,
    RelayMeasurementMetadata,
    analyze_relay_contact_bounce,
)


def analyze_gds3504_relay_captures(
    time_s: np.ndarray,
    source_voltage_captures: np.ndarray,
    contact_or_load_captures: np.ndarray,
    command_captures: np.ndarray,
    capture_ids: list[str],
):
    contexts = [
        RelayCaptureContext(
            capture_id=capture_id,
            signal_type="ac",
            measurement_topology="load_side_voltage",
            commanded_final_state="closed",
            initial_state="open",
            transition_expected=True,
            transition_validated=True,
            transition_completed=True,
            line_frequency_hz=60.0,
            operating_state="ENTER_OPERATING_STATE",
            relay_or_contactor_id="ENTER_RELAY_ID",
        )
        for capture_id in capture_ids
    ]

    metadata = RelayMeasurementMetadata(
        contact_channel_name="CH2 contact/load voltage",
        contact_channel_units="V",
        source_reference_channel_name="CH1 source voltage",
        command_channel_name="CH3 command or coil voltage",
        scope_model="GW Instek GDS-3504",
        scope_bandwidth_hz=500e6,
        sample_rate_hz=1.0 / float(np.median(np.diff(time_s))),
        probe_bandwidth_hz=None,
    )

    return analyze_relay_contact_bounce(
        time_s,
        contact_or_load_captures,
        contexts,
        metadata,
        source_reference_captures=source_voltage_captures,
        command_captures=command_captures,
        config=RelayBounceConfig(
            derivative_window_s=0.00025,
        ),
    )
