import numpy as np
import pytest

from gamma_core.schema import CaptureRecord, ReferenceResult, SignatureResult


def test_valid_secondary_legacy_passes():
    capture = CaptureRecord(sample_rate_hz=1000.0, primary=np.zeros(16), secondary=np.ones(16))
    capture.validate()
    assert "secondary" in capture.references


def test_valid_references_passes():
    capture = CaptureRecord(
        sample_rate_hz=1000.0,
        primary=np.zeros(16),
        references={"a": np.ones(16), "b": np.arange(16)},
    )
    capture.validate()
    assert set(capture.references) == {"a", "b"}


def test_missing_references_fails():
    with pytest.raises(ValueError):
        CaptureRecord(sample_rate_hz=1000.0, primary=np.zeros(16)).validate()


def test_bad_reference_length_fails():
    with pytest.raises(ValueError):
        CaptureRecord(sample_rate_hz=1000.0, primary=np.zeros(16), references={"a": np.zeros(15)}).validate()


def test_bad_sample_rate_fails():
    with pytest.raises(ValueError):
        CaptureRecord(sample_rate_hz=0.0, primary=np.zeros(16), secondary=np.ones(16)).validate()


def test_time_length_mismatch_fails():
    with pytest.raises(ValueError):
        CaptureRecord(sample_rate_hz=1000.0, primary=np.zeros(16), secondary=np.ones(16), time_s=np.zeros(15)).validate()


def test_signature_result_confidence_fails():
    with pytest.raises(ValueError):
        SignatureResult("x", True, 1.5).validate()


def test_reference_result_confidence_fails():
    with pytest.raises(ValueError):
        ReferenceResult("ref", True, -0.1).validate()
