from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from missed_short_pulse_analyzer import analyze_missed_short_pulse_v2


CLASSES = [
    "healthy",
    "complete_absence",
    "subthreshold_rc",
    "width_collapse",
    "late",
    "merge",
    "split",
    "stretched",
    "extra_spurious",
    "acquisition_limited",
]

EXPECTED_CLASS = {
    "healthy": "valid pulse propagation",
    "complete_absence": "complete pulse non-propagation",
    "subthreshold_rc": "subthreshold pulse suppression",
    "width_collapse": "pulse-width collapse",
    "late": "late pulse propagation",
    "merge": "pulse merging",
    "split": "pulse splitting",
    "stretched": "pulse stretching",
    "extra_spurious": "valid pulse propagation",
    "acquisition_limited": "possible acquisition miss",
}

def random_pulse_train(
    t: np.ndarray,
    pulse_specs: list[tuple[float, float, float]],
) -> np.ndarray:
    y = np.zeros_like(t)
    for start, width, amplitude in pulse_specs:
        y[(t >= start) & (t < start + width)] = amplitude
    return y

def delay_signal(t: np.ndarray, x: np.ndarray, delay_s: float) -> np.ndarray:
    return np.interp(t - delay_s, t, x, left=0.0, right=0.0)

def first_order_filter(t: np.ndarray, x: np.ndarray, tau_s: float) -> np.ndarray:
    dt = float(np.median(np.diff(t)))
    alpha = dt / (tau_s + dt)
    y = np.zeros_like(x, dtype=float)
    for i in range(1, len(x)):
        y[i] = y[i - 1] + alpha * (x[i] - y[i - 1])
    return y

def add_noise(x: np.ndarray, sigma: float, rng: np.random.Generator) -> np.ndarray:
    return np.asarray(x, dtype=float) + rng.normal(0.0, sigma, len(x))

