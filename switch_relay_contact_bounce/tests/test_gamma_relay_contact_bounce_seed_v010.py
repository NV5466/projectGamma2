from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import numpy as np
import pytest

from gamma_relay_contact_bounce_seed_v010 import (
    RelayBounceConfig,
    RelayCaptureContext,
    RelayMeasurementMetadata,
    _synthetic_case,
    analyze_relay_contact_bounce,
)


FAMILIES = (
    "ac_clean_close",
    "dc_clean_close",
    "ac_bounce_close",
    "dc_bounce_close",
    "ac_bounce_open",
    "ac_transient_only",
    "ac_failed",
    "ac_uncertain_multiple_commands",
    "ac_near_zero_bounce",
)


def metadata(sample_rate_hz=200_000.0):
    return RelayMeasurementMetadata(
        contact_channel_name="CH2",
        contact_channel_units="V",
        source_reference_channel_name="CH1",
        command_channel_name="CH3",
        scope_model="GW Instek GDS-3504",
        scope_bandwidth_hz=500e6,
        sample_rate_hz=sample_rate_hz,
    )


def analyze_families(
    families,
    seed=1,
    *,
    sample_rate_hz=200_000.0,
    line_frequency_hz=60.0,
):
    rng = np.random.default_rng(seed)
    contacts = []
    sources = []
    commands = []
    contexts = []
    expected = []
    time_s = None
    for family in families:
        time_s, contact, source, command, context, expected_class = _synthetic_case(
            rng,
            family,
            sample_rate_hz=sample_rate_hz,
            line_frequency_hz=line_frequency_hz,
        )
        contacts.append(contact)
        sources.append(source if source is not None else np.ones_like(contact))
        commands.append(command)
        contexts.append(context)
        expected.append(expected_class)
    result = analyze_relay_contact_bounce(
        time_s,
        np.vstack(contacts),
        contexts,
        metadata(sample_rate_hz),
        source_reference_captures=np.vstack(sources),
        command_captures=np.vstack(commands),
        config=RelayBounceConfig(),
    )
    return result, expected


def analyze_one(
    family,
    seed,
    *,
    sample_rate_hz,
    line_frequency_hz,
):
    rng = np.random.default_rng(seed)
    time_s, contact, source, command, context, expected = _synthetic_case(
        rng,
        family,
        sample_rate_hz=sample_rate_hz,
        line_frequency_hz=line_frequency_hz,
    )
    source = source if source is not None else np.ones_like(contact)
    result = analyze_relay_contact_bounce(
        time_s,
        contact[None, :],
        [context],
        metadata(sample_rate_hz),
        source_reference_captures=source[None, :],
        command_captures=command[None, :],
        config=RelayBounceConfig(),
    )
    return result, expected


# 108 separately reported pytest cases:
# 9 behavior families x 12 randomized acquisition conditions.
CLASSIFICATION_CASES = []
_SAMPLE_RATES = (100_000.0, 200_000.0, 500_000.0)
_LINE_FREQUENCIES = (50.0, 60.0)
for repetition in range(12):
    for family_index, family in enumerate(FAMILIES):
        sample_rate = _SAMPLE_RATES[(repetition + family_index) % len(_SAMPLE_RATES)]
        line_frequency = _LINE_FREQUENCIES[(repetition + family_index) % len(_LINE_FREQUENCIES)]
        seed = 10_000 + repetition * 101 + family_index * 17
        CLASSIFICATION_CASES.append(
            pytest.param(
                family,
                seed,
                sample_rate,
                line_frequency,
                id=(
                    f"{family}-r{repetition:02d}-"
                    f"{int(sample_rate/1000)}k-{int(line_frequency)}Hz"
                ),
            )
        )


@pytest.mark.parametrize(
    "family,seed,sample_rate_hz,line_frequency_hz",
    CLASSIFICATION_CASES,
)
def test_108_randomized_classification_cases(
    family,
    seed,
    sample_rate_hz,
    line_frequency_hz,
):
    result, expected = analyze_one(
        family,
        seed,
        sample_rate_hz=sample_rate_hz,
        line_frequency_hz=line_frequency_hz,
    )
    row = result.capture_classification.iloc[0]
    assert row["capture_class"] == expected
    assert result.snr_evaluated is False
    assert result.confidence_status == "final_confidence_unavailable_snr_deferred"


def test_ac_and_dc_bounce_are_detected():
    result, expected = analyze_families(
        ["ac_bounce_close", "dc_bounce_close", "ac_bounce_open"]
    )
    assert result.capture_classification["capture_class"].tolist() == expected
    bounce = result.bounce_features
    assert np.all(bounce["extra_edge_count"].to_numpy() >= 2)
    assert np.all(bounce["bounce_duration_s"].to_numpy() > 0)


def test_clean_transition_reference_excludes_transient_and_failed():
    result, expected = analyze_families(
        ["ac_clean_close", "dc_clean_close", "ac_transient_only", "ac_failed"],
        seed=2,
    )
    assert result.capture_classification["capture_class"].tolist() == expected
    assert result.diagnostics["clean_reference_capture_indices"] == [0, 1]
    assert result.capture_classification["reference_eligible"].tolist() == [
        True,
        True,
        False,
        False,
    ]


def test_window_features_use_median_and_mad_not_signed_average():
    result, _ = analyze_families(["ac_bounce_close"], seed=3)
    columns = set(result.window_features.columns)
    assert "median_abs_state_derivative_per_s" in columns
    assert "mad_abs_state_derivative_per_s" in columns
    assert "derivative_activity_window" in columns
    assert "mean_signed_derivative" not in columns


def test_multiple_commands_are_not_mislabeled_as_bounce():
    result, expected = analyze_families(["ac_uncertain_multiple_commands"], seed=4)
    assert result.capture_classification["capture_class"].tolist() == expected
    assert result.capture_classification.iloc[0]["classification_reason"].startswith(
        "multiple_command_edges"
    )


def test_near_zero_crossing_reports_observability_without_crashing():
    result, expected = analyze_families(["ac_near_zero_bounce"], seed=5)
    assert result.capture_classification["capture_class"].tolist() == expected
    row = result.bounce_features.iloc[0]
    assert row["edge_timing_low_observability_count"] >= 0
    assert bool(row["edge_count_is_observability_limited"])
    assert row["pre_first_contact_unobservable_gap_s"] > 0
    assert 0 <= row["final_state_observable_fraction"] <= 1


def test_clean_does_not_mean_globally_healthy():
    result, _ = analyze_families(["ac_clean_close"], seed=6)
    assert result.status == "no_relay_contact_bounce_population_available"
    assert "not proof of whole-system health" in result.notes[1]
    assert result.snr_evaluated is False
