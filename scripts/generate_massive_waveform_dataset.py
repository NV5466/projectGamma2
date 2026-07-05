from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gamma_app.registry import ALLOWED_FAMILIES, is_mechanical_only_id, read_seed_registry_entries


DATASET_ID = "massive_1900"
SAMPLE_RATE_HZ = 100_000.0
DURATION_S = 0.050
SAMPLES = int(SAMPLE_RATE_HZ * DURATION_S)
CHANNEL_NAMES = ["primary", "reference_command"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a reproducible Gamma waveform validation dataset.")
    parser.add_argument("--registry", default="seed_registry.yaml")
    parser.add_argument("--out", default="validation/generated/massive_1900")
    parser.add_argument("--sets-per-signature", type=int, default=10)
    parser.add_argument("--chunks-per-set", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1337)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.chunks_per_set != 10:
        raise SystemExit("chunks-per-set must be 10: 5 positive and 5 negative chunks are required per set")
    out = Path(args.out)
    rows = generate_dataset(
        registry_path=Path(args.registry),
        out_dir=out,
        sets_per_signature=args.sets_per_signature,
        seed=args.seed,
    )
    write_outputs(out, rows, args)
    print(json.dumps(build_summary(rows, args), indent=2, sort_keys=True))
    return 0


def generate_dataset(
    *,
    registry_path: Path,
    out_dir: Path,
    sets_per_signature: int,
    seed: int,
) -> list[dict[str, Any]]:
    entries = load_electrical_registry_entries(registry_path)
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    created_at = datetime.now(timezone.utc).isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    for signature_index, entry in enumerate(entries):
        signature_id = str(entry["seed_id"])
        family = str(entry["family"])
        generator_status = generator_status_for(entry)
        for set_index in range(sets_per_signature):
            set_noise_scale = float(rng.uniform(0.006, 0.028))
            set_dir = out_dir / "signatures" / signature_id / f"set_{set_index:03d}"
            set_dir.mkdir(parents=True, exist_ok=True)
            chunk_specs = [
                *[("positive", idx, "normal") for idx in range(3)],
                *[("positive", idx, "high") for idx in range(3, 5)],
                *[("negative", idx, "normal") for idx in range(3)],
                *[("negative", idx, "high") for idx in range(3, 5)],
            ]
            for local_index, (truth_label, truth_index, noise_tier) in enumerate(chunk_specs):
                noise_multiplier = 2.0 if noise_tier == "high" else 1.0
                noise_scale = set_noise_scale * noise_multiplier
                chunk_seed = int(rng.integers(0, 2**31 - 1))
                chunk_rng = np.random.default_rng(chunk_seed)
                expected_fault_present = truth_label == "positive"
                variant = negative_variant(local_index, signature_index) if not expected_fault_present else "true_to_form"
                waveform = synthesize_waveform(
                    signature_id=signature_id,
                    family=family,
                    expected_fault_present=expected_fault_present,
                    variant=variant,
                    rng=chunk_rng,
                    noise_scale=noise_scale,
                    signature_index=signature_index,
                    set_index=set_index,
                )
                capture_id = f"{signature_id}__set{set_index:03d}__{'pos' if expected_fault_present else 'neg'}{truth_index:02d}__{noise_tier}_noise"
                file_path = set_dir / f"{capture_id}.npz"
                metadata = {
                    "capture_id": capture_id,
                    "signature_id": signature_id,
                    "family": family,
                    "set_index": set_index,
                    "chunk_index": local_index,
                    "truth_label": truth_label,
                    "expected_fault_present": expected_fault_present,
                    "noise_tier": noise_tier,
                    "noise_scale": noise_scale,
                    "set_noise_scale": set_noise_scale,
                    "high_noise_multiplier": noise_multiplier,
                    "sample_rate_hz": SAMPLE_RATE_HZ,
                    "duration_s": DURATION_S,
                    "channel_names": CHANNEL_NAMES,
                    "generator_name": "gamma_massive_synthetic_v1",
                    "generator_status": generator_status,
                    "random_seed": seed,
                    "chunk_seed": chunk_seed,
                    "threshold_profile": "default",
                    "created_at": created_at,
                    "variant": variant,
                    "notes": generator_notes(entry, variant),
                }
                np.savez_compressed(
                    file_path,
                    sample_rate_hz=np.array(SAMPLE_RATE_HZ),
                    primary=waveform["primary"],
                    secondary=waveform["reference_command"],
                    reference_command=waveform["reference_command"],
                    time_s=waveform["time_s"],
                    capture_id=np.array(capture_id),
                    truth_label=np.array(signature_id if expected_fault_present else ""),
                    primary_label=np.array("primary"),
                    references_json=np.array(json.dumps({"command": "reference_command"})),
                    metadata_json=np.array(json.dumps(metadata, sort_keys=True)),
                )
                row = {
                    **metadata,
                    "relative_path": file_path.relative_to(out_dir).as_posix(),
                    "file_name": file_path.name,
                    "file_size_bytes": file_path.stat().st_size,
                }
                rows.append(row)
    return rows


def load_electrical_registry_entries(path: Path) -> list[dict[str, Any]]:
    entries = read_seed_registry_entries(path)
    if len(entries) != 19:
        raise ValueError(f"expected 19 registered electrical signatures, found {len(entries)}")
    bad = [
        entry
        for entry in entries
        if entry.get("family") not in ALLOWED_FAMILIES or is_mechanical_only_id(str(entry.get("seed_id", "")))
    ]
    if bad:
        raise ValueError(f"registry contains non-electrical or mechanical-only entries: {bad}")
    return entries


def synthesize_waveform(
    *,
    signature_id: str,
    family: str,
    expected_fault_present: bool,
    variant: str,
    rng: np.random.Generator,
    noise_scale: float,
    signature_index: int,
    set_index: int,
) -> dict[str, np.ndarray]:
    t = np.arange(SAMPLES, dtype=float) / SAMPLE_RATE_HZ
    phase = 0.11 * signature_index + 0.03 * set_index
    baseline = 0.08 * np.sin(2 * np.pi * (60.0 + signature_index) * t + phase)
    reference = command_reference(t, rng, signature_index)
    primary = baseline.copy()
    if family == "power_quality":
        primary += power_quality_pattern(t, signature_id, expected_fault_present, variant, rng)
    elif family == "switching_emc":
        primary += switching_emc_pattern(t, signature_id, expected_fault_present, variant, rng)
    elif family == "digital_timing":
        primary += digital_timing_pattern(t, signature_id, expected_fault_present, variant, rng)
    elif family == "measurement_artifact":
        primary += measurement_artifact_pattern(t, signature_id, expected_fault_present, variant, rng)
    else:
        raise ValueError(f"unsupported family: {family}")
    primary += rng.normal(0.0, noise_scale, size=SAMPLES)
    reference = reference + rng.normal(0.0, noise_scale * 0.45, size=SAMPLES)
    return {"time_s": t, "primary": primary.astype(float), "reference_command": reference.astype(float)}


def command_reference(t: np.ndarray, rng: np.random.Generator, signature_index: int) -> np.ndarray:
    command = np.zeros_like(t)
    event_time = 0.012 + 0.001 * (signature_index % 9) + float(rng.uniform(-0.0004, 0.0004))
    command[t >= event_time] = 1.0
    return command


def power_quality_pattern(t: np.ndarray, signature_id: str, positive: bool, variant: str, rng: np.random.Generator) -> np.ndarray:
    wave = np.sin(2 * np.pi * 60.0 * t)
    start, end = 0.014, 0.032
    mask = (t >= start) & (t <= end)
    if not positive:
        if variant == "subthreshold_event":
            wave[mask] *= 0.94
        elif variant == "wrong_family_waveform":
            wave += gaussian_pulse(t, 0.021, 0.00018, 0.12)
        elif variant == "timing_shifted_event":
            wave[(t >= 0.040) & (t <= 0.046)] *= 0.82
        else:
            wave += 0.02 * np.sin(2 * np.pi * 180.0 * t)
        return wave
    if "sag" in signature_id:
        wave[mask] *= 0.55
    elif "swell" in signature_id:
        wave[mask] *= 1.45
    elif "interruption" in signature_id:
        wave[mask] *= 0.05
    elif "harmonic" in signature_id:
        wave += 0.22 * np.sin(2 * np.pi * 300.0 * t) + 0.11 * np.sin(2 * np.pi * 420.0 * t)
    elif "flicker" in signature_id:
        wave *= 1.0 + 0.22 * np.sin(2 * np.pi * 9.0 * t)
    elif "notch" in signature_id:
        for center in np.arange(0.006, 0.046, 1 / 360.0):
            wave -= gaussian_pulse(t, center, 0.00007, 0.35)
    elif "impulsive" in signature_id:
        wave += gaussian_pulse(t, 0.023 + rng.uniform(-0.002, 0.002), 0.00008, 1.2)
    elif "oscillatory" in signature_id:
        center = 0.023
        ring = np.exp(-np.maximum(t - center, 0) / 0.004) * np.sin(2 * np.pi * 1800.0 * np.maximum(t - center, 0))
        wave += (t >= center) * 0.55 * ring
    return wave


def switching_emc_pattern(t: np.ndarray, signature_id: str, positive: bool, variant: str, rng: np.random.Generator) -> np.ndarray:
    wave = np.zeros_like(t)
    if not positive:
        if variant == "near_miss_waveform":
            wave += gaussian_pulse(t, 0.021, 0.00022, 0.10)
        elif variant == "wrong_family_waveform":
            wave += 0.2 * np.sin(2 * np.pi * 60.0 * t)
        elif variant == "harmless_noise_burst":
            wave += burst(t, 0.028, 0.0025, 650.0, 0.08)
        else:
            wave += gaussian_pulse(t, 0.041, 0.00012, 0.14)
        return wave
    if "eft" in signature_id:
        for center in np.linspace(0.017, 0.026, 9):
            wave += gaussian_pulse(t, center + rng.uniform(-0.00012, 0.00012), 0.000035, 0.55)
    elif "inrush" in signature_id:
        onset = 0.012
        wave += (t >= onset) * 1.1 * np.exp(-(t - onset) / 0.010)
    elif "relay_coil" in signature_id:
        wave += gaussian_pulse(t, 0.021, 0.00013, 1.1)
        wave -= gaussian_pulse(t, 0.02145, 0.00022, 0.35)
    elif "pwm" in signature_id:
        wave += burst(t, 0.018, 0.020, 3200.0, 0.42)
        for center in np.arange(0.012, 0.041, 0.003):
            wave += gaussian_pulse(t, center, 0.00004, 0.25)
    return wave


def digital_timing_pattern(t: np.ndarray, signature_id: str, positive: bool, variant: str, rng: np.random.Generator) -> np.ndarray:
    wave = np.zeros_like(t)
    if not positive:
        if variant == "near_miss_waveform":
            wave += digital_pulse(t, 0.020, 0.004, 0.45)
        elif variant == "timing_shifted_event":
            wave += digital_pulse(t, 0.043, 0.001, 0.7)
        elif variant == "subthreshold_event":
            wave += digital_pulse(t, 0.020, 0.0005, 0.18)
        else:
            wave += digital_pulse(t, 0.015, 0.014, 0.55)
        return wave
    if "contact_bounce" in signature_id:
        for center in [0.018, 0.0187, 0.0194, 0.0202, 0.0212]:
            wave += digital_pulse(t, center, 0.00032, 0.65)
    elif "threshold_chatter" in signature_id:
        wave += 0.04 * np.sin(2 * np.pi * 70.0 * t)
        for center in np.linspace(0.018, 0.026, 12):
            wave += digital_pulse(t, center, 0.00022, 0.25 * (-1 if int(center * 1e6) % 2 else 1))
    elif "slow_edge" in signature_id:
        wave += np.clip((t - 0.015) / 0.018, 0, 1)
    elif "missed_short_pulse" in signature_id:
        wave += digital_pulse(t, 0.021, 0.00022, 0.9)
    elif "high_speed_input_bounce" in signature_id:
        for center in np.linspace(0.020, 0.022, 7):
            wave += digital_pulse(t, center, 0.00011, 0.75)
    return wave


def measurement_artifact_pattern(t: np.ndarray, signature_id: str, positive: bool, variant: str, rng: np.random.Generator) -> np.ndarray:
    wave = 0.08 * np.sin(2 * np.pi * 60.0 * t)
    if not positive:
        if variant == "wrong_family_waveform":
            wave += gaussian_pulse(t, 0.023, 0.00010, 0.25)
        elif variant == "distorted_nonmatching":
            wave += 0.03 * np.sin(2 * np.pi * 120.0 * t)
        else:
            wave += 0.015 * np.sin(2 * np.pi * 1000.0 * t)
        return wave
    if "ground_loop" in signature_id:
        wave += 0.28 * np.sin(2 * np.pi * 60.0 * t + 0.6) + 0.08 * np.sin(2 * np.pi * 180.0 * t)
    elif "common_mode" in signature_id:
        wave += 0.18 * np.sin(2 * np.pi * 2400.0 * t) + 0.11 * np.sin(2 * np.pi * 4100.0 * t)
    return wave


def gaussian_pulse(t: np.ndarray, center: float, width: float, amplitude: float) -> np.ndarray:
    return amplitude * np.exp(-0.5 * ((t - center) / width) ** 2)


def burst(t: np.ndarray, center: float, duration: float, frequency: float, amplitude: float) -> np.ndarray:
    window = np.exp(-((t - center) / max(duration, 1e-6)) ** 2)
    return amplitude * window * np.sin(2 * np.pi * frequency * t)


def digital_pulse(t: np.ndarray, start: float, width: float, amplitude: float) -> np.ndarray:
    return amplitude * ((t >= start) & (t <= start + width)).astype(float)


def negative_variant(local_index: int, signature_index: int) -> str:
    variants = [
        "clean_baseline_with_noise",
        "near_miss_waveform",
        "wrong_family_waveform",
        "subthreshold_event",
        "timing_shifted_event",
        "distorted_nonmatching",
        "harmless_noise_burst",
    ]
    return variants[(local_index + signature_index) % len(variants)]


def generator_status_for(entry: dict[str, Any]) -> str:
    status = str(entry.get("status", "unknown"))
    if status in {"scaffolded", "needs_review"}:
        return "scaffold_compatible_placeholder"
    return "synthetic_signature_generator"


def generator_notes(entry: dict[str, Any], variant: str) -> str:
    return f"{entry.get('seed_id')} generated as {variant}; synthetic validation waveform, no field calibration claim"


def write_outputs(out: Path, rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    manifest_json = out / "dataset_manifest.json"
    manifest_csv = out / "dataset_manifest.csv"
    summary_json = out / "generation_summary.json"
    summary_csv = out / "generation_summary.csv"
    readme = out / "README.md"
    manifest_json.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    write_csv(manifest_csv, rows)
    summary = build_summary(rows, args)
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    write_csv(summary_csv, [summary])
    readme.write_text(build_readme(summary), encoding="utf-8")


def build_summary(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    positives = [row for row in rows if row["expected_fault_present"]]
    negatives = [row for row in rows if not row["expected_fault_present"]]
    normal = [row for row in rows if row["noise_tier"] == "normal"]
    high = [row for row in rows if row["noise_tier"] == "high"]
    return {
        "dataset_id": DATASET_ID,
        "registry": str(args.registry),
        "out": str(args.out),
        "seed": args.seed,
        "sets_per_signature": args.sets_per_signature,
        "chunks_per_set": args.chunks_per_set,
        "signature_count": len({row["signature_id"] for row in rows}),
        "total_chunks": len(rows),
        "positive_chunks": len(positives),
        "negative_chunks": len(negatives),
        "normal_noise_chunks": len(normal),
        "high_noise_chunks": len(high),
        "positive_high_noise_chunks": len([row for row in positives if row["noise_tier"] == "high"]),
        "negative_high_noise_chunks": len([row for row in negatives if row["noise_tier"] == "high"]),
        "allowed_families": sorted(ALLOWED_FAMILIES),
    }


def build_readme(summary: dict[str, Any]) -> str:
    return f"""# Gamma Massive Waveform Dataset

Synthetic electrical-observable validation dataset generated by `scripts/generate_massive_waveform_dataset.py`.

- Total chunks: {summary['total_chunks']}
- Signatures: {summary['signature_count']}
- Sets per signature: {summary['sets_per_signature']}
- Chunks per set: {summary['chunks_per_set']}
- Positive chunks: {summary['positive_chunks']}
- Negative/control chunks: {summary['negative_chunks']}
- Normal-noise chunks: {summary['normal_noise_chunks']}
- High-noise chunks: {summary['high_noise_chunks']}
- Seed: {summary['seed']}

Each set has 5 positive chunks and 5 negative/control chunks. Each set also has 3 positive normal-noise chunks, 2 positive high-noise chunks, 3 negative normal-noise chunks, and 2 negative high-noise chunks. High-noise chunks use exactly 2x the set base noise scale.

This dataset is synthetic and does not imply field calibration.
"""


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