def random_case(
    case: str,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict, dict]:
    latency_min = rng.uniform(80e-6, 250e-6)
    latency_max = rng.uniform(2.0e-3, 3.5e-3)
    source_amplitude = rng.uniform(20.0, 28.0)
    threshold = 0.5 * source_amplitude
    noise_source = rng.uniform(0.01, 0.08)
    noise_output = rng.uniform(0.015, 0.12)

    if case == "acquisition_limited":
        fs = float(rng.choice([40_000, 50_000, 62_500, 80_000, 100_000]))
        duration = 0.012
        t = np.arange(0, duration, 1 / fs)
        sample_index = int(rng.integers(int(0.25 * len(t)), int(0.55 * len(t))))
        start = float(t[sample_index])
        width = 1 / fs  # exactly one sample period
        source = random_pulse_train(t, [(start, width, source_amplitude)])
        output = np.zeros_like(t)
        min_width = 0.5 / fs
        bandwidth = rng.uniform(0.05, 0.25) * fs
        params = {
            "fs": fs,
            "source_width_s": width,
            "latency_min_s": latency_min,
            "latency_max_s": latency_max,
            "minimum_valid_width_s": min_width,
            "source_amplitude": source_amplitude,
            "output_noise": noise_output,
        }
        return (
            t,
            add_noise(source, noise_source, rng),
            add_noise(output, noise_output, rng),
            {
                "source_threshold": threshold,
                "output_threshold": threshold,
                "latency_min_s": latency_min,
                "latency_max_s": latency_max,
                "minimum_valid_output_width_s": min_width,
                "acquisition_bandwidth_hz": bandwidth,
            },
            params,
        )

    fs = float(rng.choice([400_000, 500_000, 625_000, 800_000, 1_000_000, 1_250_000]))
    duration = 0.026
    t = np.arange(0, duration, 1 / fs)
    start = rng.uniform(0.0035, 0.0065)
    source_width = rng.uniform(180e-6, 700e-6)
    latency = rng.uniform(max(latency_min, 250e-6), min(latency_max * 0.55, 1.5e-3))
    min_width = rng.uniform(0.38, 0.58) * source_width
    bandwidth = rng.uniform(5e6, 30e6)

    source = np.zeros_like(t)
    output = np.zeros_like(t)

    if case == "healthy":
        count = int(rng.integers(1, 4))
        spacing = rng.uniform(4e-3, 7e-3)
        specs = []
        for k in range(count):
            width_k = source_width * rng.uniform(0.8, 1.2)
            specs.append((start + k * spacing, width_k, source_amplitude))
        source = random_pulse_train(t, specs)
        output = delay_signal(t, source, latency)
        tau = rng.uniform(3e-6, 18e-6)
        output = first_order_filter(t, output, tau)

    elif case == "complete_absence":
        source = random_pulse_train(t, [(start, source_width, source_amplitude)])
        output = np.zeros_like(t)

    elif case == "subthreshold_rc":
        source_width = rng.uniform(60e-6, 220e-6)
        source = random_pulse_train(t, [(start, source_width, source_amplitude)])
        delayed = delay_signal(t, source, latency)
        # Force a peak safely below threshold while retaining a clear analog response.
        tau = rng.uniform(3.0, 8.0) * source_width
        output = first_order_filter(t, delayed, tau)

    elif case == "width_collapse":
        source = random_pulse_train(t, [(start, source_width, source_amplitude)])
        ratio = rng.uniform(0.10, 0.36)
        output_width = source_width * ratio
        output = random_pulse_train(
            t,
            [(start + latency, output_width, source_amplitude)],
        )

    elif case == "late":
        source = random_pulse_train(t, [(start, source_width, source_amplitude)])
        late_latency = rng.uniform(
            max(latency_max + 1.2e-3, 4.5e-3),
            min(0.014, max(latency_max * 3.5, 7e-3)),
        )
        output = random_pulse_train(
            t,
            [(start + late_latency, source_width * rng.uniform(0.85, 1.15), source_amplitude)],
        )

    elif case == "merge":
        width_1 = rng.uniform(180e-6, 360e-6)
        width_2 = rng.uniform(180e-6, 360e-6)
        gap = rng.uniform(120e-6, 550e-6)
        start_2 = start + width_1 + gap
        source = random_pulse_train(
            t,
            [
                (start, width_1, source_amplitude),
                (start_2, width_2, source_amplitude),
            ],
        )
        output_start = start + latency
        output_end = start_2 + latency + width_2 + rng.uniform(80e-6, 300e-6)
        output = random_pulse_train(
            t,
            [(output_start, output_end - output_start, source_amplitude)],
        )
        source_width = min(width_1, width_2)
        min_width = 0.4 * source_width

    elif case == "split":
        source_width = rng.uniform(400e-6, 900e-6)
        source = random_pulse_train(t, [(start, source_width, source_amplitude)])
        first_width = rng.uniform(80e-6, 220e-6)
        separation = rng.uniform(90e-6, 350e-6)
        second_width = rng.uniform(80e-6, 240e-6)
        output = random_pulse_train(
            t,
            [
                (start + latency, first_width, source_amplitude),
                (start + latency + first_width + separation, second_width, source_amplitude),
            ],
        )
        min_width = rng.uniform(60e-6, 120e-6)

    elif case == "stretched":
        source = random_pulse_train(t, [(start, source_width, source_amplitude)])
        output_width = source_width * rng.uniform(1.8, 4.5)
        output = random_pulse_train(
            t,
            [(start + latency, output_width, source_amplitude)],
        )

    elif case == "extra_spurious":
        source = random_pulse_train(t, [(start, source_width, source_amplitude)])
        output = random_pulse_train(
            t,
            [
                (start + latency, source_width * rng.uniform(0.85, 1.15), source_amplitude),
                (rng.uniform(0.018, 0.023), rng.uniform(150e-6, 500e-6), source_amplitude),
            ],
        )

    else:
        raise ValueError(case)

    params = {
        "fs": fs,
        "source_width_s": source_width,
        "latency_min_s": latency_min,
        "latency_max_s": latency_max,
        "minimum_valid_width_s": min_width,
        "source_amplitude": source_amplitude,
        "output_noise": noise_output,
    }

    return (
        t,
        add_noise(source, noise_source, rng),
        add_noise(output, noise_output, rng),
        {
            "source_threshold": threshold,
            "output_threshold": threshold,
            "latency_min_s": latency_min,
            "latency_max_s": latency_max,
            "minimum_valid_output_width_s": min_width,
            "acquisition_bandwidth_hz": bandwidth,
        },
        params,
    )


