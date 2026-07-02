from __future__ import annotations

from dataclasses import dataclass, field

from .ranking import rank_signature_results
from .registry import SignatureSpec
from .schema import CaptureRecord, SignatureResult


@dataclass
class CaseRunResult:
    capture_id: str
    truth_label: str | None
    results: list[SignatureResult]
    winner: str | None
    decision: str
    ranked_signature_ids: list[str] = field(default_factory=list)


def run_capture(capture: CaptureRecord, signatures: list[SignatureSpec]) -> CaseRunResult:
    capture.validate()
    results: list[SignatureResult] = []
    for spec in signatures:
        try:
            result = spec.analyze(capture)
            result.validate()
        except Exception as exc:
            result = SignatureResult(
                signature_id=spec.seed_id,
                matched=False,
                confidence=0.0,
                best_reference=None,
                reference_results=[],
                evidence=[],
                rejections=["signature_runtime_error"],
                errors=[repr(exc)],
            )
        results.append(result)

    ranked = rank_signature_results(results)
    winner = ranked[0].signature_id if ranked and ranked[0].matched else None
    decision = "matched" if winner else "no_match"
    return CaseRunResult(
        capture_id=capture.capture_id or "capture",
        truth_label=capture.truth_label,
        results=ranked,
        winner=winner,
        decision=decision,
        ranked_signature_ids=[r.signature_id for r in ranked],
    )


def run_campaign(captures: list[CaptureRecord], signatures: list[SignatureSpec]) -> list[CaseRunResult]:
    return [run_capture(capture, signatures) for capture in captures]
