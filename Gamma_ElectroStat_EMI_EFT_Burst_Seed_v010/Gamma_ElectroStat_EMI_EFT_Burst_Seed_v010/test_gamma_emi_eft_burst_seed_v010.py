
import numpy as np

from gamma_emi_eft_burst_seed_v010 import (
    EFTAcquisitionMetadata,
    EFTConfig,
    _synthetic_detail_set,
    _synthetic_overview,
    analyze_emi_eft_burst,
    assess_acquisition,
)


def metadata():
    return EFTAcquisitionMetadata(
        scope_model="GW Instek GDS-3504",
        probe_model="synthetic",
        analog_bandwidth_hz=500e6,
        probe_bandwidth_hz=500e6,
        vertical_min_v=-2.0,
        vertical_max_v=2.0,
        acquisition_mode="real_time",
    )


def test_gds3504_observability_is_strong_at_4_gsa():
    t = np.arange(1040) / 4e9
    captures = np.zeros((2, t.size))
    assessment = assess_acquisition(t, captures, metadata())
    assert np.isclose(assessment.samples_across_nominal_rise, 20.0)
    assert assessment.observability_status == "strongly_supported"


def test_snr_is_explicitly_deferred():
    rng = np.random.default_rng(1)
    t, detail = _synthetic_detail_set(rng, ring_frequency_hz=120e6)
    ot, overview = _synthetic_overview(rng, repetition_hz=100e3)
    result = analyze_emi_eft_burst(
        t, detail, metadata(),
        overview_time_s=ot,
        overview_waveform_v=overview,
    )
    assert result.snr_evaluated is False
    assert "snr_deferred" in result.confidence_status


def test_nominal_burst_is_supported():
    rng = np.random.default_rng(2)
    t, detail = _synthetic_detail_set(rng, ring_frequency_hz=120e6)
    ot, overview = _synthetic_overview(rng, repetition_hz=100e3)
    result = analyze_emi_eft_burst(
        t, detail, metadata(),
        overview_time_s=ot,
        overview_waveform_v=overview,
    )
    assert result.status == "eft_like_burst_supported"
    assert len(result.pulse_features) >= 3
    assert bool(result.train_summary["expected_repetition_match"].iloc[0])


def test_no_event_is_not_invented():
    rng = np.random.default_rng(3)
    t, detail = _synthetic_detail_set(rng, no_event=True, ring_frequency_hz=None)
    result = analyze_emi_eft_burst(t, detail, metadata())
    assert result.status == "no_fast_transient_detected"
    assert result.pulse_features.empty


def test_broad_step_is_not_called_eft_like():
    rng = np.random.default_rng(4)
    t, detail = _synthetic_detail_set(rng, broad_step=True, ring_frequency_hz=None)
    ot, overview = _synthetic_overview(rng, repetition_hz=100e3)
    result = analyze_emi_eft_burst(
        t, detail, metadata(),
        overview_time_s=ot,
        overview_waveform_v=overview,
    )
    assert result.status == "no_fast_transient_detected"


def test_template_preserves_measured_peak_scale():
    rng = np.random.default_rng(5)
    t, detail = _synthetic_detail_set(rng, ring_frequency_hz=120e6)
    result = analyze_emi_eft_burst(t, detail, metadata())
    median_feature_peak = float(result.pulse_features["peak_abs_v"].median())
    template_peak = float(np.max(np.abs(result.pulse_template_v)))
    relative_difference = abs(template_peak - median_feature_peak) / median_feature_peak
    assert relative_difference < 0.08
