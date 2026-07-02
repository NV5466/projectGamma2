import numpy as np

from gamma_core.registry import load_registry
from gamma_core.schema import CaptureRecord, SignatureResult


def test_implemented_signatures_return_valid_results():
    specs, failures = load_registry(".", include_status={"implemented", "implemented_synthetic", "validated"})
    target_ids = {"relay_coil_inductive_kick", "high_speed_input_bounce", "missed_short_pulse"}
    specs = [spec for spec in specs if spec.seed_id in target_ids]
    assert {spec.seed_id for spec in specs} == target_ids

    primary = np.zeros(1000)
    primary[500] = 1.0
    refs = {
        "ref_a": np.zeros(1000),
        "ref_b": np.zeros(1000),
        "ref_c": np.zeros(1000),
    }
    refs["ref_a"][500] = 1.0
    capture = CaptureRecord(sample_rate_hz=100_000.0, primary=primary, references=refs)

    for spec in specs:
        result = spec.analyze(capture)
        result.validate()
        assert isinstance(result, SignatureResult)
        assert result.signature_id == spec.seed_id
        assert result.reference_results
