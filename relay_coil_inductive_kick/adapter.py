from __future__ import annotations

from gamma_core.schema import CaptureRecord, ReferenceResult, SignatureResult

from .relay_coil_inductive_kick.classifier import classify_inductive_kick

SIGNATURE_ID = "relay_coil_inductive_kick"


def _classify_reference(capture: CaptureRecord, label: str, waveform, mode: str) -> ReferenceResult:
    decision = classify_inductive_kick(
        capture.time_s,
        waveform,
        capture.primary,
        source_mode=mode,
    )
    features = dict(decision.features)
    model = "primary ~= k * d(reference)/dt" if mode == "current" else "primary ~= k * reference"
    return ReferenceResult(
        reference_label=label,
        matched=bool(decision.is_relay_coil_inductive_kick),
        confidence=float(decision.confidence),
        relationship={
            "type": "unknown_gain_derivative_fit" if mode == "current" else "unknown_gain_voltage_fit",
            "model": model,
            "source_mode": mode,
            "lag_us": features.get("lag_us"),
            "fit_r2": features.get("fit_r2"),
            "gain_k": features.get("fit_gain_k"),
        },
        features=features,
        evidence=[decision.reason] if decision.is_relay_coil_inductive_kick else [],
        rejections=[] if decision.is_relay_coil_inductive_kick else [decision.reason],
    )


def analyze(capture: CaptureRecord) -> SignatureResult:
    capture.validate()
    reference_modes = dict(capture.metadata.get("reference_modes", {}))
    reference_results: list[ReferenceResult] = []

    for label, waveform in capture.references.items():
        configured_mode = reference_modes.get(label)
        modes = [configured_mode] if configured_mode in {"current", "voltage"} else ["voltage", "current"]
        candidates = [_classify_reference(capture, label, waveform, mode) for mode in modes]
        reference_results.append(
            sorted(
                candidates,
                key=lambda r: (
                    not r.matched,
                    -float(r.confidence),
                    -len(r.evidence),
                    len(r.rejections),
                    r.relationship.get("source_mode", ""),
                ),
            )[0]
        )

    best = sorted(
        reference_results,
        key=lambda r: (
            not r.matched,
            -float(r.confidence),
            -len(r.evidence),
            len(r.rejections),
            r.reference_label,
        ),
    )[0]
    result = SignatureResult(
        signature_id=SIGNATURE_ID,
        matched=bool(best.matched),
        confidence=float(best.confidence),
        best_reference=best.reference_label,
        reference_results=reference_results,
        relationship={**best.relationship, "best_reference": best.reference_label},
        features=best.features,
        evidence=[f"best_reference={best.reference_label}", *best.evidence],
        rejections=best.rejections,
    )
    result.validate()
    return result
