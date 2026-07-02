from __future__ import annotations

from .schema import SignatureResult


def rank_signature_results(results: list[SignatureResult]) -> list[SignatureResult]:
    return sorted(
        results,
        key=lambda r: (
            not r.matched,
            -float(r.confidence),
            -len(r.evidence),
            len(r.rejections),
            len(r.errors),
            r.signature_id,
        ),
    )
