from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable
import argparse
import json
import math

import numpy as np
import pandas as pd

from .threshold_profiles import ThresholdProfile, load_threshold_profile
from .tuning_statistics import load_manifest_table, load_results_table, stratified_split_manifest, write_dataframe


DEFAULT_SPLIT_RATIOS = (0.60, 0.20, 0.20)
DEFAULT_CREDIBLE_INTERVAL = 0.95
DEFAULT_PRIOR_ALPHA = 1.0
DEFAULT_PRIOR_BETA = 1.0

OBJECTIVE_FILE_MAP = {
    "balanced_default": "balanced_validation.yaml",
    "fault_finding_sensitive": "fault_finding_sensitive.yaml",
    "conservative_precision": "conservative_precision.yaml",
    "field_triage": "field_triage.yaml",
}

BUILTIN_OBJECTIVES: dict[str, dict[str, Any]] = {
    "balanced_default": {
        "mode": "balanced_validation_distribution",
        "description": "Balanced validation objective that prefers posterior success, precision, recall, and specificity.",
        "weights": {
            "posterior_mean_success": 0.25,
            "posterior_lower_success": 0.20,
            "precision": 0.12,
            "recall": 0.12,
            "specificity": 0.10,
            "worst_bucket_success": 0.08,
            "high_noise_success": 0.06,
            "conflict_resistance": 0.05,
            "one_minus_false_positive_rate": 0.02,
            "one_minus_false_negative_rate": 0.02,
            "one_minus_fp_concentration_share": 0.02,
            "one_minus_high_noise_gap": 0.01,
            "one_minus_primary_stolen_rate": 0.01,
        },
        "notes": [
            "Balanced across the deliberate synthetic validation strata.",
            "Treat as development-corpus methodology, not field calibration.",
        ],
    },
    "fault_finding_sensitive": {
        "mode": "balanced_validation_distribution",
        "description": "Sensitive objective that leans toward recall while retaining acceptable precision.",
        "weights": {
            "posterior_mean_success": 0.18,
            "posterior_lower_success": 0.22,
            "precision": 0.08,
            "recall": 0.20,
            "specificity": 0.10,
            "worst_bucket_success": 0.08,
            "high_noise_success": 0.06,
            "conflict_resistance": 0.04,
            "one_minus_false_positive_rate": 0.02,
            "one_minus_false_negative_rate": 0.04,
            "one_minus_fp_concentration_share": 0.02,
            "one_minus_high_noise_gap": 0.04,
            "one_minus_primary_stolen_rate": 0.02,
        },
        "notes": [
            "Prioritizes catching useful faults over absolute conservatism.",
            "Use when missed detections are more costly than moderate false positives.",
        ],
    },
    "conservative_precision": {
        "mode": "balanced_validation_distribution",
        "description": "Conservative objective that prefers precision and low false-positive behavior.",
        "weights": {
            "posterior_mean_success": 0.16,
            "posterior_lower_success": 0.20,
            "precision": 0.24,
            "recall": 0.08,
            "specificity": 0.16,
            "worst_bucket_success": 0.08,
            "high_noise_success": 0.04,
            "conflict_resistance": 0.04,
            "one_minus_false_positive_rate": 0.04,
            "one_minus_false_negative_rate": 0.02,
            "one_minus_fp_concentration_share": 0.02,
            "one_minus_high_noise_gap": 0.01,
            "one_minus_primary_stolen_rate": 0.01,
        },
        "notes": [
            "Use when false positives are expensive and confidence needs to stay disciplined.",
            "Recall still matters, but the floor is secondary to precision and specificity.",
        ],
    },
    "field_triage": {
        "mode": "field_weighted_distribution",
        "description": "Operational triage objective that rewards F1 while penalizing conflicts and concentrated false positives.",
        "weights": {
            "posterior_mean_success": 0.14,
            "posterior_lower_success": 0.16,
            "precision": 0.15,
            "recall": 0.15,
            "specificity": 0.08,
            "worst_bucket_success": 0.06,
            "high_noise_success": 0.05,
            "conflict_resistance": 0.05,
            "one_minus_false_positive_rate": 0.04,
            "one_minus_false_negative_rate": 0.04,
            "one_minus_fp_concentration_share": 0.06,
            "one_minus_high_noise_gap": 0.01,
            "one_minus_primary_stolen_rate": 0.01,
        },
        "notes": [
            "Field-weighted objective that treats ambiguity and repeated false positives as operational costs.",
            "The beta posterior is still synthetic-corpus evidence, not field calibration.",
        ],
    },
}


@dataclass(frozen=True)
class ObjectiveProfile:
    name: str
    mode: str
    description: str
    weights: dict[str, float]
    notes: list[str]
    source_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode,
            "description": self.description,
            "weights": dict(self.weights),
            "notes": list(self.notes),
            "source_path": self.source_path,
        }


def load_objective_profile(path_or_name: str | Path | None) -> ObjectiveProfile:
    if path_or_name is None:
        name = "balanced_default"
        data = dict(BUILTIN_OBJECTIVES[name])
        return ObjectiveProfile(
            name=name,
            mode=str(data.get("mode", "balanced_validation_distribution")),
            description=str(data.get("description", "")),
            weights={str(k): float(v) for k, v in dict(data.get("weights", {})).items()},
            notes=[str(item) for item in data.get("notes", [])],
            source_path=None,
        )

    candidate = Path(path_or_name)
    if candidate.exists():
        data = _load_mapping(candidate)
        return _objective_from_mapping(data, source_path=str(candidate))

    name = str(path_or_name)
    mapped = OBJECTIVE_FILE_MAP.get(name)
    if mapped:
        config_path = Path("configs") / "power_objectives" / mapped
        if config_path.exists():
            data = _load_mapping(config_path)
            return _objective_from_mapping(data, source_path=str(config_path))

    if name in BUILTIN_OBJECTIVES:
        data = dict(BUILTIN_OBJECTIVES[name])
        return ObjectiveProfile(
            name=name,
            mode=str(data.get("mode", "balanced_validation_distribution")),
            description=str(data.get("description", "")),
            weights={str(k): float(v) for k, v in dict(data.get("weights", {})).items()},
            notes=[str(item) for item in data.get("notes", [])],
            source_path=None,
        )

    raise FileNotFoundError(f"objective profile not found: {path_or_name}")


def _objective_from_mapping(data: dict[str, Any], *, source_path: str | None) -> ObjectiveProfile:
    weights = data.get("weights", data.get("components", {}))
    if not isinstance(weights, dict):
        raise ValueError("objective profile weights must be a mapping")
    return ObjectiveProfile(
        name=str(data.get("name", Path(source_path).stem if source_path else "unknown")),
        mode=str(data.get("mode", "balanced_validation_distribution")),
        description=str(data.get("description", "")),
        weights={str(k): float(v) for k, v in weights.items()},
        notes=[str(item) for item in list(data.get("notes", []))],
        source_path=source_path,
    )


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        return dict(json.loads(text))
    try:
        import yaml  # type: ignore

        return dict(yaml.safe_load(text) or {})
    except Exception:
        return _parse_objective_yaml_subset(text)