def run_validation(output_dir: Path, seed: int = 6262026, trials_per_class: int = 100) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    rows = []
    failures = []
    trial_id = 0

    for case in CLASSES:
        for class_trial in range(trials_per_class):
            trial_id += 1
            t, source, output, meta, params = random_case(case, rng)

            frame, summary, diagnostics = analyze_missed_short_pulse_v2(
                t=t,
                source=source,
                output=output,
                source_threshold=meta["source_threshold"],
                output_threshold=meta["output_threshold"],
                latency_min_s=meta["latency_min_s"],
                latency_max_s=meta["latency_max_s"],
                minimum_valid_output_width_s=meta["minimum_valid_output_width_s"],
                sample_rate_hz=params["fs"],
                acquisition_bandwidth_hz=meta["acquisition_bandwidth_hz"],
                system_consequence="logically missed",
            )

            expected = EXPECTED_CLASS[case]
            observed = summary.dominant_classification
            passed = observed == expected

            if case == "extra_spurious":
                passed = (
                    observed == "valid pulse propagation"
                    and summary.extra_output_pulses >= 1
                )

            row = {
                "trial_id": trial_id,
                "case": case,
                "expected": expected,
                "observed": observed,
                "pass": bool(passed),
                "expected_pulses": summary.expected_pulses,
                "matched_pulses": summary.matched_pulses,
                "missed_pulses": summary.missed_pulses,
                "split_pulses": summary.split_pulses,
                "merged_groups": summary.merged_groups,
                "extra_output_pulses": summary.extra_output_pulses,
                "detection_ratio": summary.detection_ratio,
                "acquisition_limited_events": summary.acquisition_limited_events,
                **params,
            }

            if not frame.empty:
                row["first_event_class"] = frame.iloc[0]["observed_failure_mode"]
                row["first_event_confidence"] = frame.iloc[0]["confidence"]
                row["first_event_peak"] = frame.iloc[0]["downstream_peak"]
                row["estimated_tau_s"] = frame.iloc[0]["estimated_tau_s"]
                row["estimated_cutoff_hz"] = frame.iloc[0]["estimated_cutoff_hz"]

            rows.append(row)

            if not passed:
                failures.append(
                    {
                        "trial_id": trial_id,
                        "case": case,
                        "expected": expected,
                        "observed": observed,
                        "params": params,
                        "events": frame.to_dict(orient="records"),
                    }
                )

    trials = pd.DataFrame(rows)
    per_class = (
        trials.groupby("case")
        .agg(
            trials=("trial_id", "count"),
            passed=("pass", "sum"),
            accuracy=("pass", "mean"),
            mean_detection_ratio=("detection_ratio", "mean"),
            mean_expected_pulses=("expected_pulses", "mean"),
            mean_missed_pulses=("missed_pulses", "mean"),
            mean_extra_outputs=("extra_output_pulses", "mean"),
        )
        .reset_index()
    )
    confusion = pd.crosstab(
        trials["expected"],
        trials["observed"],
        rownames=["Expected"],
        colnames=["Observed"],
    )

    trials.to_csv(output_dir / "monte_carlo_trials.csv", index=False)
    per_class.to_csv(output_dir / "per_class_summary.csv", index=False)
    confusion.to_csv(output_dir / "confusion_matrix.csv")
    (output_dir / "failed_cases.json").write_text(
        json.dumps(failures, indent=2),
        encoding="utf-8",
    )

    total = len(trials)
    passed = int(trials["pass"].sum())
    print(f"{passed}/{total} passed ({passed / total:.2%})")
    print(per_class[["case", "passed", "trials", "accuracy"]].to_string(index=False))
    return trials


def main() -> None:
    parser = argparse.ArgumentParser(description="Run randomized Missed Short Pulse validation.")
    parser.add_argument("--output-dir", default="missed_short_pulse_validation")
    parser.add_argument("--seed", type=int, default=6262026)
    parser.add_argument("--trials-per-class", type=int, default=100)
    args = parser.parse_args()

    run_validation(
        output_dir=Path(args.output_dir),
        seed=args.seed,
        trials_per_class=args.trials_per_class,
    )


if __name__ == "__main__":
    main()
