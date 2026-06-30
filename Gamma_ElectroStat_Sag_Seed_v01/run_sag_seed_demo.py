"""Run synthetic validation and create user-facing artifacts for Sag Seed v0.1."""

from __future__ import annotations

from pathlib import Path
import json
import time
import zipfile
import os

# Tiny linear algebra repeated hundreds of times is faster and more stable with
# one BLAS thread than with a large thread pool on this workload.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from gamma_sag_seed_v01 import (
    SagConfig,
    fit_sag_baseline,
    make_reference_waveform,
    make_healthy_population,
    make_synthetic_case,
    run_sag_seed,
)

OUT = Path(__file__).resolve().parent
SEED = 230626
DT = 0.001
T = np.arange(0.0, 2.0, DT)
CASES = (
    "clean_sag",
    "gradual_sag",
    "distorted_sag",
    "healthy",
    "offset_step",
    "phase_glitch",
    "swell",
    "impulse_only",
    "short_dip",
)
POSITIVE_CASES = {"clean_sag", "gradual_sag", "distorted_sag"}
REPEATS_PER_CASE = 100


def supported(status: str) -> bool:
    return status in {"clean_sag_supported", "distorted_sag_supported"}


def main() -> None:
    rng = np.random.default_rng(SEED)
    reference = make_reference_waveform(T)
    healthy = make_healthy_population(reference, DT, 100, rng)
    config = SagConfig(
        candidate_windows=(41, 81, 161, 241),
        max_alignment_lag=25,
        enter_sigma=3.0,
        exit_sigma=1.25,
        enter_persistence_s=0.020,
        exit_persistence_s=0.030,
        minimum_event_s=0.035,
    )

    start_time = time.perf_counter()
    baseline = fit_sag_baseline(healthy, DT, config)

    # Representative cases use a separate deterministic stream.
    representative_rng = np.random.default_rng(SEED + 1)
    representative = {}
    for case in CASES:
        waveform, truth = make_synthetic_case(reference, DT, representative_rng, case)
        evidence = run_sag_seed(baseline, waveform, config)
        representative[case] = (waveform, truth, evidence)

    rows = []
    evaluation_rng = np.random.default_rng(SEED + 2)
    for case in CASES:
        for repeat in range(REPEATS_PER_CASE):
            waveform, truth = make_synthetic_case(reference, DT, evaluation_rng, case)
            evidence = run_sag_seed(baseline, waveform, config)
            detected = supported(evidence.status)
            event = max(evidence.events, key=lambda item: item.confidence) if evidence.events else None

            row = {
                "case": case,
                "repeat": repeat,
                "true_sag": case in POSITIVE_CASES,
                "detected_sag": detected,
                "status": evidence.status,
                "selected_window_samples": evidence.selected_window,
                "alignment_lag_samples": evidence.alignment_lag_samples,
                "alignment_correlation": evidence.alignment_correlation,
                "event_count": len(evidence.events),
                "confidence": event.confidence if event else 0.0,
                "classification": event.classification if event else "none",
                "true_start_s": truth["true_start_s"],
                "true_end_s": truth["true_end_s"],
                "retained_gain": truth["retained_gain"],
                "detected_start_s": event.start_time if event else np.nan,
                "detected_end_s": event.end_time if event else np.nan,
                "max_depth": event.max_depth if event else np.nan,
                "deficit_area_s": event.deficit_area_s if event else np.nan,
                "entry_timescale_s": event.entry_timescale_s if event else np.nan,
                "recovery_timescale_s": event.recovery_timescale_s if event else np.nan,
                "median_correlation": event.median_correlation if event else np.nan,
                "median_rms_ratio": event.median_rms_ratio if event else np.nan,
                "unknown_residual_energy": event.unknown_residual_energy if event else np.nan,
            }
            if event and case in POSITIVE_CASES:
                row["start_error_s"] = event.start_time - float(truth["true_start_s"])
                row["end_error_s"] = event.end_time - float(truth["true_end_s"])
            else:
                row["start_error_s"] = np.nan
                row["end_error_s"] = np.nan
            rows.append(row)

    results = pd.DataFrame(rows)
    results_path = OUT / "sag_seed_v01_monte_carlo_results.csv"
    results.to_csv(results_path, index=False)

    summary_rows = []
    for case, group in results.groupby("case", sort=False):
        true_sag = bool(group["true_sag"].iloc[0])
        detection_rate = float(group["detected_sag"].mean())
        detected_group = group[group["detected_sag"]]
        summary_rows.append(
            {
                "case": case,
                "true_sag": true_sag,
                "runs": len(group),
                "detection_rate": detection_rate,
                "median_confidence_when_detected": float(detected_group["confidence"].median()) if len(detected_group) else np.nan,
                "median_selected_window_samples": float(group["selected_window_samples"].median()),
                "median_abs_start_error_ms": float(group["start_error_s"].abs().median() * 1000.0) if true_sag else np.nan,
                "median_abs_end_error_ms": float(group["end_error_s"].abs().median() * 1000.0) if true_sag else np.nan,
                "clean_label_rate": float((group["classification"] == "clean_sag_supported").mean()),
                "distorted_label_rate": float((group["classification"] == "distorted_sag_supported").mean()),
            }
        )
    summary = pd.DataFrame(summary_rows)

    positives = results[results["true_sag"]]
    negatives = results[~results["true_sag"]]
    tp = int(positives["detected_sag"].sum())
    fn = int((~positives["detected_sag"]).sum())
    fp = int(negatives["detected_sag"].sum())
    tn = int((~negatives["detected_sag"]).sum())
    overall = pd.DataFrame(
        [
            {
                "true_positives": tp,
                "false_negatives": fn,
                "false_positives": fp,
                "true_negatives": tn,
                "sensitivity": tp / max(tp + fn, 1),
                "specificity": tn / max(tn + fp, 1),
                "precision": tp / max(tp + fp, 1),
                "balanced_accuracy": 0.5 * (
                    tp / max(tp + fn, 1) + tn / max(tn + fp, 1)
                ),
            }
        ]
    )

    summary_path = OUT / "sag_seed_v01_case_summary.csv"
    overall_path = OUT / "sag_seed_v01_overall_summary.csv"
    summary.to_csv(summary_path, index=False)
    overall.to_csv(overall_path, index=False)

    # Representative waveform comparison.
    waveform, truth, evidence = representative["clean_sag"]
    aligned_waveform = np.interp(
        np.arange(waveform.size) + evidence.alignment_lag_samples,
        np.arange(waveform.size),
        waveform,
        left=waveform[0],
        right=waveform[-1],
    )
    plt.figure(figsize=(10, 5.2))
    plt.plot(T, baseline.mean_waveform, label="Healthy collective waveform")
    plt.plot(T, aligned_waveform, label="Aligned test waveform", alpha=0.85)
    for event in evidence.events:
        plt.axvspan(event.start_time, event.end_time, alpha=0.16, label="Detected sag block")
    plt.xlabel("Time (s)")
    plt.ylabel("Amplitude")
    plt.title("Sag Seed v0.1 — aligned raw waveform and detected event")
    plt.legend()
    plt.grid(True, alpha=0.25)
    plt.tight_layout()
    waveform_plot = OUT / "sag_seed_v01_waveform_event.png"
    plt.savefig(waveform_plot, dpi=180)
    plt.close()

    # Local gain and RMS confirmation.
    plt.figure(figsize=(10, 5.2))
    plt.plot(T, evidence.beta_trace, label="Local gain β(t)")
    plt.plot(T, evidence.rms_ratio_trace, label="Local RMS ratio")
    plt.axhline(1.0, linestyle="--", label="Expected ratio")
    for event in evidence.events:
        plt.axvspan(event.start_time, event.end_time, alpha=0.16)
    plt.xlabel("Time (s)")
    plt.ylabel("Ratio to healthy expectation")
    plt.title("Local gain and RMS evidence for a clean sag")
    plt.legend()
    plt.grid(True, alpha=0.25)
    plt.tight_layout()
    feature_plot = OUT / "sag_seed_v01_gain_rms.png"
    plt.savefig(feature_plot, dpi=180)
    plt.close()

    # Joint sigma evidence and hysteresis thresholds.
    plt.figure(figsize=(10, 5.2))
    plt.plot(T, evidence.joint_deficit_sigma_trace, label="Joint deficit evidence")
    plt.axhline(config.enter_sigma, linestyle="--", label="Entry threshold")
    plt.axhline(config.exit_sigma, linestyle=":", label="Exit threshold")
    for event in evidence.events:
        plt.axvspan(event.start_time, event.end_time, alpha=0.16)
    plt.xlabel("Time (s)")
    plt.ylabel("Joint deficit (robust σ)")
    plt.title("Statistical hysteresis and persistence event trace")
    plt.legend()
    plt.grid(True, alpha=0.25)
    plt.tight_layout()
    evidence_plot = OUT / "sag_seed_v01_hysteresis_evidence.png"
    plt.savefig(evidence_plot, dpi=180)
    plt.close()

    # Residual separation.
    plt.figure(figsize=(10, 5.2))
    plt.plot(T, evidence.residual, label="Residual after sag reconstruction", alpha=0.75)
    plt.plot(T, evidence.known_noise_residual, label="Known healthy-noise component")
    plt.plot(T, evidence.unknown_residual, label="Unexplained residual", alpha=0.75)
    plt.xlabel("Time (s)")
    plt.ylabel("Residual amplitude")
    plt.title("Residual decomposition after the sag model explains local scaling")
    plt.legend()
    plt.grid(True, alpha=0.25)
    plt.tight_layout()
    residual_plot = OUT / "sag_seed_v01_residual_decomposition.png"
    plt.savefig(residual_plot, dpi=180)
    plt.close()

    # Detection rate by case.
    plt.figure(figsize=(10, 5.2))
    positions = np.arange(len(summary))
    plt.bar(positions, summary["detection_rate"] * 100.0)
    plt.xticks(positions, summary["case"], rotation=30, ha="right")
    plt.ylabel("Sag-supported runs (%)")
    plt.title("Synthetic Sag Seed v0.1 detection rate by scenario")
    plt.ylim(0, 105)
    plt.grid(True, axis="y", alpha=0.25)
    plt.tight_layout()
    rate_plot = OUT / "sag_seed_v01_detection_rates.png"
    plt.savefig(rate_plot, dpi=180)
    plt.close()

    representative_json = OUT / "sag_seed_v01_representative_result.json"
    representative_json.write_text(
        json.dumps(evidence.summary_dict(), indent=2), encoding="utf-8"
    )

    readme = OUT / "README.md"
    readme.write_text(
        f"""# Gamma / ElectroStat Sag Seed v0.1

This bundle implements the agreed synthetic sag worker:

1. align the raw capture to the WaveCompare healthy collective;
2. let the sag seed test several analysis windows;
3. estimate local affine gain, offset, correlation, and RMS ratio;
4. require local gain and RMS to fall abnormally together;
5. apply statistical hysteresis and temporal persistence;
6. construct a bounded event block;
7. measure depth, duration, deficit area, entry/recovery slopes, and amplitude-over-slope timescales;
8. separate ordinary healthy residual modes from unexplained residual structure.

## Synthetic validation

- Healthy training captures: 100
- Validation runs: {len(results)} ({REPEATS_PER_CASE} per scenario)
- Candidate windows: {config.candidate_windows}
- Entry/exit thresholds: {config.enter_sigma:.2f}σ / {config.exit_sigma:.2f}σ
- Entry/exit persistence: {config.enter_persistence_s*1000:.0f} ms / {config.exit_persistence_s*1000:.0f} ms

The validation is model-designed and synthetic. It proves the implementation behaves coherently on controlled examples; it does not validate field power-quality performance or establish standard thresholds.
""",
        encoding="utf-8",
    )

    runtime = time.perf_counter() - start_time
    run_info = OUT / "run_information.txt"
    run_info.write_text(
        f"Seed: {SEED}\nRuntime seconds: {runtime:.3f}\nValidation runs: {len(results)}\n",
        encoding="utf-8",
    )

    bundle = OUT.parent / "Gamma_ElectroStat_Sag_Seed_v01.zip"
    files = [
        OUT / "gamma_sag_seed_v01.py",
        OUT / "test_gamma_sag_seed.py",
        OUT / "run_sag_seed_demo.py",
        readme,
        run_info,
        results_path,
        summary_path,
        overall_path,
        representative_json,
        waveform_plot,
        feature_plot,
        evidence_plot,
        residual_plot,
        rate_plot,
    ]
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in files:
            zf.write(file, arcname=file.name)

    print(summary.to_string(index=False))
    print("\nOverall:")
    print(overall.to_string(index=False))
    print(f"\nRuntime: {runtime:.2f} s")
    print(f"Bundle: {bundle}")


if __name__ == "__main__":
    main()