def _parse_objective_yaml_subset(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_map: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith(":") and not line.startswith("  "):
            current_map = stripped[:-1]
            if current_map not in data:
                data[current_map] = {}
            continue
        if current_map and line.startswith("  ") and ":" in line:
            key, raw = line.split(":", 1)
            key = key.strip()
            value = raw.strip()
            if value.startswith("[") and value.endswith("]"):
                data[current_map][key] = [item.strip().strip('"').strip("'") for item in value[1:-1].split(",") if item.strip()]
            elif value.lower() in {"true", "false"}:
                data[current_map][key] = value.lower() == "true"
            else:
                try:
                    data[current_map][key] = float(value) if "." in value else int(value)
                except Exception:
                    data[current_map][key] = value.strip('"').strip("'")
            continue
        if ":" in line:
            key, raw = line.split(":", 1)
            key = key.strip()
            value = raw.strip()
            if value.startswith("[") and value.endswith("]"):
                data[key] = [item.strip().strip('"').strip("'") for item in value[1:-1].split(",") if item.strip()]
            elif value.lower() in {"true", "false"}:
                data[key] = value.lower() == "true"
            elif value:
                try:
                    data[key] = float(value) if "." in value else int(value)
                except Exception:
                    data[key] = value.strip('"').strip("'")
            else:
                data[key] = {}
                current_map = key
    return data


def beta_posterior(successes: int, failures: int, *, prior_alpha: float = DEFAULT_PRIOR_ALPHA, prior_beta: float = DEFAULT_PRIOR_BETA) -> tuple[float, float, float]:
    alpha = float(successes) + float(prior_alpha)
    beta = float(failures) + float(prior_beta)
    mean = alpha / (alpha + beta)
    return alpha, beta, mean


def beta_credible_interval(
    alpha: float,
    beta: float,
    *,
    credible_interval: float = DEFAULT_CREDIBLE_INTERVAL,
) -> tuple[float, float]:
    tail = (1.0 - float(credible_interval)) / 2.0
    try:
        from scipy.stats import beta as beta_dist  # type: ignore

        low = float(beta_dist.ppf(tail, alpha, beta))
        high = float(beta_dist.ppf(1.0 - tail, alpha, beta))
        return _clamp01(low), _clamp01(high)
    except Exception:
        mean = alpha / (alpha + beta)
        variance = (alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1.0))
        std = math.sqrt(max(0.0, variance))
        z = NormalDist().inv_cdf(1.0 - tail) if tail > 0 else 0.0
        low = mean - z * std
        high = mean + z * std
        return _clamp01(low), _clamp01(high)


