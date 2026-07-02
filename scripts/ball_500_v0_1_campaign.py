from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import csv
import json
import platform
import shutil
import subprocess
import sys
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gamma_core.evidence import write_evidence_outputs
from gamma_core.registry import load_registry
from gamma_core.runner import CaseRunResult, run_campaign
from gamma_core.schema import CaptureRecord
from relay_coil_inductive_kick.relay_coil_inductive_kick.generator import generate_inductive_case


OUT_DIR = Path("validation/campaigns/ball_500_v0_1")
RANDOM_SEED = 546601
CASE_COUNT = 500
SIGNATURE_IDS = [
    "relay_coil_inductive_kick",
    "high_speed_input_bounce",
    "missed_short_pulse",
]
VARIANTS = [
    "clean",
    "noisy",
    "amplitude_shifted",
    "timing_shifted",
    "degraded_reference",
    "near_miss_ambiguous",
]


def _git_value(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _provenance() -> dict[str, Any]:
    commit = _git_value(["rev-parse", "HEAD"])
    return {
        "campaign_id": "ball_500_v0_1",
        "producing_branch": _git_value(["branch", "--show-current"]),
        "producing_commit": commit,
        "intended_base_branch": "Gammav0.1",
        "intended_base_commit": "ee8b1f8",
        "source_main_commit": "068deea",
        "campaign_harness_commit": commit,
        "random_seed": RANDOM_SEED,
        "python_version": sys.version.replace("\n", " "),
        "platform": platform.platform(),
        "command": "python scripts/ball_500_v0_1_campaign.py",
        "cwd": str(Path.cwd()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _shift(x: np.ndarray, samples: int) -> np.ndarray:
    if samples == 0:
        return x.copy()
    out = np.zeros_like(x, dtype=float)
    if samples > 0:
        out[samples:] = x[:-samples]
    else:
        out[:samples] = x[-samples:]
    return out


def _pulse_train(t: np.ndarray, times: list[float], width_s: float, amplitude: float) -> np.ndarray:
    y = np.zeros_like(t, dtype=float)
    half = width_s / 2.0
    for center in times:
        y[(t >= center - half) & (t <= center + half)] = amplitude
    return y


def _noise(rng: np.random.Generator, n: int, scale: float) -> np.ndarray:
    return rng.normal(0.0, scale, size=n)


def _case_variant(index: int) -> str:
    return VARIANTS[index % len(VARIANTS)]


def _variant_from_capture_id(capture_id: str) -> str:
    for variant in VARIANTS:
        if capture_id.endswith(f"_{variant}"):
            return variant
    return "unknown"


def _relay_case(rng: np.random.Generator, index: int) -> CaptureRecord:
    variant = _case_variant(index)
    seed = int(rng.integers(0, 2**31 - 1))
    mode = "current" if index % 3 else "voltage"
    t, source, victim, meta = generate_inductive_case(
        seed=seed,
        sample_rate_hz=160_000.0,
        duration_s=0.012,
        source_mode=mode,
    )
    primary = victim.copy()
    true_ref = source.copy()

    if variant == "clean":
        pass
    elif variant == "noisy":
        primary += _noise(rng, len(primary), max(np.std(primary) * 0.08, 0.002))
        true_ref += _noise(rng, len(true_ref), max(np.std(true_ref) * 0.015, 0.0005))
    elif variant == "amplitude_shifted":
        primary *= float(rng.uniform(0.55, 1.65))
        true_ref *= float(rng.uniform(0.65, 1.45))
    elif variant == "timing_shifted":
        primary = _shift(primary, int(rng.integers(-10, 11)))
    elif variant == "degraded_reference":
        true_ref = 0.72 * true_ref + _noise(rng, len(true_ref), max(np.std(true_ref) * 0.04, 0.002))
    elif variant == "near_miss_ambiguous":
        primary += _hsib_transient(t, float(meta.event_time_s), amplitude=0.55, frequency_hz=1_600_000.0)

    refs = {
        "relay_source": true_ref,
        "edge_decoy": _pulse_train(t, [float(meta.event_time_s)], 12e-6, 1.0),
    }
    return CaptureRecord(
        sample_rate_hz=float(meta.sample_rate_hz),
        primary=primary,
        references=refs,
        time_s=t,
        capture_id=f"ball500_relay_{index:03d}_{variant}",
        truth_label="relay_coil_inductive_kick",
        primary_label="victim_channel",
        metadata={
            "variant": variant,
            "generator": "ball_500_v0_1",
            "reference_modes": {"relay_source": mode, "edge_decoy": "voltage"},
            "source_metadata": asdict(meta),
        },
    )


def _hsib_transient(t: np.ndarray, event_time_s: float, *, amplitude: float, frequency_hz: float, tau_s: float = 8.0e-6) -> np.ndarray:
    local_t = np.maximum(t - event_time_s, 0.0)
    return amplitude * np.exp(-local_t / tau_s) * np.sin(2.0 * np.pi * frequency_hz * local_t) * (local_t > 0.0)


def _hsib_case(rng: np.random.Generator, index: int) -> CaptureRecord:
    variant = _case_variant(index)
    sample_rate_hz = 5_000_000.0
    duration_s = 0.0005
    n = int(sample_rate_hz * duration_s)
    t = np.arange(n, dtype=float) / sample_rate_hz
    event_time = float(rng.uniform(0.00012, 0.00034))
    event_idx = int(round(event_time * sample_rate_hz))
    ref_width = 0
    reference = np.zeros(n, dtype=float)
    for offset_us, scale in [(-8.0, 0.50), (-4.0, 0.62), (0.0, 2.0), (4.0, 0.66), (8.0, 0.54)]:
        idx = event_idx + int(round(offset_us * 1e-6 * sample_rate_hz))
        reference[max(0, idx - ref_width) : min(n, idx + ref_width + 1)] = float(scale * rng.uniform(0.8, 1.4))
    amplitude = float(rng.uniform(2.7, 5.0))
    primary = _hsib_transient(
        t,
        event_time + float(rng.uniform(0.0e-6, 0.25e-6)),
        amplitude=amplitude,
        frequency_hz=float(rng.uniform(1_100_000.0, 1_900_000.0)),
        tau_s=2.5e-6,
    )
    primary += _noise(rng, n, 0.018)

    if variant == "clean":
        pass
    elif variant == "noisy":
        primary += _noise(rng, n, 0.06)
        reference += _noise(rng, n, 0.015)
    elif variant == "amplitude_shifted":
        primary *= float(rng.uniform(0.48, 1.75))
    elif variant == "timing_shifted":
        primary = _shift(primary, int(rng.integers(-6, 9)))
    elif variant == "degraded_reference":
        reference = 0.6 * reference + _noise(rng, n, 0.04)
    elif variant == "near_miss_ambiguous":
        primary += _pulse_train(t, [event_time + 80e-6], 28e-6, 0.55)

    refs = {
        "input_event": reference,
        "quiet_reference": _noise(rng, n, 0.01),
    }
    return CaptureRecord(
        sample_rate_hz=sample_rate_hz,
        primary=primary,
        references=refs,
        time_s=t,
        capture_id=f"ball500_hsib_{index:03d}_{variant}",
        truth_label="high_speed_input_bounce",
        primary_label="middle_node_response",
        metadata={"variant": variant, "generator": "ball_500_v0_1"},
    )


def _missed_pulse_case(rng: np.random.Generator, index: int) -> CaptureRecord:
    variant = _case_variant(index)
    sample_rate_hz = 50_000.0
    duration_s = 0.060
    n = int(sample_rate_hz * duration_s)
    t = np.arange(n, dtype=float) / sample_rate_hz
    pulse_count = int(rng.integers(3, 8))
    times = sorted(rng.uniform(0.008, 0.052, size=pulse_count).tolist())
    width_s = float(rng.uniform(0.00045, 0.0012))
    source_amp = float(rng.uniform(0.9, 1.4))
    source = _pulse_train(t, times, width_s, source_amp)
    missing_count = max(1, int(round(pulse_count * rng.uniform(0.22, 0.45))))
    missing_indices = set(rng.choice(np.arange(pulse_count), size=missing_count, replace=False).tolist())
    observed_times = [v for i, v in enumerate(times) if i not in missing_indices]
    output = _pulse_train(t, observed_times, width_s * float(rng.uniform(0.8, 1.25)), float(rng.uniform(0.85, 1.2)))
    output += _noise(rng, n, 0.018)

    if variant == "clean":
        pass
    elif variant == "noisy":
        output += _noise(rng, n, 0.07)
        source += _noise(rng, n, 0.025)
    elif variant == "amplitude_shifted":
        output *= float(rng.uniform(0.45, 1.65))
        source *= float(rng.uniform(0.75, 1.35))
    elif variant == "timing_shifted":
        output = _shift(output, int(rng.integers(-18, 19)))
    elif variant == "degraded_reference":
        source = 0.7 * source + _noise(rng, n, 0.055)
    elif variant == "near_miss_ambiguous":
        faint = [times[i] for i in missing_indices]
        output += _pulse_train(t, faint, width_s * 0.55, 0.34)
        output += _hsib_transient(t, float(times[0]), amplitude=0.45, frequency_hz=10_000.0)

    refs = {
        "physical_pulse": source,
        "edge_decoy": _pulse_train(t, [times[0]], 0.00012, 1.0),
    }
    return CaptureRecord(
        sample_rate_hz=sample_rate_hz,
        primary=output,
        references=refs,
        time_s=t,
        capture_id=f"ball500_missed_{index:03d}_{variant}",
        truth_label="missed_short_pulse",
        primary_label="observed_output",
        metadata={
            "variant": variant,
            "generator": "ball_500_v0_1",
            "source_thresholds": {"physical_pulse": max(0.35, 0.45 * source_amp)},
            "source_threshold": max(0.35, 0.45 * source_amp),
            "output_threshold": 0.42,
            "latency_max_s": 0.0035,
            "missed_short_pulse_max_expected_pulses": 10,
            "pulse_count": pulse_count,
            "missing_count": missing_count,
        },
    )


def generate_cases() -> list[CaptureRecord]:
    rng = np.random.default_rng(RANDOM_SEED)
    counts = {"relay_coil_inductive_kick": 167, "high_speed_input_bounce": 167, "missed_short_pulse": 166}
    cases: list[CaptureRecord] = []
    for i in range(counts["relay_coil_inductive_kick"]):
        cases.append(_relay_case(rng, i))
    for i in range(counts["high_speed_input_bounce"]):
        cases.append(_hsib_case(rng, i))
    for i in range(counts["missed_short_pulse"]):
        cases.append(_missed_pulse_case(rng, i))
    rng.shuffle(cases)
    return cases


def _case_confidence(case: CaseRunResult) -> float:
    return float(case.results[0].confidence) if case.results else 0.0


def _case_errors(case: CaseRunResult) -> list[dict[str, Any]]:
    errors = []
    for result in case.results:
        if result.errors:
            errors.append({"signature_id": result.signature_id, "errors": result.errors})
    return errors


def _write_per_case_results(case_results: list[CaseRunResult], out_dir: Path) -> pd.DataFrame:
    rows = []
    for case in case_results:
        errors = _case_errors(case)
        winner_confidence = _case_confidence(case)
        rows.append(
            {
                "capture_id": case.capture_id,
                "truth_label": case.truth_label or "",
                "winner": case.winner or "",
                "decision": case.decision,
                "winner_confidence": winner_confidence,
                "correct": bool(case.truth_label and case.winner == case.truth_label),
                "failed": bool(errors),
                "error_count": sum(len(item["errors"]) for item in errors),
                "errors_json": json.dumps(errors, sort_keys=True),
                "ranked_signature_ids": "|".join(case.ranked_signature_ids),
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(out_dir / "per_case_results.csv", index=False)
    return frame


def _write_failure_examples(case_results: list[CaseRunResult], out_dir: Path) -> None:
    failure_dir = out_dir / "failure_examples"
    failure_dir.mkdir(parents=True, exist_ok=True)
    for old_file in failure_dir.glob("*.json"):
        old_file.unlink()
    selected = []
    for case in case_results:
        confidence = _case_confidence(case)
        wrong = bool(case.truth_label and case.winner != case.truth_label)
        low_confidence = bool(case.truth_label and case.winner == case.truth_label and confidence < 0.72)
        failed = bool(_case_errors(case))
        if wrong or low_confidence or failed:
            selected.append((wrong, failed, confidence, case))
    selected.sort(key=lambda item: (not item[0], not item[1], item[2], item[3].capture_id))
    for _, _, _, case in selected[:75]:
        payload = {
            "capture_id": case.capture_id,
            "truth_label": case.truth_label,
            "winner": case.winner,
            "decision": case.decision,
            "winner_confidence": _case_confidence(case),
            "ranked_signature_ids": case.ranked_signature_ids,
            "errors": _case_errors(case),
            "ranked": [
                {
                    "signature_id": result.signature_id,
                    "matched": result.matched,
                    "confidence": result.confidence,
                    "best_reference": result.best_reference,
                    "evidence": result.evidence,
                    "rejections": result.rejections,
                    "errors": result.errors,
                    "features": result.features,
                }
                for result in case.results
            ],
        }
        (failure_dir / f"{case.capture_id}.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _top_confusions(per_case: pd.DataFrame) -> list[dict[str, Any]]:
    wrong = per_case[(per_case["correct"] == False) & (per_case["failed"] == False)]  # noqa: E712
    if wrong.empty:
        return []
    rows = []
    grouped = wrong.groupby(["truth_label", "winner"], dropna=False)
    for (truth, winner), frame in grouped:
        rows.append({"truth_label": truth, "winner": winner or "pred_none", "count": int(len(frame))})
    return sorted(rows, key=lambda row: (-row["count"], row["truth_label"], row["winner"]))[:10]


def _per_signature_accuracy(per_case: pd.DataFrame) -> dict[str, Any]:
    out = {}
    for truth, frame in per_case.groupby("truth_label", sort=True):
        total = int(len(frame))
        correct = int(frame["correct"].astype(bool).sum())
        failed = int(frame["failed"].astype(bool).sum())
        out[str(truth)] = {
            "total": total,
            "correct": correct,
            "failed": failed,
            "accuracy": correct / total if total else 0.0,
        }
    return out


def _write_summary(
    case_results: list[CaseRunResult],
    per_case: pd.DataFrame,
    out_dir: Path,
    signatures_failed_to_load: list[dict[str, str]],
    provenance: dict[str, Any],
) -> None:
    total = int(len(per_case))
    correct = int(per_case["correct"].astype(bool).sum())
    failed = int(per_case["failed"].astype(bool).sum())
    wrong = per_case[(per_case["correct"] == False) & (per_case["failed"] == False)]  # noqa: E712
    correct_frame = per_case[(per_case["correct"] == True) & (per_case["failed"] == False)]  # noqa: E712
    signature_error_counts: Counter[str] = Counter()
    for case in case_results:
        for item in _case_errors(case):
            signature_error_counts[item["signature_id"]] += len(item["errors"])

    lowest_correct = (
        correct_frame.sort_values(["winner_confidence", "capture_id"]).head(10)[
            ["capture_id", "truth_label", "winner", "winner_confidence"]
        ].to_dict("records")
        if not correct_frame.empty
        else []
    )
    highest_wrong = (
        wrong.sort_values(["winner_confidence", "capture_id"], ascending=[False, True]).head(10)[
            ["capture_id", "truth_label", "winner", "winner_confidence"]
        ].to_dict("records")
        if not wrong.empty
        else []
    )
    summary = {
        "campaign": "ball_500_v0_1",
        "campaign_id": "ball_500_v0_1",
        "provenance": provenance,
        "random_seed": RANDOM_SEED,
        "total_cases": total,
        "case_count_requested": CASE_COUNT,
        "signature_ids": SIGNATURE_IDS,
        "variant_counts": dict(sorted(Counter(_variant_from_capture_id(case.capture_id) for case in case_results).items())),
        "accuracy": correct / total if total else 0.0,
        "correct_cases": correct,
        "wrong_cases": int(len(wrong)),
        "failed_cases": failed,
        "per_signature_accuracy": _per_signature_accuracy(per_case),
        "top_confusion_pairs": _top_confusions(per_case),
        "lowest_confidence_correct_classifications": lowest_correct,
        "highest_confidence_wrong_classifications": highest_wrong,
        "signature_error_counts": dict(sorted(signature_error_counts.items())),
        "registry_failures": signatures_failed_to_load,
        "outputs": [
            "confusion_matrix.csv",
            "per_case_results.csv",
            "reference_comparison.csv",
            "summary.json",
            "failure_examples/",
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    signatures, registry_failures = load_registry(".", include_status={"implemented_synthetic"})
    signatures = [sig for sig in signatures if sig.seed_id in set(SIGNATURE_IDS)]
    signatures.sort(key=lambda sig: SIGNATURE_IDS.index(sig.seed_id))
    if [sig.seed_id for sig in signatures] != SIGNATURE_IDS:
        loaded = [sig.seed_id for sig in signatures]
        raise RuntimeError(f"expected wrapped signatures {SIGNATURE_IDS}, loaded {loaded}")

    cases = generate_cases()
    case_results = run_campaign(cases, signatures)
    provenance = _provenance()
    write_evidence_outputs(
        case_results,
        OUT_DIR,
        run_config={
            "campaign": "ball_500_v0_1",
            "campaign_id": "ball_500_v0_1",
            "provenance": provenance,
            "random_seed": RANDOM_SEED,
            "case_count": CASE_COUNT,
            "signature_ids": SIGNATURE_IDS,
            "variants": VARIANTS,
            "notes": "Synthetic stress campaign for Gamma Core v0.1 tournament ranking.",
        },
        signatures_failed_to_load=registry_failures,
    )
    per_case = _write_per_case_results(case_results, OUT_DIR)
    _write_failure_examples(case_results, OUT_DIR)
    _write_summary(case_results, per_case, OUT_DIR, registry_failures, provenance)

    with (OUT_DIR / "stress_campaign_stdout_summary.txt").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerow(["total_cases", len(per_case)])
        writer.writerow(["accuracy", f"{float(per_case['correct'].mean()):.6f}"])
        writer.writerow(["failed_cases", int(per_case["failed"].astype(bool).sum())])
    print(json.dumps(json.loads((OUT_DIR / "summary.json").read_text(encoding="utf-8")), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
