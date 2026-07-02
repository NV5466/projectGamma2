from dataclasses import dataclass

import numpy as np

from gamma_core.registry import SignatureSpec
from gamma_core.runner import run_capture
from gamma_core.schema import CaptureRecord, ReferenceResult, SignatureResult


@dataclass
class FakeSpec:
    seed_id: str
    confidence: float
    best_reference: str

    def analyze(self, _capture):
        return SignatureResult(
            signature_id=self.seed_id,
            matched=True,
            confidence=self.confidence,
            best_reference=self.best_reference,
            reference_results=[ReferenceResult(self.best_reference, True, self.confidence)],
            evidence=["fake"],
        )


def test_winner_is_highest_confidence():
    capture = CaptureRecord(sample_rate_hz=1000.0, primary=np.zeros(1000), references={"ref_a": np.zeros(1000)})
    signatures = [
        FakeSpec("low", 0.4, "ref_b"),
        FakeSpec("high", 0.8, "ref_a"),
    ]
    result = run_capture(capture, signatures)  # type: ignore[arg-type]
    assert result.winner == "high"
    assert result.ranked_signature_ids == ["high", "low"]