def analyze_analyzer_power(
    *,
    manifest_path: str | Path,
    results_path: str | Path,
    threshold_profile_path: str | Path | None,
    out_dir: str | Path,
    objective: str | Path | None = "balanced_default",
    split_manifest_path: str | Path | None = None,
    split_seed: int = 1337,
    split_ratios: tuple[float, float, float] = DEFAULT_SPLIT_RATIOS,
    prior_alpha: float = DEFAULT_PRIOR_ALPHA,
    prior_beta: float = DEFAULT_PRIOR_BETA,
    credible_interval: float = DEFAULT_CREDIBLE_INTERVAL,
    bootstrap: int = 0,
    threshold_sweep_path: str | Path | None = None,
) -> dict[str, Any]:
    manifest = load_manifest_table(manifest_path)
    results = load_results_table(results_path)
    threshold_profile = _load_threshold_profile(threshold_profile_path)
    objective_profile = load_objective_profile(objective)
    split_frame = _load_or_build_splits(
        manifest,
        split_manifest_path=split_manifest_path,
        split_seed=split_seed,
        split_ratios=split_ratios,
    )
    case_rows = _build_case_rows(split_frame, results, threshold_profile)

    analyzer_success_rows = _build_success_distribution_rows(
        case_rows,
        objective_profile,
        prior_alpha=prior_alpha,
        prior_beta=prior_beta,
        credible_interval=credible_interval,
    )
    ranking_rows = _build_ranking_rows(
        analyzer_success_rows,
        objective_profile,
    )
    bucket_rows = _build_bucket_rows(analyzer_success_rows)
    noise_rows = _build_noise_rows(case_rows, analyzer_success_rows)
    conflict_rows = _build_conflict_rows(case_rows)
    fp_rows = _build_false_positive_concentration_rows(case_rows, analyzer_success_rows)
    worst_rows = _build_worst_bucket_rows(analyzer_success_rows)
    status_rows = _build_status_rows(ranking_rows)
    threshold_robustness_rows = _build_threshold_robustness_rows(threshold_sweep_path, ranking_rows)
    bootstrap_rows = _build_bootstrap_rows(case_rows, objective_profile, bootstrap, credible_interval) if bootstrap > 0 else []

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    write_dataframe(out_path / "analyzer_success_distribution.csv", analyzer_success_rows)
    write_dataframe(out_path / "analyzer_power_ranking.csv", ranking_rows)
    write_dataframe(out_path / "analyzer_bucket_metrics.csv", bucket_rows)
    write_dataframe(out_path / "analyzer_noise_stability.csv", noise_rows)
    write_dataframe(out_path / "analyzer_conflict_resistance.csv", conflict_rows)
    write_dataframe(out_path / "analyzer_false_positive_concentration.csv", fp_rows)
    write_dataframe(out_path / "analyzer_worst_buckets.csv", worst_rows)
    write_dataframe(out_path / "analyzer_recommended_status.csv", status_rows)
    if threshold_robustness_rows:
        write_dataframe(out_path / "threshold_robustness.csv", threshold_robustness_rows)
    if bootstrap_rows:
        write_dataframe(out_path / "analyzer_power_bootstrap.csv", bootstrap_rows)

    analyzer_success_json = _safe_json(analyzer_success_rows)
    ranking_json = _safe_json(ranking_rows)
    bucket_json = _safe_json(bucket_rows)
    noise_json = _safe_json(noise_rows)
    conflict_json = _safe_json(conflict_rows)
    fp_json = _safe_json(fp_rows)
    worst_json = _safe_json(worst_rows)
    status_json = _safe_json(status_rows)
    threshold_robustness_json = _safe_json(threshold_robustness_rows)
    bootstrap_json = _safe_json(bootstrap_rows)

    (out_path / "analyzer_success_distribution.json").write_text(json.dumps(analyzer_success_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_path / "analyzer_power_ranking.json").write_text(json.dumps(ranking_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_path / "analyzer_bucket_metrics.json").write_text(json.dumps(bucket_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_path / "analyzer_noise_stability.json").write_text(json.dumps(noise_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_path / "analyzer_conflict_resistance.json").write_text(json.dumps(conflict_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_path / "analyzer_false_positive_concentration.json").write_text(json.dumps(fp_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_path / "analyzer_worst_buckets.json").write_text(json.dumps(worst_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_path / "analyzer_recommended_status.json").write_text(json.dumps(status_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if threshold_robustness_rows:
        (out_path / "threshold_robustness.json").write_text(json.dumps(threshold_robustness_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if bootstrap_rows:
        (out_path / "analyzer_power_bootstrap.json").write_text(json.dumps(bootstrap_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    objective_weights = objective_profile.to_dict()
    (out_path / "objective_weights.json").write_text(json.dumps(objective_weights, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    power_summary = _build_power_summary(
        ranking_rows=ranking_rows,
        conflict_rows=conflict_rows,
        fp_rows=fp_rows,
        worst_rows=worst_rows,
        objective_profile=objective_profile,
        threshold_profile=threshold_profile,
        threshold_robustness_rows=threshold_robustness_rows,
        bootstrap_rows=bootstrap_rows,
        split_seed=split_seed,
        split_ratios=split_ratios,
        credible_interval=credible_interval,
        prior_alpha=prior_alpha,
        prior_beta=prior_beta,
        manifest=split_frame,
    )
    (out_path / "power_summary.json").write_text(json.dumps(power_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_path / "README.md").write_text(
        _build_readme(
            power_summary=power_summary,
            objective_profile=objective_profile,
            threshold_profile=threshold_profile,
            split_seed=split_seed,
            split_ratios=split_ratios,
            credible_interval=credible_interval,
            bootstrap=bootstrap,
        ),
        encoding="utf-8",
    )

    return {
        "analyzer_success_distribution_csv": out_path / "analyzer_success_distribution.csv",
        "analyzer_power_ranking_csv": out_path / "analyzer_power_ranking.csv",
        "analyzer_bucket_metrics_csv": out_path / "analyzer_bucket_metrics.csv",
        "analyzer_noise_stability_csv": out_path / "analyzer_noise_stability.csv",
        "analyzer_conflict_resistance_csv": out_path / "analyzer_conflict_resistance.csv",
        "analyzer_false_positive_concentration_csv": out_path / "analyzer_false_positive_concentration.csv",
        "analyzer_worst_buckets_csv": out_path / "analyzer_worst_buckets.csv",
        "analyzer_recommended_status_csv": out_path / "analyzer_recommended_status.csv",
        "objective_weights_json": out_path / "objective_weights.json",
        "power_summary_json": out_path / "power_summary.json",
        "README": out_path / "README.md",
    }


def _load_threshold_profile(path: str | Path | None) -> ThresholdProfile:
    if path is None:
        return ThresholdProfile()
    return load_threshold_profile(path)


def _load_or_build_splits(
    manifest: pd.DataFrame,
    *,
    split_manifest_path: str | Path | None,
    split_seed: int,
    split_ratios: tuple[float, float, float],
) -> pd.DataFrame:
    frame = manifest.copy()
    if split_manifest_path:
        split_frame = pd.read_csv(split_manifest_path, keep_default_na=False)
        if "capture_id" not in split_frame.columns:
            raise ValueError("split manifest must include capture_id")
        if "split" not in split_frame.columns:
            raise ValueError("split manifest must include split")
        merge_cols = [col for col in split_frame.columns if col != "capture_id"]
        split_frame = split_frame[["capture_id", *merge_cols]].drop_duplicates("capture_id")
        merged = frame.merge(split_frame, on="capture_id", how="left", suffixes=("", "_split"))
        if "split_split" in merged.columns:
            merged["split"] = merged["split_split"].where(merged["split_split"].astype(str) != "", merged.get("split", "overall"))
            merged = merged.drop(columns=["split_split"])
        if "split_purpose_split" in merged.columns:
            merged["split_purpose"] = merged["split_purpose_split"].where(
                merged["split_purpose_split"].astype(str) != "",
                merged.get("split_purpose", ""),
            )
            merged = merged.drop(columns=["split_purpose_split"])
        if "split_bucket_split" in merged.columns:
            merged["split_bucket"] = merged["split_bucket_split"].where(
                merged["split_bucket_split"].astype(str) != "",
                merged.get("split_bucket", ""),
            )
            merged = merged.drop(columns=["split_bucket_split"])
    elif "split" not in frame.columns:
        merged = stratified_split_manifest(frame, seed=split_seed, ratios=split_ratios)
    else:
        merged = frame

    if "split" not in merged.columns:
        merged["split"] = "overall"
    if "split_purpose" not in merged.columns:
        merged["split_purpose"] = merged["split"].map(
            lambda value: {"train": "tune/dev", "dev": "validation/model-selection", "test": "locked_test"}.get(str(value), "overall")
        )
    if "split_bucket" not in merged.columns:
        merged["split_bucket"] = ""
    return merged


def _build_case_rows(
    manifest: pd.DataFrame,
    results: pd.DataFrame,
    threshold_profile: ThresholdProfile,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    results_by_capture = {str(capture_id): group.copy() for capture_id, group in results.groupby("capture_id", sort=False)}
    for row in manifest.itertuples(index=False):
        manifest_row = row._asdict()
        capture_id = str(manifest_row["capture_id"])
        capture_results = results_by_capture.get(capture_id, pd.DataFrame())
        rows.append(_build_case_row(manifest_row, capture_results, threshold_profile))
    return rows


def _build_case_row(
    manifest_row: dict[str, Any],
    capture_rows: pd.DataFrame,
    threshold_profile: ThresholdProfile,
) -> dict[str, Any]:
    capture_id = str(manifest_row["capture_id"])
    expected_signature = str(manifest_row["signature_id"])
    expected_family = str(manifest_row["family"])
    truth_label = str(manifest_row["truth_label"])
    expected_fault_present = _to_bool(manifest_row["expected_fault_present"])
    noise_tier = str(manifest_row.get("noise_tier", "unknown"))
    waveform_intent = str(manifest_row.get("waveform_intent", manifest_row.get("variant", truth_label)))
    test_id = str(manifest_row.get("test_id", capture_id))
    split = str(manifest_row.get("split", "overall"))
    split_purpose = str(manifest_row.get("split_purpose", "overall"))
    split_bucket = str(manifest_row.get("split_bucket", ""))
    target_rule_or_feature = str(manifest_row.get("target_rule_or_feature", expected_signature))
    channel_names = manifest_row.get("channel_names", "")

    candidate_rows = _build_candidate_rows(capture_rows, threshold_profile)
    primary_row = _choose_primary_row(candidate_rows)
    expected_row = next((candidate for candidate in candidate_rows if candidate["signature_id"] == expected_signature), None)

    primary_signature = primary_row["signature_id"] if primary_row else ""
    primary_confidence = float(primary_row["confidence"]) if primary_row else 0.0
    expected_confidence = float(expected_row["confidence"]) if expected_row else 0.0
    expected_threshold = float(expected_row["threshold"]) if expected_row else float(threshold_profile.threshold_for(expected_signature))
    selected_threshold = float(primary_row["threshold"]) if primary_row else expected_threshold

    top_candidates = candidate_rows[:3]
    top_competing_signatures = " | ".join(f"{row['signature_id']}@{row['confidence']}" for row in top_candidates)
    conflict_warning = _conflict_warning(candidate_rows)
    required_reference_status = expected_row["required_reference_status"] if expected_row else "missing_or_not_reported"
    reference_status = required_reference_status

    if expected_fault_present:
        if primary_signature == expected_signature:
            conflict_state = "positive_expected_won_primary"
        elif primary_signature:
            conflict_state = "positive_expected_lost_primary"
        else:
            conflict_state = "positive_expected_no_match"
    else:
        if primary_signature == expected_signature:
            conflict_state = "negative_false_positive"
        elif primary_signature:
            conflict_state = "negative_avoided_primary"
        else:
            conflict_state = "negative_no_match"
    if primary_row and primary_row["multi_match_ambiguity"]:
        conflict_state += "_ambiguous"

    success = (expected_fault_present and primary_signature == expected_signature) or ((not expected_fault_present) and primary_signature != expected_signature)
    false_positive = (not expected_fault_present) and primary_signature == expected_signature
    false_negative = expected_fault_present and primary_signature != expected_signature
    primary_stolen = expected_fault_present and primary_signature not in {"", expected_signature}

    warnings = []
    if expected_row and expected_row["reference_score"] <= 0.0:
        warnings.append("required_reference_evidence_missing_or_weak")
    if conflict_warning:
        warnings.append(conflict_warning)
    if not candidate_rows:
        warnings.append("no_analyzer_candidates_available")

    return {
        "capture_id": capture_id,
        "test_id": test_id,
        "analyzer_id": expected_signature,
        "signature_id": expected_signature,
        "family": expected_family,
        "truth_label": truth_label,
        "expected_fault_present": expected_fault_present,
        "expected_decision": "select_primary" if expected_fault_present else "avoid_primary",
        "split": split,
        "split_purpose": split_purpose,
        "split_bucket": split_bucket,
        "noise_tier": noise_tier,
        "waveform_intent": waveform_intent,
        "target_rule_or_feature": target_rule_or_feature,
        "reference_status": reference_status,
        "channel_names": channel_names,
        "predicted_primary_signature": primary_signature,
        "predicted_primary_confidence": primary_confidence,
        "expected_analyzer_confidence": expected_confidence,
        "threshold_used": selected_threshold,
        "threshold_profile": threshold_profile.name,
        "decision_reason": _decision_reason(expected_fault_present, expected_signature, primary_signature, primary_row),
        "warning": " | ".join(warnings),
        "conflict_warning": conflict_warning,
        "conflict_state": conflict_state,
        "multi_match_count": len([row for row in candidate_rows if row["threshold_pass"]]),
        "multi_match_ambiguity": bool(primary_row and primary_row["multi_match_ambiguity"]),
        "top_3_competing_signatures": top_competing_signatures,
        "selected_primary_confidence": primary_confidence,
        "selected_primary_warning": str(primary_row["warning"]) if primary_row else "",
        "selected_primary_conflict_warning": str(primary_row["conflict_warning"]) if primary_row else "",
        "is_correct": success,
        "is_false_positive": false_positive,
        "is_false_negative": false_negative,
        "primary_stolen": primary_stolen,
        "primary_diagnosis": primary_signature,
        "secondary_candidates": ",".join(row["signature_id"] for row in candidate_rows[1:]),
        "selected_primary_signature": primary_signature or expected_signature,
    }


def _build_candidate_rows(capture_rows: pd.DataFrame, threshold_profile: ThresholdProfile) -> list[dict[str, Any]]:
    candidate_rows: list[dict[str, Any]] = []
    for _, result in capture_rows.iterrows():
        sig_id = str(result["signature_id"])
        threshold = float(result.get("threshold", threshold_profile.threshold_for(sig_id)))
        confidence = float(result.get("confidence", 0.0))
        matched = _to_bool(result.get("raw_matched", result.get("matched", True)))
        threshold_pass = _to_bool(result.get("threshold_pass", matched and confidence >= threshold))
        reference_score = float(result.get("reference_evidence_score", 1.0))
        diagnostic_score = float(
            result.get(
                "diagnostic_score",
                max(0.0, min(1.0, confidence * (0.70 + 0.30 * reference_score) + (0.05 if threshold_pass else 0.0))),
            )
        )
        candidate_rows.append(
            {
                "signature_id": sig_id,
                "confidence": confidence,
                "threshold": threshold,
                "threshold_pass": bool(threshold_pass and reference_score > 0.0),
                "reference_score": reference_score,
                "reference_status": str(result.get("required_reference_status", "")),
                "rank": int(result.get("rank", 0)),
                "diagnostic_score": diagnostic_score,
                "raw_matched": matched,
                "warning": str(result.get("warnings", "")),
                "conflict_warning": str(result.get("conflict_warning", "")),
                "multi_match_ambiguity": _to_bool(result.get("multi_match_ambiguity", False)),
                "required_reference_status": str(result.get("required_reference_status", "missing_or_not_reported")),
            }
        )
    candidate_rows.sort(
        key=lambda item: (
            item["threshold_pass"],
            item["diagnostic_score"],
            item["confidence"],
            item["reference_score"],
            -item["rank"],
        ),
        reverse=True,
    )
    return candidate_rows


def _choose_primary_row(candidate_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidate_rows:
        return None
    threshold_rows = [row for row in candidate_rows if row["threshold_pass"]]
    if threshold_rows:
        return threshold_rows[0]
    selected = sorted(
        candidate_rows,
        key=lambda item: (item["confidence"], item["reference_score"], -item["rank"]),
        reverse=True,
    )
    return selected[0]


def _decision_reason(expected_fault_present: bool, expected_signature: str, primary_signature: str, primary_row: dict[str, Any] | None) -> str:
    if primary_row is None:
        return "rejected_or_below_threshold"
    if expected_fault_present and primary_signature == expected_signature:
        return "primary_diagnosis"
    if (not expected_fault_present) and primary_signature != expected_signature:
        return "correct_rejection"
    return "primary_diagnosis_conflict"


def _build_success_distribution_rows(
    case_rows: list[dict[str, Any]],
    objective_profile: ObjectiveProfile,
    *,
    prior_alpha: float,
    prior_beta: float,
    credible_interval: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    bucket_specs = [
        ("overall", None),
        ("family", "family"),
        ("split", "split"),
        ("noise_tier", "noise_tier"),
        ("waveform_intent", "waveform_intent"),
        ("test_id", "test_id"),
        ("truth_label", "truth_label"),
        ("reference_status", "reference_status"),
        ("conflict_state", "conflict_state"),
        ("target_rule_or_feature", "target_rule_or_feature"),
    ]
    for analyzer_id, analyzer_rows in _group_by(case_rows, "analyzer_id").items():
        analyzer_family = str(analyzer_rows[0]["family"]) if analyzer_rows else "unknown"
        for bucket_type, column in bucket_specs:
            if column is None:
                rows.append(_summarize_analyzer_bucket(
                    analyzer_rows,
                    analyzer_id=analyzer_id,
                    family=analyzer_family,
                    bucket_type=bucket_type,
                    bucket_value="all",
                    objective_profile=objective_profile,
                    prior_alpha=prior_alpha,
                    prior_beta=prior_beta,
                    credible_interval=credible_interval,
                ))
                continue
            for bucket_value, subset in sorted(_group_by(analyzer_rows, column).items()):
                rows.append(_summarize_analyzer_bucket(
                    subset,
                    analyzer_id=analyzer_id,
                    family=analyzer_family,
                    bucket_type=bucket_type,
                    bucket_value=bucket_value,
                    objective_profile=objective_profile,
                    prior_alpha=prior_alpha,
                    prior_beta=prior_beta,
                    credible_interval=credible_interval,
                ))
    return rows


def _summarize_analyzer_bucket(
    rows: list[dict[str, Any]],
    *,
    analyzer_id: str,
    family: str,
    bucket_type: str,
    bucket_value: str,
    objective_profile: ObjectiveProfile,
    prior_alpha: float,
    prior_beta: float,
    credible_interval: float,
) -> dict[str, Any]:
    n_cases = len(rows)
    successes = sum(1 for row in rows if row["is_correct"])
    failures = n_cases - successes
    alpha, beta, posterior_mean = beta_posterior(successes, failures, prior_alpha=prior_alpha, prior_beta=prior_beta)
    credible_low, credible_high = beta_credible_interval(alpha, beta, credible_interval=credible_interval)
    metrics = _compute_case_metrics(rows)
    high_noise_rows = [row for row in rows if row["noise_tier"] == "high"]
    normal_noise_rows = [row for row in rows if row["noise_tier"] == "normal"]
    high_noise_success = _success_rate(high_noise_rows)
    normal_noise_success = _success_rate(normal_noise_rows)
    high_noise_delta = high_noise_success - normal_noise_success if high_noise_rows or normal_noise_rows else 0.0
    conflict_rows = [row for row in rows if _is_conflict_case(row)]
    conflict_resistance = _success_rate(conflict_rows) if conflict_rows else 1.0
    primary_stolen_rate = _safe_div(sum(1 for row in rows if row["primary_stolen"]), n_cases)
    fp_cases = [row for row in rows if row["is_false_positive"]]
    fp_concentration_share = _top_concentration_share(fp_cases)
    worst_bucket_success = _worst_bucket_success(rows)
    power_score = _objective_score_from_metrics(
        {
            "posterior_mean_success": posterior_mean,
            "posterior_lower_success": credible_low,
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "specificity": metrics["specificity"],
            "high_noise_success": high_noise_success,
            "normal_noise_success": normal_noise_success,
            "worst_bucket_success": worst_bucket_success,
            "conflict_resistance": conflict_resistance,
            "one_minus_false_positive_rate": 1.0 - metrics["false_positive_rate"],
            "one_minus_false_negative_rate": 1.0 - metrics["false_negative_rate"],
            "one_minus_fp_concentration_share": 1.0 - fp_concentration_share,
            "one_minus_high_noise_gap": 1.0 - abs(high_noise_delta),
            "one_minus_primary_stolen_rate": 1.0 - primary_stolen_rate,
        },
        objective_profile,
    )
    return {
        "analyzer_id": analyzer_id,
        "signature_id": analyzer_id,
        "family": family,
        "condition_bucket": bucket_type,
        "bucket_value": bucket_value,
        "split": bucket_value if bucket_type == "split" else "all",
        "truth_label": bucket_value if bucket_type == "truth_label" else "all",
        "noise_tier": bucket_value if bucket_type == "noise_tier" else "all",
        "waveform_intent": bucket_value if bucket_type == "waveform_intent" else "all",
        "test_id": bucket_value if bucket_type == "test_id" else "all",
        "reference_status": bucket_value if bucket_type == "reference_status" else "all",
        "conflict_state": bucket_value if bucket_type == "conflict_state" else "all",
        "target_rule_or_feature": bucket_value if bucket_type == "target_rule_or_feature" else "all",
        "n_cases": n_cases,
        "successes": successes,
        "failures": failures,
        "success_rate": _success_rate(rows),
        "posterior_alpha": alpha,
        "posterior_beta": beta,
        "posterior_mean": posterior_mean,
        "credible_low": credible_low,
        "credible_high": credible_high,
        "credible_width": credible_high - credible_low,
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "specificity": metrics["specificity"],
        "false_positive_rate": metrics["false_positive_rate"],
        "false_negative_rate": metrics["false_negative_rate"],
        "conflict_rate": metrics["conflict_rate"],
        "primary_stolen_rate": primary_stolen_rate,
        "high_noise_success": high_noise_success,
        "normal_noise_success": normal_noise_success,
        "high_noise_delta": high_noise_delta,
        "worst_bucket_success": worst_bucket_success,
        "fp_concentration_share": fp_concentration_share,
        "power_score": power_score,
        "objective_name": objective_profile.name,
    }


def _build_ranking_rows(success_rows: list[dict[str, Any]], objective_profile: ObjectiveProfile) -> list[dict[str, Any]]:
    overall_rows = [row for row in success_rows if row["condition_bucket"] == "overall"]
    rows: list[dict[str, Any]] = []
    for row in overall_rows:
        lower_bound_power = _objective_score_from_metrics(
            {
                "posterior_mean_success": row["credible_low"],
                "posterior_lower_success": row["credible_low"],
                "precision": row["precision"],
                "recall": row["recall"],
                "specificity": row["specificity"],
                "high_noise_success": row["high_noise_success"],
                "normal_noise_success": row["normal_noise_success"],
                "worst_bucket_success": row["worst_bucket_success"],
                "conflict_resistance": 1.0 - row["conflict_rate"],
                "one_minus_false_positive_rate": 1.0 - row["false_positive_rate"],
                "one_minus_false_negative_rate": 1.0 - row["false_negative_rate"],
                "one_minus_fp_concentration_share": 1.0 - row["fp_concentration_share"],
                "one_minus_high_noise_gap": 1.0 - abs(row["high_noise_delta"]),
                "one_minus_primary_stolen_rate": 1.0 - row["primary_stolen_rate"],
            },
            objective_profile,
        )
        rows.append(
            {
                "analyzer_id": row["analyzer_id"],
                "signature_id": row["signature_id"],
                "family": row["family"],
                "objective_name": objective_profile.name,
                "mean_power": row["power_score"],
                "lower_bound_power": lower_bound_power,
                "posterior_mean_success": row["posterior_mean"],
                "posterior_lower_success": row["credible_low"],
                "worst_bucket_success": row["worst_bucket_success"],
                "high_noise_success": row["high_noise_success"],
                "normal_noise_success": row["normal_noise_success"],
                "high_noise_delta": row["high_noise_delta"],
                "conflict_resistance": 1.0 - row["conflict_rate"],
                "false_positive_rate": row["false_positive_rate"],
                "false_negative_rate": row["false_negative_rate"],
                "fp_concentration_share": row["fp_concentration_share"],
                "primary_stolen_rate": row["primary_stolen_rate"],
                "recommended_status": _recommended_status(row, lower_bound_power=lower_bound_power),
                "recommended_action": _recommended_action(_recommended_status(row, lower_bound_power=lower_bound_power)),
            }
        )
    rows.sort(key=lambda item: (item["mean_power"], item["lower_bound_power"], item["posterior_mean_success"]), reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def _build_bucket_rows(success_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in success_rows:
        rows.append(
            {
                "analyzer_id": row["analyzer_id"],
                "signature_id": row["signature_id"],
                "family": row["family"],
                "condition_bucket": row["condition_bucket"],
                "bucket_value": row["bucket_value"],
                "n_cases": row["n_cases"],
                "success_rate": row["success_rate"],
                "posterior_mean": row["posterior_mean"],
                "credible_low": row["credible_low"],
                "credible_high": row["credible_high"],
                "credible_width": row["credible_width"],
                "precision": row["precision"],
                "recall": row["recall"],
                "specificity": row["specificity"],
                "false_positive_rate": row["false_positive_rate"],
                "false_negative_rate": row["false_negative_rate"],
                "conflict_rate": row["conflict_rate"],
                "power_score": row["power_score"],
                "objective_name": row["objective_name"],
            }
        )
    return rows


def _build_noise_rows(case_rows: list[dict[str, Any]], success_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for analyzer_id, analyzer_case_rows in _group_by(case_rows, "analyzer_id").items():
        analyzer_rows = [row for row in success_rows if row["analyzer_id"] == analyzer_id]
        overall = next((row for row in analyzer_rows if row["condition_bucket"] == "overall"), analyzer_rows[0])
        rows.append(
            {
                "analyzer_id": analyzer_id,
                "signature_id": overall["signature_id"],
                "family": overall["family"],
                "normal_noise_success": overall["normal_noise_success"],
                "high_noise_success": overall["high_noise_success"],
                "high_noise_delta": overall["high_noise_delta"],
                "noise_stability_score": 1.0 - abs(overall["high_noise_delta"]),
                "normal_noise_cases": _bucket_case_count(analyzer_case_rows, "noise_tier", "normal"),
                "high_noise_cases": _bucket_case_count(analyzer_case_rows, "noise_tier", "high"),
                "objective_name": overall["objective_name"],
            }
        )
    rows.sort(key=lambda item: (item["noise_stability_score"], item["high_noise_success"]), reverse=True)
    return rows


def _build_conflict_rows(case_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for analyzer_id, analyzer_rows in _group_by(case_rows, "analyzer_id").items():
        conflict_rows = [row for row in analyzer_rows if _is_conflict_case(row)]
        conflict_cases = len(conflict_rows)
        conflict_successes = sum(1 for row in conflict_rows if row["is_correct"])
        primary_stolen_cases = sum(1 for row in analyzer_rows if row["primary_stolen"])
        rows.append(
            {
                "analyzer_id": analyzer_id,
                "signature_id": analyzer_rows[0]["signature_id"],
                "family": analyzer_rows[0]["family"],
                "conflict_cases": conflict_cases,
                "conflict_successes": conflict_successes,
                "conflict_resistance": _success_rate(conflict_rows) if conflict_rows else 1.0,
                "primary_stolen_cases": primary_stolen_cases,
                "primary_stolen_rate": _safe_div(primary_stolen_cases, len(analyzer_rows)),
                "multi_match_ambiguity_cases": sum(1 for row in analyzer_rows if row["multi_match_ambiguity"]),
                "conflict_rate": _safe_div(conflict_cases, len(analyzer_rows)),
            }
        )
    rows.sort(key=lambda item: (item["conflict_resistance"], -item["primary_stolen_rate"]), reverse=True)
    return rows


def _build_false_positive_concentration_rows(case_rows: list[dict[str, Any]], success_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for analyzer_id, analyzer_rows in _group_by(case_rows, "analyzer_id").items():
        fp_rows = [row for row in analyzer_rows if row["is_false_positive"]]
        total_fp = len(fp_rows)
        if not fp_rows:
            rows.append(
                {
                    "analyzer_id": analyzer_id,
                    "signature_id": analyzer_rows[0]["signature_id"],
                    "family": analyzer_rows[0]["family"],
                    "false_positive_cases": 0,
                    "fp_concentration_share": 0.0,
                    "top_fp_bucket_type": "",
                    "top_fp_bucket_value": "",
                    "top_fp_count": 0,
                    "objective_name": next(row["objective_name"] for row in success_rows if row["analyzer_id"] == analyzer_id and row["condition_bucket"] == "overall"),
                }
            )
            continue

        bucket_candidates: list[tuple[str, str, int]] = []
        for bucket_type, column in [
            ("split", "split"),
            ("noise_tier", "noise_tier"),
            ("waveform_intent", "waveform_intent"),
            ("test_id", "test_id"),
            ("conflict_state", "conflict_state"),
        ]:
            for bucket_value, subset in _group_by(fp_rows, column).items():
                bucket_candidates.append((bucket_type, bucket_value, len(subset)))
        bucket_candidates.sort(key=lambda item: (item[2], item[0], item[1]), reverse=True)
        top_type, top_value, top_count = bucket_candidates[0]
        rows.append(
            {
                "analyzer_id": analyzer_id,
                "signature_id": analyzer_rows[0]["signature_id"],
                "family": analyzer_rows[0]["family"],
                "false_positive_cases": total_fp,
                "fp_concentration_share": _safe_div(top_count, total_fp),
                "top_fp_bucket_type": top_type,
                "top_fp_bucket_value": top_value,
                "top_fp_count": top_count,
                "objective_name": next(row["objective_name"] for row in success_rows if row["analyzer_id"] == analyzer_id and row["condition_bucket"] == "overall"),
            }
        )
    rows.sort(key=lambda item: (item["fp_concentration_share"], item["false_positive_cases"]), reverse=True)
    return rows


def _build_worst_bucket_rows(success_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for analyzer_id, analyzer_rows in _group_by(success_rows, "analyzer_id").items():
        candidate_rows = [row for row in analyzer_rows if row["condition_bucket"] != "overall" and row["n_cases"] > 0]
        worst = min(candidate_rows, key=lambda item: (item["success_rate"], item["credible_low"], -item["n_cases"])) if candidate_rows else next(row for row in analyzer_rows if row["condition_bucket"] == "overall")
        rows.append(
            {
                "analyzer_id": analyzer_id,
                "signature_id": worst["signature_id"],
                "family": worst["family"],
                "bucket_type": worst["condition_bucket"],
                "bucket_value": worst["bucket_value"],
                "n_cases": worst["n_cases"],
                "success_rate": worst["success_rate"],
                "credible_low": worst["credible_low"],
                "credible_high": worst["credible_high"],
                "power_score": worst["power_score"],
                "objective_name": worst["objective_name"],
            }
        )
    rows.sort(key=lambda item: (item["success_rate"], item["credible_low"]), reverse=False)
    return rows


def _build_status_rows(ranking_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in ranking_rows:
        rows.append(
            {
                "rank": row["rank"],
                "analyzer_id": row["analyzer_id"],
                "signature_id": row["signature_id"],
                "family": row["family"],
                "objective_name": row["objective_name"],
                "recommended_status": row["recommended_status"],
                "recommended_action": row["recommended_action"],
                "mean_power": row["mean_power"],
                "lower_bound_power": row["lower_bound_power"],
                "posterior_mean_success": row["posterior_mean_success"],
                "posterior_lower_success": row["posterior_lower_success"],
                "worst_bucket_success": row["worst_bucket_success"],
                "high_noise_success": row["high_noise_success"],
                "normal_noise_success": row["normal_noise_success"],
                "high_noise_delta": row["high_noise_delta"],
                "conflict_resistance": row["conflict_resistance"],
                "false_positive_rate": row["false_positive_rate"],
                "false_negative_rate": row["false_negative_rate"],
                "fp_concentration_share": row["fp_concentration_share"],
            }
        )
    return rows


def _build_threshold_robustness_rows(threshold_sweep_path: str | Path | None, ranking_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not threshold_sweep_path:
        return []
    path = Path(threshold_sweep_path)
    if not path.exists():
        return []
    frame = pd.read_csv(path, keep_default_na=False)
    if "signature_id" not in frame.columns:
        return []
    value_column = next((col for col in ["objective_score", "balanced_accuracy", "power_score", "mean_power"] if col in frame.columns), None)
    if value_column is None:
        return []
    rows: list[dict[str, Any]] = []
    for signature_id, group in frame.groupby("signature_id", sort=False):
        scores = pd.to_numeric(group[value_column], errors="coerce").fillna(0.0)
        if scores.empty:
            continue
        best = float(scores.max())
        near_best = group[scores >= best - 0.01]
        selected_threshold = None
        if "threshold" in near_best.columns:
            selected_threshold = float(pd.to_numeric(near_best["threshold"], errors="coerce").dropna().min()) if not near_best["threshold"].empty else None
        rows.append(
            {
                "analyzer_id": signature_id,
                "signature_id": signature_id,
                "family": next((row["family"] for row in ranking_rows if row["signature_id"] == signature_id), "unknown"),
                "threshold_interval_width": float(pd.to_numeric(group["threshold"], errors="coerce").max() - pd.to_numeric(group["threshold"], errors="coerce").min()) if "threshold" in group.columns else 0.0,
                "within_one_percent_count": int(len(near_best)),
                "best_score": best,
                "selected_threshold": selected_threshold if selected_threshold is not None else "",
            }
        )
    return rows


def _build_bootstrap_rows(
    case_rows: list[dict[str, Any]],
    objective_profile: ObjectiveProfile,
    bootstrap: int,
    credible_interval: float,
) -> list[dict[str, Any]]:
    rng = np.random.default_rng(1337)
    rows: list[dict[str, Any]] = []
    for analyzer_id, analyzer_rows in _group_by(case_rows, "analyzer_id").items():
        if not analyzer_rows:
            continue
        samples = []
        indices = np.arange(len(analyzer_rows))
        for _ in range(int(bootstrap)):
            sample = [analyzer_rows[int(index)] for index in rng.choice(indices, size=len(indices), replace=True)]
            sample_metrics = _summary_metric_dict(sample)
            samples.append(
                _objective_score_from_metrics(
                    {
                        "posterior_mean_success": sample_metrics["posterior_mean_success"],
                        "posterior_lower_success": sample_metrics["posterior_lower_success"],
                        "precision": sample_metrics["precision"],
                        "recall": sample_metrics["recall"],
                        "specificity": sample_metrics["specificity"],
                        "high_noise_success": sample_metrics["high_noise_success"],
                        "normal_noise_success": sample_metrics["normal_noise_success"],
                        "worst_bucket_success": sample_metrics["worst_bucket_success"],
                        "conflict_resistance": sample_metrics["conflict_resistance"],
                        "one_minus_false_positive_rate": 1.0 - sample_metrics["false_positive_rate"],
                        "one_minus_false_negative_rate": 1.0 - sample_metrics["false_negative_rate"],
                        "one_minus_fp_concentration_share": 1.0 - sample_metrics["fp_concentration_share"],
                        "one_minus_high_noise_gap": 1.0 - abs(sample_metrics["high_noise_delta"]),
                        "one_minus_primary_stolen_rate": 1.0 - sample_metrics["primary_stolen_rate"],
                    },
                    objective_profile,
                )
            )
        if not samples:
            continue
        rows.append(
            {
                "analyzer_id": analyzer_id,
                "signature_id": analyzer_rows[0]["signature_id"],
                "family": analyzer_rows[0]["family"],
                "bootstrap": int(bootstrap),
                "credible_interval": float(credible_interval),
                "power_score_estimate": float(np.mean(samples)),
                "power_score_ci_low": float(np.quantile(samples, (1.0 - credible_interval) / 2.0)),
                "power_score_ci_high": float(np.quantile(samples, 1.0 - (1.0 - credible_interval) / 2.0)),
                "sample_count": int(len(samples)),
            }
        )
    return rows


def _build_power_summary(
    *,
    ranking_rows: list[dict[str, Any]],
    conflict_rows: list[dict[str, Any]],
    fp_rows: list[dict[str, Any]],
    worst_rows: list[dict[str, Any]],
    objective_profile: ObjectiveProfile,
    threshold_profile: ThresholdProfile,
    threshold_robustness_rows: list[dict[str, Any]],
    bootstrap_rows: list[dict[str, Any]],
    split_seed: int,
    split_ratios: tuple[float, float, float],
    credible_interval: float,
    prior_alpha: float,
    prior_beta: float,
    manifest: pd.DataFrame,
) -> dict[str, Any]:
    if not ranking_rows:
        return {
            "objective_name": objective_profile.name,
            "total_analyzers": 0,
            "notes": ["No analyzers were available for power ranking."],
        }
    strongest_mean = max(ranking_rows, key=lambda item: (item["mean_power"], item["lower_bound_power"]))
    strongest_lower = max(ranking_rows, key=lambda item: (item["lower_bound_power"], item["mean_power"]))
    weakest = min(ranking_rows, key=lambda item: (item["lower_bound_power"], item["mean_power"]))
    guardrail = max(ranking_rows, key=lambda item: (item["fp_concentration_share"], -item["lower_bound_power"]))
    worst_noise = min(ranking_rows, key=lambda item: (item["high_noise_success"], item["mean_power"]))
    summary = {
        "objective_name": objective_profile.name,
        "objective_mode": objective_profile.mode,
        "total_analyzers": len(ranking_rows),
        "total_cases": int(len(manifest)),
        "split_seed": split_seed,
        "split_ratios": list(split_ratios),
        "credible_interval": float(credible_interval),
        "prior_alpha": float(prior_alpha),
        "prior_beta": float(prior_beta),
        "threshold_profile": threshold_profile.to_dict(),
        "objective_weights": dict(objective_profile.weights),
        "strongest_analyzer_by_mean": strongest_mean,
        "strongest_analyzer_by_lower_bound": strongest_lower,
        "weakest_analyzer": weakest,
        "guardrail_needed_analyzer": guardrail,
        "worst_high_noise_analyzer": worst_noise,
        "largest_fp_concentration_analyzer": max(fp_rows, key=lambda item: (item["fp_concentration_share"], item["false_positive_cases"])) if fp_rows else {},
        "worst_bucket_analyzer": worst_rows[0] if worst_rows else {},
        "conflict_warning_count": len([row for row in conflict_rows if row.get("conflict_cases", 0) > 0]),
        "threshold_robustness_available": bool(threshold_robustness_rows),
        "bootstrap_available": bool(bootstrap_rows),
        "notes": [
            "Beta-binomial posterior estimates success probability by analyzer and condition bucket.",
            "Synthetic-corpus results are development methodology, not field calibration.",
        ],
    }
    return summary


def _build_readme(
    *,
    power_summary: dict[str, Any],
    objective_profile: ObjectiveProfile,
    threshold_profile: ThresholdProfile,
    split_seed: int,
    split_ratios: tuple[float, float, float],
    credible_interval: float,
    bootstrap: int,
) -> str:
    strongest_mean = power_summary.get("strongest_analyzer_by_mean", {})
    strongest_lower = power_summary.get("strongest_analyzer_by_lower_bound", {})
    weakest = power_summary.get("weakest_analyzer", {})
    guardrail = power_summary.get("guardrail_needed_analyzer", {})
    worst_noise = power_summary.get("worst_high_noise_analyzer", {})
    fp = power_summary.get("largest_fp_concentration_analyzer", {})
    lines = [
        "# Gamma Analyzer Power Audit",
        "",
        "## What this is",
        "This layer ranks analyzers by posterior diagnostic power, not raw accuracy alone.",
        "The beta-binomial posterior estimates success probability under the deliberate synthetic validation corpus.",
        "Treat these results as development-corpus evidence, not field calibration.",
        "",
        "## Objective",
        f"- Objective: `{objective_profile.name}`",
        f"- Mode: `{objective_profile.mode}`",
        f"- Threshold profile: `{threshold_profile.name}`",
        f"- Split seed: {split_seed}",
        f"- Split ratios: {split_ratios[0]:.2f}/{split_ratios[1]:.2f}/{split_ratios[2]:.2f}",
        f"- Credible interval: {credible_interval:.2f}",
        f"- Bootstrap samples: {bootstrap}",
        "",
        "## Summary",
        f"- Strongest analyzer by balanced objective: {strongest_mean.get('analyzer_id', 'n/a')}",
        f"- Strongest analyzer by lower bound: {strongest_lower.get('analyzer_id', 'n/a')}",
        f"- Weakest analyzer: {weakest.get('analyzer_id', 'n/a')}",
        f"- Guardrail-needed analyzer: {guardrail.get('analyzer_id', 'n/a')}",
        f"- Worst high-noise analyzer: {worst_noise.get('analyzer_id', 'n/a')}",
        f"- Largest false-positive concentration: {fp.get('analyzer_id', 'n/a')}",
        "",
        "## Notes",
        "- Success distributions are conditioned by analyzer, family, split, truth label, noise tier, waveform intent, and conflict state where available.",
        "- Lower-bound ranking is more conservative than mean-power ranking.",
        "- If a threshold sweep was supplied, threshold robustness is captured separately.",
    ]
    return "\n".join(lines) + "\n"


def _objective_score_from_metrics(metrics: dict[str, float], objective_profile: ObjectiveProfile) -> float:
    return sum(float(weight) * float(metrics.get(metric, 0.0)) for metric, weight in objective_profile.weights.items())


def _summary_metric_dict(rows: list[dict[str, Any]]) -> dict[str, float]:
    metrics = _compute_case_metrics(rows)
    overall = _summarize_rows_for_metrics(rows)
    return {
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "specificity": metrics["specificity"],
        "false_positive_rate": metrics["false_positive_rate"],
        "false_negative_rate": metrics["false_negative_rate"],
        "posterior_mean_success": overall["posterior_mean_success"],
        "posterior_lower_success": overall["posterior_lower_success"],
        "high_noise_success": overall["high_noise_success"],
        "normal_noise_success": overall["normal_noise_success"],
        "high_noise_delta": overall["high_noise_delta"],
        "conflict_resistance": overall["conflict_resistance"],
        "fp_concentration_share": overall["fp_concentration_share"],
        "primary_stolen_rate": overall["primary_stolen_rate"],
        "worst_bucket_success": overall["worst_bucket_success"],
    }


def _compute_case_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    positives = sum(1 for row in rows if _to_bool(row["expected_fault_present"]))
    negatives = total - positives
    tp = fp = tn = fn = 0
    for row in rows:
        expected = _to_bool(row["expected_fault_present"])
        success = bool(row["is_correct"])
        if expected and success:
            tp += 1
        elif expected and not success:
            fn += 1
        elif (not expected) and not success:
            fp += 1
        else:
            tn += 1
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    specificity = _safe_div(tn, tn + fp)
    return {
        "total_cases": total,
        "positives": positives,
        "negatives": negatives,
        "TP": tp,
        "FP": fp,
        "TN": tn,
        "FN": fn,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "false_positive_rate": _safe_div(fp, fp + tn),
        "false_negative_rate": _safe_div(fn, fn + tp),
        "accuracy": _safe_div(tp + tn, total),
        "balanced_accuracy": (recall + specificity) / 2.0 if total else 0.0,
        "F1": _safe_div(2 * precision * recall, precision + recall),
        "conflict_rate": _safe_div(sum(1 for row in rows if row["conflict_state"] not in {"negative_avoided_primary", "negative_no_match"}), total),
    }


def _summarize_rows_for_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {
            "posterior_mean_success": 0.0,
            "posterior_lower_success": 0.0,
            "high_noise_success": 0.0,
            "normal_noise_success": 0.0,
            "high_noise_delta": 0.0,
            "conflict_resistance": 0.0,
            "fp_concentration_share": 0.0,
            "primary_stolen_rate": 0.0,
            "worst_bucket_success": 0.0,
        }
    successes = sum(1 for row in rows if row["is_correct"])
    failures = len(rows) - successes
    alpha, beta, posterior_mean = beta_posterior(successes, failures)
    low, _high = beta_credible_interval(alpha, beta)
    high_noise_rows = [row for row in rows if row["noise_tier"] == "high"]
    normal_noise_rows = [row for row in rows if row["noise_tier"] == "normal"]
    conflict_rows = [row for row in rows if _is_conflict_case(row)]
    return {
        "posterior_mean_success": posterior_mean,
        "posterior_lower_success": low,
        "high_noise_success": _success_rate(high_noise_rows),
        "normal_noise_success": _success_rate(normal_noise_rows),
        "high_noise_delta": _success_rate(high_noise_rows) - _success_rate(normal_noise_rows) if high_noise_rows or normal_noise_rows else 0.0,
        "conflict_resistance": _success_rate(conflict_rows) if conflict_rows else 1.0,
        "fp_concentration_share": _top_concentration_share([row for row in rows if row["is_false_positive"]]),
        "primary_stolen_rate": _safe_div(sum(1 for row in rows if row["primary_stolen"]), len(rows)),
        "worst_bucket_success": min((_success_rate(subset) for _, subset in _group_by(rows, "noise_tier").items()), default=posterior_mean),
    }


def _recommended_status(row: dict[str, Any], *, lower_bound_power: float) -> str:
    fp_concentration = float(row.get("fp_concentration_share", 0.0))
    conflict_resistance = float(row.get("conflict_resistance", 0.0))
    high_noise_delta = abs(float(row.get("high_noise_delta", 0.0)))
    worst_bucket = float(row.get("worst_bucket_success", 0.0))
    precision = float(row.get("precision", 0.0))
    recall = float(row.get("recall", 0.0))

    if lower_bound_power >= 0.82 and fp_concentration <= 0.20 and conflict_resistance >= 0.80 and high_noise_delta <= 0.12:
        return "promote"
    if lower_bound_power >= 0.70 and precision >= 0.80 and fp_concentration <= 0.28 and worst_bucket >= 0.65:
        return "keep"
    if precision >= 0.80 and fp_concentration >= 0.30:
        return "guardrail_needed"
    if lower_bound_power < 0.60 or worst_bucket < 0.55 or recall < 0.65:
        return "do_not_trust"
    return "tune"


def _recommended_action(status: str) -> str:
    return {
        "promote": "Use as a primary analyzer candidate and monitor for drift.",
        "keep": "Keep the analyzer enabled; no immediate threshold change needed.",
        "tune": "Adjust thresholds or reference gating around the weakest bucket.",
        "guardrail_needed": "Add guardrails to curb concentrated false positives before operational use.",
        "do_not_trust": "Hold back from operational use until the analyzer is reworked or better validated.",
    }.get(status, "Review analyzer behavior before deployment.")


def _group_by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get(key, "")), []).append(row)
    return groups


def _conflict_warning(candidate_rows: list[dict[str, Any]]) -> str:
    threshold_rows = [row for row in candidate_rows if row["threshold_pass"]]
    if len(threshold_rows) < 2:
        return ""
    top = max(row["confidence"] for row in threshold_rows)
    close = [row["signature_id"] for row in threshold_rows if top - row["confidence"] <= 0.10]
    if len(close) >= 2:
        return "multiple_high_confidence_signatures_match: " + ", ".join(close)
    return "multiple_signatures_match_above_threshold: " + ", ".join(row["signature_id"] for row in threshold_rows)


def _success_rate(rows: list[dict[str, Any]]) -> float:
    return _safe_div(sum(1 for row in rows if row["is_correct"]), len(rows))


def _top_concentration_share(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    buckets: dict[str, int] = {}
    for row in rows:
        key = f"{row.get('test_id', '')}|{row.get('noise_tier', '')}|{row.get('waveform_intent', '')}|{row.get('conflict_state', '')}"
        buckets[key] = buckets.get(key, 0) + 1
    top = max(buckets.values()) if buckets else 0
    return _safe_div(top, len(rows))


def _is_conflict_case(row: dict[str, Any]) -> bool:
    return bool(
        row.get("multi_match_ambiguity")
        or row.get("primary_stolen")
        or row.get("is_false_positive")
        or row.get("is_false_negative")
        or str(row.get("conflict_warning", "")).strip()
    )


def _worst_bucket_success(rows: list[dict[str, Any]]) -> float:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = f"{row.get('split', '')}|{row.get('noise_tier', '')}|{row.get('waveform_intent', '')}|{row.get('conflict_state', '')}"
        buckets.setdefault(key, []).append(row)
    values = [_success_rate(bucket) for key, bucket in buckets.items() if len(bucket) >= 1]
    return min(values) if values else _success_rate(rows)


def _bucket_case_count(analyzer_rows: list[dict[str, Any]], bucket_type: str, bucket_value: str) -> int:
    return sum(1 for row in analyzer_rows if str(row.get(bucket_type, "")) == str(bucket_value))


def _safe_json(value: Any) -> Any:
    try:
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
    except Exception:
        pass
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_json(v) for v in value]
    if isinstance(value, tuple):
        return [_safe_json(v) for v in value]
    return value


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _safe_div(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank Gamma analyzers by posterior diagnostic power.")
    parser.add_argument("--manifest", required=True, help="Dataset manifest CSV.")
    parser.add_argument("--results", required=True, help="Campaign results CSV or directory containing them.")
    parser.add_argument("--threshold-profile", required=True, help="Threshold profile YAML/JSON used during the campaign.")
    parser.add_argument("--out", required=True, help="Output directory for analyzer power reports.")
    parser.add_argument("--split-manifest", help="Optional split manifest CSV from tuning statistics.")
    parser.add_argument("--split-seed", type=int, default=1337, help="Deterministic split seed if no split manifest is supplied.")
    parser.add_argument("--split-ratios", default="0.6,0.2,0.2", help="Comma-separated train/dev/test split ratios.")
    parser.add_argument("--objective", default="balanced_default", help="Objective profile name or path.")
    parser.add_argument("--prior-alpha", type=float, default=DEFAULT_PRIOR_ALPHA, help="Beta prior alpha.")
    parser.add_argument("--prior-beta", type=float, default=DEFAULT_PRIOR_BETA, help="Beta prior beta.")
    parser.add_argument("--credible-interval", type=float, default=DEFAULT_CREDIBLE_INTERVAL, help="Credible interval width.")
    parser.add_argument("--bootstrap", type=int, default=0, help="Optional bootstrap sample count for power score uncertainty.")
    parser.add_argument("--threshold-sweep", help="Optional threshold sweep CSV/summary for robustness analysis.")
    return parser


def _parse_ratios(value: str | None) -> tuple[float, float, float]:
    if not value:
        return DEFAULT_SPLIT_RATIOS
    parts = [float(item.strip()) for item in value.split(",") if item.strip()]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("split ratios must contain exactly three values")
    total = sum(parts)
    if not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise argparse.ArgumentTypeError("split ratios must sum to 1.0")
    return float(parts[0]), float(parts[1]), float(parts[2])


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    analyze_analyzer_power(
        manifest_path=args.manifest,
        results_path=args.results,
        threshold_profile_path=args.threshold_profile,
        out_dir=args.out,
        split_manifest_path=args.split_manifest,
        split_seed=args.split_seed,
        split_ratios=_parse_ratios(args.split_ratios),
        objective=args.objective,
        prior_alpha=args.prior_alpha,
        prior_beta=args.prior_beta,
        credible_interval=args.credible_interval,
        bootstrap=args.bootstrap,
        threshold_sweep_path=args.threshold_sweep,
    )
    return 0
