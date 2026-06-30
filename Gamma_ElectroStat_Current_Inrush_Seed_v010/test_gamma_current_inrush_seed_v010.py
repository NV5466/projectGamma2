import numpy as np
from gamma_current_inrush_seed_v010 import (
    CaptureContext, CurrentProbeMetadata, InrushConfig,
    _synthetic_case, analyze_current_inrush,
)


def probe():
    return CurrentProbeMetadata(
        probe_model="synthetic", amperes_per_volt=1.0,
        bandwidth_hz=100e3, current_limit_a=500.0,
        scope_model="GW Instek GDS-3504", scope_bandwidth_hz=500e6,
    )


def test_population_classification_and_reference():
    rng = np.random.default_rng(1)
    families = ["monotonic", "oscillatory", "no_inrush", "no_inrush", "failed"]
    raw, contexts, expected = [], [], []
    t = None
    for family in families:
        t, x, context, cls = _synthetic_case(rng, family)
        raw.append(x); contexts.append(context); expected.append(cls)
    result = analyze_current_inrush(t, np.vstack(raw), contexts, probe(), InrushConfig(line_frequency_hz=60.0))
    assert result.snr_evaluated is False
    assert list(result.capture_classification["capture_class"]) == expected
    assert result.no_inrush_reference_envelope_a.size == t.size
    assert len(result.inrush_features) == 2


def test_no_inrush_does_not_mean_global_health():
    rng = np.random.default_rng(2)
    t, x, context, cls = _synthetic_case(rng, "no_inrush")
    result = analyze_current_inrush(t, x, [context], probe(), InrushConfig(line_frequency_hz=60.0))
    assert cls == "no_inrush"
    assert result.status == "no_current_inrush_population_available"
    assert "not that the entire capture was healthy" in result.notes[1]


def test_failed_transition_stays_out_of_reference():
    rng = np.random.default_rng(3)
    t, x1, c1, _ = _synthetic_case(rng, "failed")
    _, x2, c2, _ = _synthetic_case(rng, "no_inrush")
    _, x3, c3, _ = _synthetic_case(rng, "no_inrush")
    result = analyze_current_inrush(t, np.vstack([x1, x2, x3]), [c1, c2, c3], probe(), InrushConfig(line_frequency_hz=60.0))
    assert result.capture_classification["capture_class"].tolist() == ["failed_transition", "no_inrush", "no_inrush"]
    assert result.diagnostics["no_inrush_reference_capture_indices"] == [1, 2]


def test_inrush_is_measured_twice():
    rng = np.random.default_rng(4)
    t, x1, c1, _ = _synthetic_case(rng, "monotonic")
    _, x2, c2, _ = _synthetic_case(rng, "no_inrush")
    _, x3, c3, _ = _synthetic_case(rng, "no_inrush")
    result = analyze_current_inrush(t, np.vstack([x1, x2, x3]), [c1, c2, c3], probe(), InrushConfig(line_frequency_hz=60.0))
    row = result.inrush_features.iloc[0]
    assert row["peak_to_post_ratio"] > 1.35
    assert row["recovery_reference_source"] == "validated_no_inrush_population"
    assert np.isfinite(row["post_event_relative_difference_from_reference"])
