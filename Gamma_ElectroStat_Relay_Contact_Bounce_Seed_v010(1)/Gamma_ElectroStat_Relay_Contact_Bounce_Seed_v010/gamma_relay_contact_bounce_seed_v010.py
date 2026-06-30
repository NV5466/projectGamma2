"""Gamma / ElectroStat relay-contact-bounce seed v0.1.0.

The defining event is one validated mechanical switching command followed by
one intended contact transition, a finite cluster of unintended state
reversals or partial excursions, and then a stable final state.

For AC captures, the carrier is removed before edge activity is measured.
The signal is divided into half-cycles, then into short subwindows. Every
subwindow receives robust derivative features, including median |d(state)/dt|
and MAD(|d(state)/dt|). Signed derivative averaging is never used because
positive and negative bounce edges would cancel.

Population geometry
-------------------
A = full contact bounce present
B = clean single transition, eligible for clean-reference modeling
T = transition completed with transient-only activity but no full reversal
F = failed or incomplete transition
U = uncertain or unusable

Only A builds the bounce model. Only B builds the clean transition reference.
A B capture is negative only for this seed and is not a declaration of global
system health. SNR is intentionally deferred in v0.1.0.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal
import json
import math
import zipfile

import numpy as np
from numpy.typing import NDArray
import pandas as pd
from scipy.ndimage import median_filter
from scipy.signal import find_peaks, savgol_filter
import matplotlib.pyplot as plt

Array = NDArray[np.float64]
StateName = Literal["open", "closed"]
SignalType = Literal["ac", "dc"]
Topology = Literal[
    "load_side_voltage",
    "across_contact_voltage",
    "contact_current",
    "generic_state_signal",
]


# ---------------------------------------------------------------------------
# Public data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RelayMeasurementMetadata:
    contact_channel_name: str = "contact_or_load_signal"
    contact_channel_units: str = "V"
    source_reference_channel_name: str | None = None
    command_channel_name: str | None = None
    scope_model: str = "unknown"
    scope_bandwidth_hz: float | None = None
    sample_rate_hz: float | None = None
    probe_bandwidth_hz: float | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RelayCaptureContext:
    capture_id: str
    signal_type: SignalType = "ac"
    measurement_topology: Topology = "load_side_voltage"
    commanded_final_state: StateName = "closed"
    initial_state: StateName | None = None
    transition_expected: bool = True
    transition_validated: bool = True
    transition_completed: bool | None = None
    event_marker_time_s: float | None = None
    line_frequency_hz: float | None = 60.0
    operating_state: str = "unknown"
    relay_or_contactor_id: str = "unknown"
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RelayBounceConfig:
    # Event and stable regions
    fallback_marker_fraction: float = 0.25
    pre_event_fraction_for_levels: float = 0.35
    post_event_fraction_for_levels: float = 0.25
    command_search_start_fraction: float = 0.05

    # AC carrier and half-cycle observability
    zero_crossing_exclusion_fraction: float = 0.10
    minimum_half_cycles: int = 3
    carrier_fit_min_samples: int = 32

    # Nested subwindows inside each half-cycle
    derivative_window_s: float = 0.00025
    minimum_window_samples: int = 8
    derivative_activity_scale_multiplier: float = 6.0
    derivative_activity_absolute_floor_per_s: float = 20.0
    minimum_window_observable_fraction: float = 0.35

    # State reconstruction
    state_smoothing_s: float = 0.00003
    open_state_threshold: float = 0.25
    closed_state_threshold: float = 0.75
    minimum_full_state_dwell_s: float = 0.00004
    maximum_bridgeable_unknown_gap_s: float = 0.0015
    required_final_state_hold_s: float = 0.0020
    final_state_observable_fraction_min: float = 0.90
    intended_edge_guard_s: float = 0.00008
    minimum_partial_state_excursion: float = 0.10
    maximum_bounce_cluster_s: float = 0.050

    # Level-separation and metadata guards
    minimum_level_separation_scales: float = 5.0
    minimum_level_separation_absolute: float = 0.05
    minimum_source_reference_peak: float = 1e-6

    # Population templates aligned to first intended contact
    template_pre_s: float = 0.002
    template_post_s: float = 0.020
    minimum_clean_reference_captures: int = 2
    minimum_bounce_model_captures: int = 2

    # Provisional support labels
    bootstrap_iterations: int = 100
    bootstrap_seed: int = 1159745
    epsilon: float = 1e-12

    def __post_init__(self) -> None:
        if not 0 < self.fallback_marker_fraction < 1:
            raise ValueError("fallback_marker_fraction must lie in (0, 1)")
        if self.derivative_window_s <= 0:
            raise ValueError("derivative_window_s must be positive")
        if not 0 < self.open_state_threshold < self.closed_state_threshold < 1:
            raise ValueError("state thresholds must satisfy 0 < open < closed < 1")
        if self.required_final_state_hold_s <= 0:
            raise ValueError("required_final_state_hold_s must be positive")
        if self.bootstrap_iterations < 20:
            raise ValueError("bootstrap_iterations must be at least 20")


@dataclass(frozen=True)
class RelayBounceResult:
    status: str
    snr_evaluated: bool
    confidence_status: str
    capture_classification: pd.DataFrame
    bounce_features: pd.DataFrame
    window_features: pd.DataFrame
    normalized_state_trajectories: Array
    state_validity_masks: Array
    relative_template_time_s: Array
    bounce_state_template: Array
    bounce_state_spread: Array
    clean_state_reference: Array
    clean_state_reference_spread: Array
    bounce_minus_clean_template: Array
    population_summary: pd.DataFrame
    evidence: dict[str, str]
    diagnostics: dict[str, Any]
    notes: tuple[str, ...]

    def summary_dict(self) -> dict[str, Any]:
        counts = (
            self.capture_classification["capture_class"].value_counts().to_dict()
            if not self.capture_classification.empty else {}
        )
        return {
            "status": self.status,
            "snr_evaluated": self.snr_evaluated,
            "confidence_status": self.confidence_status,
            "class_counts": counts,
            "evidence": self.evidence,
            "population_summary": (
                self.population_summary.iloc[0].to_dict()
                if not self.population_summary.empty else {}
            ),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Basic validation and robust utilities
# ---------------------------------------------------------------------------

def _validate_inputs(
    time_s: Array,
    contact_captures: Array,
    optional_captures: Array | None,
    name: str,
) -> tuple[Array, Array, Array | None, float]:
    t = np.asarray(time_s, dtype=float)
    x = np.asarray(contact_captures, dtype=float)
    if t.ndim != 1 or t.size < 64:
        raise ValueError("time_s must be one-dimensional with at least 64 samples")
    if x.ndim == 1:
        x = x[None, :]
    if x.ndim != 2 or x.shape[1] != t.size:
        raise ValueError("contact_captures must have shape (capture_count, sample_count)")
    if not np.isfinite(t).all() or not np.isfinite(x).all():
        raise ValueError("non-finite time or contact samples are unsupported")
    steps = np.diff(t)
    dt = float(np.median(steps))
    if dt <= 0 or np.any(steps <= 0):
        raise ValueError("time_s must be strictly increasing")
    if np.max(np.abs(steps - dt)) > 0.01 * dt:
        raise ValueError("uniform sampling is required in v0.1.0")

    y = None
    if optional_captures is not None:
        y = np.asarray(optional_captures, dtype=float)
        if y.ndim == 1:
            y = y[None, :]
        if y.shape != x.shape:
            raise ValueError(f"{name} must match contact_captures shape")
        if not np.isfinite(y).all():
            raise ValueError(f"non-finite values in {name} are unsupported")
    return t, x, y, dt


def _robust_location_scale(values: Array, epsilon: float) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return math.nan, math.nan
    center = float(np.median(values))
    mad = float(np.median(np.abs(values - center)))
    return center, max(1.4826 * mad, epsilon)


def _opposite_state(state: StateName) -> StateName:
    return "open" if state == "closed" else "closed"


def _state_value(state: StateName) -> int:
    return 1 if state == "closed" else 0


def _safe_savgol(values: Array, preferred_window: int = 31) -> Array:
    n = values.size
    window = min(preferred_window, n if n % 2 else n - 1)
    window = max(5, window)
    if window >= n:
        window = n - 1 if (n - 1) % 2 else n - 2
    if window < 5:
        return values.copy()
    return savgol_filter(values, window_length=window, polyorder=2, mode="interp")


# ---------------------------------------------------------------------------
# Command marker and AC carrier construction
# ---------------------------------------------------------------------------

def _command_edge_information(
    time_s: Array,
    command: Array | None,
    context: RelayCaptureContext,
    config: RelayBounceConfig,
) -> tuple[int, int, str]:
    if context.event_marker_time_s is not None:
        idx = int(np.argmin(np.abs(time_s - context.event_marker_time_s)))
        return idx, 1, "context_event_marker"

    if command is None:
        idx = int(round(config.fallback_marker_fraction * (time_s.size - 1)))
        return idx, 0, "fallback_fraction"

    smooth = _safe_savgol(np.asarray(command, dtype=float))
    derivative = np.abs(np.gradient(smooth, time_s))
    start = int(round(config.command_search_start_fraction * time_s.size))
    search = derivative[start:]
    if search.size == 0 or np.max(search) <= config.epsilon:
        idx = int(round(config.fallback_marker_fraction * (time_s.size - 1)))
        return idx, 0, "command_edge_unavailable_fallback"

    peak_height = max(float(np.max(search)) * 0.25, config.epsilon)
    distance = max(1, int(round(0.0002 / (time_s[1] - time_s[0]))))
    peaks, _ = find_peaks(search, height=peak_height, distance=distance)
    marker = start + int(peaks[0] if peaks.size else np.argmax(search))
    return marker, int(peaks.size if peaks.size else 1), "command_channel_edge"


def _fit_fundamental_carrier(
    time_s: Array,
    signal: Array,
    frequency_hz: float,
    fit_mask: Array,
    config: RelayBounceConfig,
) -> Array:
    indices = np.flatnonzero(fit_mask)
    if indices.size < config.carrier_fit_min_samples:
        raise ValueError("insufficient stable source-present samples for AC carrier fit")
    w = 2.0 * np.pi * frequency_hz
    design = np.column_stack([
        np.sin(w * time_s[indices]),
        np.cos(w * time_s[indices]),
        np.ones(indices.size),
    ])
    coefficients, *_ = np.linalg.lstsq(design, signal[indices], rcond=None)
    full_design = np.column_stack([
        np.sin(w * time_s),
        np.cos(w * time_s),
        np.ones(time_s.size),
    ])
    fitted = full_design @ coefficients
    return fitted


def _half_cycle_boundaries(
    time_s: Array,
    carrier: Array,
    frequency_hz: float,
    config: RelayBounceConfig,
) -> Array:
    dt = float(time_s[1] - time_s[0])
    samples_per_cycle = max(8, int(round(1.0 / (frequency_hz * dt))))
    smooth_window = max(5, int(round(samples_per_cycle / 20)))
    if smooth_window % 2 == 0:
        smooth_window += 1
    smooth = _safe_savgol(carrier, smooth_window)
    signs = np.signbit(smooth)
    crossings = np.flatnonzero(signs[1:] != signs[:-1]) + 1

    expected_half = max(2, int(round(0.5 / (frequency_hz * dt))))
    kept: list[int] = []
    for idx in crossings:
        if not kept or idx - kept[-1] >= int(0.45 * expected_half):
            kept.append(int(idx))

    if len(kept) < config.minimum_half_cycles + 1:
        # Phase-fit fallback. This still uses the measured carrier phase rather
        # than assuming that t=0 happens to be a zero crossing.
        w = 2.0 * np.pi * frequency_hz
        design = np.column_stack([np.sin(w * time_s), np.cos(w * time_s)])
        coefficients, *_ = np.linalg.lstsq(design, carrier, rcond=None)
        phase = math.atan2(float(coefficients[1]), float(coefficients[0]))
        cycle_phase = w * time_s + phase
        integer_crossings = np.floor(cycle_phase / np.pi).astype(int)
        kept = (np.flatnonzero(np.diff(integer_crossings) != 0) + 1).tolist()

    boundaries = np.array(sorted(set([0, *kept, time_s.size])), dtype=int)
    boundaries = boundaries[np.diff(np.r_[boundaries, boundaries[-1] + 1]) > 0]
    return boundaries


# ---------------------------------------------------------------------------
# State-coordinate construction
# ---------------------------------------------------------------------------

def _stable_region_masks(
    n: int,
    marker: int,
    context: RelayCaptureContext,
    config: RelayBounceConfig,
) -> tuple[Array, Array, StateName, StateName]:
    initial_state = context.initial_state or _opposite_state(context.commanded_final_state)
    final_state = context.commanded_final_state

    pre_stop = max(4, marker)
    pre_start = max(0, pre_stop - int(round(config.pre_event_fraction_for_levels * n)))
    post_count = max(4, int(round(config.post_event_fraction_for_levels * n)))
    post_start = max(marker + 1, n - post_count)

    pre_mask = np.zeros(n, dtype=bool)
    post_mask = np.zeros(n, dtype=bool)
    pre_mask[pre_start:pre_stop] = True
    post_mask[post_start:] = True
    return pre_mask, post_mask, initial_state, final_state


def _source_present_state(topology: Topology) -> StateName:
    if topology == "across_contact_voltage":
        return "open"
    return "closed"


def _construct_state_coordinate(
    time_s: Array,
    contact_signal: Array,
    source_reference: Array | None,
    marker: int,
    context: RelayCaptureContext,
    config: RelayBounceConfig,
) -> dict[str, Any]:
    n = time_s.size
    dt = float(time_s[1] - time_s[0])
    pre_mask, post_mask, initial_state, final_state = _stable_region_masks(
        n, marker, context, config
    )

    half_cycle_boundaries = np.array([0, n], dtype=int)
    carrier = np.zeros(n, dtype=float)
    observability = np.ones(n, dtype=bool)

    if context.signal_type == "ac":
        if context.line_frequency_hz is None or context.line_frequency_hz <= 0:
            raise ValueError("AC captures require a positive line_frequency_hz")

        if source_reference is not None:
            carrier = np.asarray(source_reference, dtype=float)
            carrier_source = "measured_source_reference"
        else:
            source_state = _source_present_state(context.measurement_topology)
            fit_mask = pre_mask if initial_state == source_state else post_mask
            carrier = _fit_fundamental_carrier(
                time_s,
                contact_signal,
                context.line_frequency_hz,
                fit_mask,
                config,
            )
            carrier_source = "fitted_from_stable_source_present_contact_region"

        half_cycle_boundaries = _half_cycle_boundaries(
            time_s,
            carrier,
            context.line_frequency_hz,
            config,
        )

        abs_carrier = np.abs(carrier)
        denominator = np.empty(n, dtype=float)
        observability[:] = False
        for start, stop in zip(half_cycle_boundaries[:-1], half_cycle_boundaries[1:]):
            if stop - start < 2:
                continue
            local = abs_carrier[start:stop]
            local_peak = float(np.quantile(local, 0.95))
            floor = max(
                config.minimum_source_reference_peak,
                config.zero_crossing_exclusion_fraction * local_peak,
            )
            denominator[start:stop] = np.maximum(local, floor)
            observability[start:stop] = local >= floor

        metric = np.abs(contact_signal) / np.maximum(denominator, config.epsilon)
    else:
        carrier_source = "not_applicable_dc"
        metric = np.asarray(contact_signal, dtype=float).copy()

    # Learn open and closed levels from the actual pre and tail states. This
    # automatically handles load-side, across-contact, and polarity inversions.
    pre_values = metric[pre_mask & observability]
    post_values = metric[post_mask & observability]
    pre_center, pre_scale = _robust_location_scale(pre_values, config.epsilon)
    post_center, post_scale = _robust_location_scale(post_values, config.epsilon)

    if initial_state == "open":
        open_level, open_scale = pre_center, pre_scale
        closed_level, closed_scale = post_center, post_scale
    else:
        closed_level, closed_scale = pre_center, pre_scale
        open_level, open_scale = post_center, post_scale

    separation = abs(closed_level - open_level)
    pooled_scale = max(open_scale, closed_scale, config.epsilon)
    separation_scales = separation / pooled_scale
    levels_identifiable = bool(
        np.isfinite(separation)
        and separation >= config.minimum_level_separation_absolute
        and separation_scales >= config.minimum_level_separation_scales
    )

    if levels_identifiable:
        state_coordinate = (metric - open_level) / (closed_level - open_level)
    else:
        state_coordinate = np.full(n, np.nan)

    smoothing_samples = max(1, int(round(config.state_smoothing_s / dt)))
    if smoothing_samples % 2 == 0:
        smoothing_samples += 1
    if smoothing_samples > 1 and np.isfinite(state_coordinate).any():
        fill = np.where(np.isfinite(state_coordinate), state_coordinate, 0.5)
        state_coordinate = median_filter(fill, size=smoothing_samples, mode="nearest")
        state_coordinate[~observability] = np.nan

    return {
        "state_coordinate": state_coordinate,
        "observability": observability,
        "carrier": carrier,
        "carrier_source": carrier_source,
        "half_cycle_boundaries": half_cycle_boundaries,
        "initial_state": initial_state,
        "final_state": final_state,
        "open_level": open_level,
        "closed_level": closed_level,
        "open_scale": open_scale,
        "closed_scale": closed_scale,
        "level_separation": separation,
        "level_separation_scales": separation_scales,
        "levels_identifiable": levels_identifiable,
    }


# ---------------------------------------------------------------------------
# Half-cycle subwindow derivative and MAD features
# ---------------------------------------------------------------------------

def _window_feature_table(
    time_s: Array,
    state_coordinate: Array,
    observability: Array,
    half_cycle_boundaries: Array,
    marker: int,
    capture_id: str,
    config: RelayBounceConfig,
) -> pd.DataFrame:
    dt = float(time_s[1] - time_s[0])
    valid_indices = np.flatnonzero(np.isfinite(state_coordinate) & observability)
    if valid_indices.size >= 2:
        filled = np.interp(
            np.arange(time_s.size),
            valid_indices,
            state_coordinate[valid_indices],
        )
        derivative = np.gradient(filled, dt)
        derivative[~observability] = np.nan
        invalid_neighbors = ~observability.copy()
        invalid_neighbors[:-1] |= ~observability[1:]
        invalid_neighbors[1:] |= ~observability[:-1]
        derivative[invalid_neighbors] = np.nan
    else:
        derivative = np.full(time_s.size, np.nan)

    window_samples = max(
        config.minimum_window_samples,
        int(round(config.derivative_window_s / dt)),
    )

    rows: list[dict[str, Any]] = []
    if half_cycle_boundaries.size < 2:
        half_cycle_boundaries = np.array([0, time_s.size], dtype=int)

    for half_idx, (half_start, half_stop) in enumerate(
        zip(half_cycle_boundaries[:-1], half_cycle_boundaries[1:])
    ):
        if half_stop <= half_start:
            continue
        for start in range(int(half_start), int(half_stop), window_samples):
            stop = min(start + window_samples, int(half_stop))
            if stop - start < 2:
                continue
            local_d = np.abs(derivative[start:stop])
            local_state = state_coordinate[start:stop]
            finite_d = local_d[np.isfinite(local_d)]
            finite_state = local_state[np.isfinite(local_state)]
            observable_fraction = float(np.mean(observability[start:stop]))
            if finite_d.size:
                derivative_median = float(np.median(finite_d))
                derivative_mad = 1.4826 * float(
                    np.median(np.abs(finite_d - derivative_median))
                )
                derivative_peak = float(np.max(finite_d))
            else:
                derivative_median = math.nan
                derivative_mad = math.nan
                derivative_peak = math.nan
            if finite_state.size:
                state_median = float(np.median(finite_state))
                state_mad = 1.4826 * float(
                    np.median(np.abs(finite_state - state_median))
                )
                state_p01 = float(np.quantile(finite_state, 0.01))
                state_p05 = float(np.quantile(finite_state, 0.05))
                state_p95 = float(np.quantile(finite_state, 0.95))
                state_p99 = float(np.quantile(finite_state, 0.99))
                state_quantile_range = state_p95 - state_p05
            else:
                state_median = math.nan
                state_mad = math.nan
                state_p01 = math.nan
                state_p05 = math.nan
                state_p95 = math.nan
                state_p99 = math.nan
                state_quantile_range = math.nan

            rows.append({
                "capture_id": capture_id,
                "half_cycle_index": half_idx,
                "window_index_in_half_cycle": int((start - half_start) // window_samples),
                "window_start_index": start,
                "window_stop_index": stop,
                "window_start_time_s": float(time_s[start]),
                "window_stop_time_s": float(time_s[stop - 1]),
                "window_mid_time_s": float(0.5 * (time_s[start] + time_s[stop - 1])),
                "after_command_marker": bool(start >= marker),
                "observable_fraction": observable_fraction,
                "median_abs_state_derivative_per_s": derivative_median,
                "mad_abs_state_derivative_per_s": derivative_mad,
                "peak_abs_state_derivative_per_s": derivative_peak,
                "median_normalized_state": state_median,
                "mad_normalized_state": state_mad,
                "state_p01": state_p01,
                "state_p05": state_p05,
                "state_p95": state_p95,
                "state_p99": state_p99,
                "state_quantile_range": state_quantile_range,
            })

    table = pd.DataFrame(rows)
    if table.empty:
        return table

    baseline_candidates = table[
        (table["window_start_index"] >= int(0.75 * time_s.size))
        & (table["observable_fraction"] >= config.minimum_window_observable_fraction)
    ]
    if len(baseline_candidates) < 3:
        baseline_candidates = table[
            table["observable_fraction"] >= config.minimum_window_observable_fraction
        ]

    median_center, median_scale = _robust_location_scale(
        baseline_candidates["median_abs_state_derivative_per_s"].to_numpy(float),
        config.epsilon,
    )
    mad_center, mad_scale = _robust_location_scale(
        baseline_candidates["mad_abs_state_derivative_per_s"].to_numpy(float),
        config.epsilon,
    )

    table["derivative_median_activity_z"] = (
        table["median_abs_state_derivative_per_s"] - median_center
    ) / max(median_scale, config.epsilon)
    table["derivative_mad_activity_z"] = (
        table["mad_abs_state_derivative_per_s"] - mad_center
    ) / max(mad_scale, config.epsilon)
    table["derivative_activity_window"] = (
        table["observable_fraction"] >= config.minimum_window_observable_fraction
    ) & (
        table["peak_abs_state_derivative_per_s"]
        >= config.derivative_activity_absolute_floor_per_s
    ) & (
        (table["derivative_median_activity_z"] >= config.derivative_activity_scale_multiplier)
        | (table["derivative_mad_activity_z"] >= config.derivative_activity_scale_multiplier)
    )
    return table


# ---------------------------------------------------------------------------
# State labels, runs, and bounce anatomy
# ---------------------------------------------------------------------------

def _bridge_unknown_same_state(labels: NDArray[np.int_], max_gap: int) -> NDArray[np.int_]:
    out = labels.copy()
    n = out.size
    idx = 0
    while idx < n:
        if out[idx] != -1:
            idx += 1
            continue
        start = idx
        while idx < n and out[idx] == -1:
            idx += 1
        stop = idx
        left = out[start - 1] if start > 0 else -1
        right = out[stop] if stop < n else -1
        if stop - start <= max_gap and left == right and left in (0, 1):
            out[start:stop] = left
    return out


def _extract_runs(labels: NDArray[np.int_], time_s: Array) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    n = labels.size
    idx = 0
    dt = float(time_s[1] - time_s[0])
    while idx < n:
        if labels[idx] not in (0, 1):
            idx += 1
            continue
        state = int(labels[idx])
        start = idx
        idx += 1
        while idx < n and labels[idx] == state:
            idx += 1
        stop = idx
        runs.append({
            "state": state,
            "start_index": start,
            "stop_index": stop,
            "start_time_s": float(time_s[start]),
            "stop_time_s": float(time_s[min(stop - 1, n - 1)] + dt),
            "duration_s": float((stop - start) * dt),
        })
    return runs


def _state_anatomy(
    time_s: Array,
    state_coordinate: Array,
    observability: Array,
    marker: int,
    final_state_name: StateName,
    window_table: pd.DataFrame,
    config: RelayBounceConfig,
) -> dict[str, Any]:
    dt = float(time_s[1] - time_s[0])
    labels = np.full(time_s.size, -1, dtype=int)
    labels[(state_coordinate <= config.open_state_threshold) & observability] = 0
    labels[(state_coordinate >= config.closed_state_threshold) & observability] = 1
    max_gap = max(1, int(round(config.maximum_bridgeable_unknown_gap_s / dt)))
    labels = _bridge_unknown_same_state(labels, max_gap)

    all_runs = _extract_runs(labels, time_s)
    minimum_dwell_samples = max(1, int(round(config.minimum_full_state_dwell_s / dt)))
    full_runs = [
        run for run in all_runs
        if run["stop_index"] - run["start_index"] >= minimum_dwell_samples
    ]
    runt_runs = [
        run for run in all_runs
        if run["stop_index"] - run["start_index"] < minimum_dwell_samples
    ]

    final_state = _state_value(final_state_name)
    full_after = [run for run in full_runs if run["stop_index"] > marker]
    first_final_pos = next(
        (idx for idx, run in enumerate(full_after) if run["state"] == final_state),
        None,
    )

    result: dict[str, Any] = {
        "labels": labels,
        "all_runs": all_runs,
        "full_runs": full_runs,
        "runt_runs": runt_runs,
        "first_final_run": None,
        "settle_run": None,
        "first_contact_index": -1,
        "final_settle_index": -1,
        "full_state_reversal_count": 0,
        "extra_edge_count": 0,
        "runt_excursion_count": 0,
        "partial_transient_window_count": 0,
        "edge_timing_low_observability_count": 0,
        "false_state_dwell_times_s": [],
        "stable_final_state_confirmed": False,
        "final_state_observable_fraction": 0.0,
        "event_interval_observable_fraction": 0.0,
        "edge_count_is_observability_limited": False,
        "pre_first_contact_unobservable_gap_s": 0.0,
    }
    if first_final_pos is None:
        return result

    first_final = full_after[first_final_pos]
    result["first_final_run"] = first_final
    result["first_contact_index"] = int(first_final["start_index"])
    preceding_unobservable_samples = 0
    lookback = int(first_final["start_index"]) - 1
    while lookback >= marker and not observability[lookback]:
        preceding_unobservable_samples += 1
        lookback -= 1
    result["pre_first_contact_unobservable_gap_s"] = float(
        preceding_unobservable_samples * dt
    )

    subsequent = full_after[first_final_pos:]
    opposite_positions = [
        idx for idx, run in enumerate(subsequent) if run["state"] != final_state
    ]
    if opposite_positions:
        last_opposite = max(opposite_positions)
        settle_pos = next(
            (
                idx for idx in range(last_opposite + 1, len(subsequent))
                if subsequent[idx]["state"] == final_state
            ),
            None,
        )
        if settle_pos is None:
            return result
    else:
        settle_pos = 0

    settle_run = subsequent[settle_pos]
    settle_index = int(settle_run["start_index"])
    result["settle_run"] = settle_run
    result["final_settle_index"] = settle_index

    segment = subsequent[:settle_pos + 1]
    edge_count = 0
    low_observable_edges = 0
    false_dwells: list[float] = []
    for previous, current in zip(segment[:-1], segment[1:]):
        if previous["state"] != current["state"]:
            edge_count += 1
            gap = current["start_index"] - previous["stop_index"]
            if gap > 1:
                low_observable_edges += 1
        if current["state"] != final_state:
            false_dwells.append(float(current["duration_s"]))

    result["extra_edge_count"] = edge_count
    result["full_state_reversal_count"] = edge_count // 2 if edge_count else 0
    result["edge_timing_low_observability_count"] = low_observable_edges
    result["false_state_dwell_times_s"] = false_dwells

    cluster_stop = min(
        time_s.size,
        first_final["start_index"]
        + int(round(config.maximum_bounce_cluster_s / dt)),
    )
    runt_excursions = [
        run for run in runt_runs
        if first_final["start_index"] <= run["start_index"] < cluster_stop
        and run["state"] != final_state
    ]
    result["runt_excursion_count"] = len(runt_excursions)

    final_region_stop = min(
        time_s.size,
        settle_index + int(round(config.required_final_state_hold_s / dt)),
    )
    if final_region_stop > settle_index:
        region_labels = labels[settle_index:final_region_stop]
        known = region_labels >= 0
        if np.any(known):
            final_fraction = float(np.mean(region_labels[known] == final_state))
            observable_fraction = float(np.mean(known))
        else:
            final_fraction = 0.0
            observable_fraction = 0.0
    else:
        final_fraction = 0.0
        observable_fraction = 0.0
    result["final_state_observable_fraction"] = observable_fraction
    event_observability_stop = min(
        time_s.size,
        settle_index + max(1, int(round(config.required_final_state_hold_s / dt))),
    )
    event_observability_region = observability[
        first_final["start_index"]:event_observability_stop
    ]
    event_observable_fraction = (
        float(np.mean(event_observability_region))
        if event_observability_region.size else 0.0
    )
    result["event_interval_observable_fraction"] = event_observable_fraction
    result["edge_count_is_observability_limited"] = bool(
        event_observable_fraction < 0.80
        or low_observable_edges > 0
        or preceding_unobservable_samples > 0
    )
    result["stable_final_state_confirmed"] = bool(
        final_region_stop - settle_index
        >= int(round(config.required_final_state_hold_s / dt))
        and final_fraction >= 0.999
        and observable_fraction >= config.final_state_observable_fraction_min
    )

    if not window_table.empty:
        guard_start_time = float(
            time_s[first_final["start_index"]]
            + max(config.intended_edge_guard_s, 1.5 * config.derivative_window_s)
        )
        if result["stable_final_state_confirmed"]:
            analysis_stop_time = float(
                min(
                    time_s[-1],
                    time_s[first_final["start_index"]] + config.maximum_bounce_cluster_s,
                )
            )
        else:
            analysis_stop_time = float(time_s[min(cluster_stop - 1, time_s.size - 1)])

        activity = window_table[
            (window_table["window_mid_time_s"] >= guard_start_time)
            & (window_table["window_mid_time_s"] <= analysis_stop_time)
            & (
                window_table["derivative_activity_window"]
                | (
                    window_table["peak_abs_state_derivative_per_s"]
                    >= config.derivative_activity_absolute_floor_per_s
                )
            )
            & (
                (window_table["state_quantile_range"] >= config.minimum_partial_state_excursion)
                | (
                    np.maximum(
                        np.abs(window_table["state_p01"] - final_state),
                        np.abs(window_table["state_p99"] - final_state),
                    ) >= config.minimum_partial_state_excursion
                )
                | (
                    np.abs(window_table["median_normalized_state"] - final_state)
                    >= config.minimum_partial_state_excursion
                )
            )
        ]

        full_edge_times: list[float] = []
        for previous, current in zip(segment[:-1], segment[1:]):
            if previous["state"] != current["state"]:
                full_edge_times.append(
                    0.5 * (previous["stop_time_s"] + current["start_time_s"])
                )

        partial_count = 0
        for _, row in activity.iterrows():
            midpoint = float(row["window_mid_time_s"])
            half_width = max(
                config.derivative_window_s,
                float(row["window_stop_time_s"] - row["window_start_time_s"]),
            )
            if not any(abs(midpoint - edge) <= half_width for edge in full_edge_times):
                partial_count += 1
        result["partial_transient_window_count"] = partial_count

    return result


# ---------------------------------------------------------------------------
# Capture analysis and classification
# ---------------------------------------------------------------------------

def _analyze_capture(
    time_s: Array,
    contact_signal: Array,
    source_reference: Array | None,
    command_signal: Array | None,
    context: RelayCaptureContext,
    config: RelayBounceConfig,
) -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame, Array, Array]:
    marker, command_edge_count, marker_source = _command_edge_information(
        time_s, command_signal, context, config
    )

    classification_base = {
        "capture_id": context.capture_id,
        "signal_type": context.signal_type,
        "measurement_topology": context.measurement_topology,
        "commanded_final_state": context.commanded_final_state,
        "marker_index": marker,
        "marker_time_s": float(time_s[marker]),
        "marker_source": marker_source,
        "command_edge_count": command_edge_count,
        "transition_expected": context.transition_expected,
        "transition_validated": context.transition_validated,
        "transition_completed_metadata": context.transition_completed,
        "operating_state": context.operating_state,
        "relay_or_contactor_id": context.relay_or_contactor_id,
    }

    try:
        state_data = _construct_state_coordinate(
            time_s,
            contact_signal,
            source_reference,
            marker,
            context,
            config,
        )
    except Exception as exc:
        classification = {
            **classification_base,
            "capture_class": "uncertain",
            "classification_reason": f"state_coordinate_failed:{type(exc).__name__}",
            "reference_eligible": False,
            "levels_identifiable": False,
            "first_contact_time_s": math.nan,
            "final_settle_time_s": math.nan,
            "bounce_duration_s": math.nan,
            "extra_edge_count": 0,
            "full_state_reversal_count": 0,
            "partial_transient_window_count": 0,
        }
        features = {
            "capture_id": context.capture_id,
            "error": str(exc),
        }
        return (
            classification,
            features,
            pd.DataFrame(),
            np.full(time_s.size, np.nan),
            np.zeros(time_s.size, dtype=bool),
        )

    state_coordinate = state_data["state_coordinate"]
    observability = state_data["observability"]
    windows = _window_feature_table(
        time_s,
        state_coordinate,
        observability,
        state_data["half_cycle_boundaries"],
        marker,
        context.capture_id,
        config,
    )
    anatomy = _state_anatomy(
        time_s,
        state_coordinate,
        observability,
        marker,
        context.commanded_final_state,
        windows,
        config,
    )

    first_idx = int(anatomy["first_contact_index"])
    settle_idx = int(anatomy["final_settle_index"])
    first_time = float(time_s[first_idx]) if first_idx >= 0 else math.nan
    settle_time = float(time_s[settle_idx]) if settle_idx >= 0 else math.nan
    bounce_duration = (
        float(settle_time - first_time)
        if first_idx >= 0 and settle_idx >= 0 else math.nan
    )

    if not context.transition_expected:
        capture_class = "uncertain"
        reason = "transition_not_expected"
    elif not context.transition_validated:
        capture_class = "uncertain"
        reason = "transition_not_validated"
    elif command_edge_count > 1:
        capture_class = "uncertain"
        reason = "multiple_command_edges_prevent_single_actuation_attribution"
    elif context.transition_completed is False:
        capture_class = "failed_transition"
        reason = "transition_marked_incomplete"
    elif not state_data["levels_identifiable"]:
        capture_class = "uncertain"
        reason = "open_and_closed_levels_not_identifiable"
    elif not anatomy["stable_final_state_confirmed"]:
        capture_class = "failed_transition"
        reason = "stable_commanded_final_state_not_confirmed"
    elif anatomy["extra_edge_count"] > 0:
        capture_class = "bounce_present"
        reason = "full_state_reversals_after_first_intended_contact"
    elif (
        anatomy["runt_excursion_count"] > 0
        or anatomy["partial_transient_window_count"] > 0
    ):
        capture_class = "non_bounce_transient"
        reason = "derivative_activity_or_runt_excursion_without_full_state_reversal"
    else:
        capture_class = "clean_single_transition"
        reason = "one_intended_transition_then_stable_final_state"

    classification = {
        **classification_base,
        "capture_class": capture_class,
        "classification_reason": reason,
        "reference_eligible": capture_class == "clean_single_transition",
        "levels_identifiable": bool(state_data["levels_identifiable"]),
        "carrier_source": state_data["carrier_source"],
        "open_level": float(state_data["open_level"]),
        "closed_level": float(state_data["closed_level"]),
        "level_separation": float(state_data["level_separation"]),
        "level_separation_scales": float(state_data["level_separation_scales"]),
        "first_contact_time_s": first_time,
        "final_settle_time_s": settle_time,
        "command_to_first_contact_latency_s": (
            float(first_time - time_s[marker]) if first_idx >= 0 else math.nan
        ),
        "bounce_duration_s": bounce_duration,
        "extra_edge_count": int(anatomy["extra_edge_count"]),
        "full_state_reversal_count": int(anatomy["full_state_reversal_count"]),
        "runt_excursion_count": int(anatomy["runt_excursion_count"]),
        "partial_transient_window_count": int(anatomy["partial_transient_window_count"]),
        "edge_timing_low_observability_count": int(
            anatomy["edge_timing_low_observability_count"]
        ),
        "final_state_observable_fraction": float(
            anatomy["final_state_observable_fraction"]
        ),
        "event_interval_observable_fraction": float(
            anatomy["event_interval_observable_fraction"]
        ),
        "edge_count_is_observability_limited": bool(
            anatomy["edge_count_is_observability_limited"]
        ),
        "pre_first_contact_unobservable_gap_s": float(
            anatomy["pre_first_contact_unobservable_gap_s"]
        ),
    }

    false_dwells = anatomy["false_state_dwell_times_s"]
    features = {
        "capture_id": context.capture_id,
        "capture_class": capture_class,
        "commanded_final_state": context.commanded_final_state,
        "command_to_first_contact_latency_s": classification[
            "command_to_first_contact_latency_s"
        ],
        "bounce_duration_s": bounce_duration,
        "extra_edge_count": int(anatomy["extra_edge_count"]),
        "full_state_reversal_count": int(anatomy["full_state_reversal_count"]),
        "false_state_dwell_count": len(false_dwells),
        "shortest_false_state_dwell_s": (
            float(min(false_dwells)) if false_dwells else math.nan
        ),
        "longest_false_state_dwell_s": (
            float(max(false_dwells)) if false_dwells else math.nan
        ),
        "median_false_state_dwell_s": (
            float(np.median(false_dwells)) if false_dwells else math.nan
        ),
        "runt_excursion_count": int(anatomy["runt_excursion_count"]),
        "partial_transient_window_count": int(anatomy["partial_transient_window_count"]),
        "edge_timing_low_observability_count": int(
            anatomy["edge_timing_low_observability_count"]
        ),
        "first_contact_time_s": first_time,
        "final_settle_time_s": settle_time,
        "final_state_observable_fraction": float(
            anatomy["final_state_observable_fraction"]
        ),
        "event_interval_observable_fraction": float(
            anatomy["event_interval_observable_fraction"]
        ),
        "edge_count_is_observability_limited": bool(
            anatomy["edge_count_is_observability_limited"]
        ),
        "pre_first_contact_unobservable_gap_s": float(
            anatomy["pre_first_contact_unobservable_gap_s"]
        ),
        "open_level": float(state_data["open_level"]),
        "closed_level": float(state_data["closed_level"]),
        "level_separation_scales": float(state_data["level_separation_scales"]),
        "half_cycle_count": int(max(0, state_data["half_cycle_boundaries"].size - 1)),
        "derivative_active_window_count": int(
            windows["derivative_activity_window"].sum()
            if not windows.empty else 0
        ),
        "morphology_class": (
            "full_make_bounce"
            if capture_class == "bounce_present" and context.commanded_final_state == "closed"
            else "full_break_bounce"
            if capture_class == "bounce_present"
            else "partial_or_transient_only"
            if capture_class == "non_bounce_transient"
            else "single_clean_transition"
            if capture_class == "clean_single_transition"
            else capture_class
        ),
    }

    return classification, features, windows, state_coordinate, observability


# ---------------------------------------------------------------------------
# Population templates and support labels
# ---------------------------------------------------------------------------

def _aligned_template(
    time_s: Array,
    state_trajectories: Array,
    align_times_s: Array,
    selected_indices: Array,
    config: RelayBounceConfig,
) -> tuple[Array, Array, Array]:
    dt = float(time_s[1] - time_s[0])
    relative_time = np.arange(
        -config.template_pre_s,
        config.template_post_s + 0.5 * dt,
        dt,
    )
    aligned: list[Array] = []
    for idx in selected_indices:
        align_time = float(align_times_s[idx])
        if not np.isfinite(align_time):
            continue
        relative_capture_time = time_s - align_time
        trajectory = state_trajectories[idx]
        finite = np.isfinite(trajectory)
        if np.sum(finite) < 2:
            continue
        aligned.append(np.interp(
            relative_time,
            relative_capture_time[finite],
            trajectory[finite],
            left=np.nan,
            right=np.nan,
        ))
    if not aligned:
        return relative_time, np.empty(0), np.empty(0)
    matrix = np.vstack(aligned)
    center = np.nanmedian(matrix, axis=0)
    spread = 1.4826 * np.nanmedian(np.abs(matrix - center[None, :]), axis=0)
    return relative_time, center, spread


def _categorical_repeatability(
    features: pd.DataFrame,
    config: RelayBounceConfig,
) -> str:
    bounce = features[features["capture_class"] == "bounce_present"]
    if len(bounce) < config.minimum_bounce_model_captures:
        return "exploratory"
    durations = bounce["bounce_duration_s"].dropna().to_numpy(float)
    edges = bounce["extra_edge_count"].to_numpy(float)
    if durations.size < 2:
        return "exploratory"
    duration_cv = float(np.std(durations) / max(np.mean(durations), config.epsilon))
    edge_cv = float(np.std(edges) / max(np.mean(edges), config.epsilon))
    if len(bounce) >= 6 and duration_cv <= 0.20 and edge_cv <= 0.20:
        return "strongly_supported"
    if duration_cv <= 0.50 and edge_cv <= 0.50:
        return "supported"
    return "exploratory"


def _bootstrap_stability(
    features: pd.DataFrame,
    config: RelayBounceConfig,
) -> tuple[str, dict[str, float]]:
    bounce = features[features["capture_class"] == "bounce_present"]
    if len(bounce) < 3:
        return "exploratory", {}
    rng = np.random.default_rng(config.bootstrap_seed)
    durations = bounce["bounce_duration_s"].to_numpy(float)
    edges = bounce["extra_edge_count"].to_numpy(float)
    duration_medians: list[float] = []
    edge_medians: list[float] = []
    for _ in range(config.bootstrap_iterations):
        sample = rng.integers(0, len(bounce), len(bounce))
        duration_medians.append(float(np.median(durations[sample])))
        edge_medians.append(float(np.median(edges[sample])))
    duration_relative = float(
        np.std(duration_medians)
        / max(abs(np.median(duration_medians)), config.epsilon)
    )
    edge_relative = float(
        np.std(edge_medians)
        / max(abs(np.median(edge_medians)), config.epsilon)
    )
    worst = max(duration_relative, edge_relative)
    status = (
        "strongly_supported" if worst <= 0.10
        else "supported" if worst <= 0.25
        else "exploratory"
    )
    return status, {
        "bootstrap_bounce_duration_relative_spread": duration_relative,
        "bootstrap_extra_edge_relative_spread": edge_relative,
    }


# ---------------------------------------------------------------------------
# Public analysis function
# ---------------------------------------------------------------------------

def analyze_relay_contact_bounce(
    time_s: Array,
    contact_captures: Array,
    contexts: Iterable[RelayCaptureContext],
    measurement_metadata: RelayMeasurementMetadata,
    *,
    source_reference_captures: Array | None = None,
    command_captures: Array | None = None,
    config: RelayBounceConfig = RelayBounceConfig(),
) -> RelayBounceResult:
    time_s, contact_captures, source_reference_captures, dt = _validate_inputs(
        time_s,
        contact_captures,
        source_reference_captures,
        "source_reference_captures",
    )
    _, _, command_captures, _ = _validate_inputs(
        time_s,
        contact_captures,
        command_captures,
        "command_captures",
    )
    contexts = list(contexts)
    if len(contexts) != contact_captures.shape[0]:
        raise ValueError("one RelayCaptureContext is required per capture")

    classifications: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    all_windows: list[pd.DataFrame] = []
    states: list[Array] = []
    validity: list[Array] = []

    for idx, context in enumerate(contexts):
        classification, feature, windows, state, valid = _analyze_capture(
            time_s,
            contact_captures[idx],
            None if source_reference_captures is None else source_reference_captures[idx],
            None if command_captures is None else command_captures[idx],
            context,
            config,
        )
        classifications.append(classification)
        features.append(feature)
        if not windows.empty:
            all_windows.append(windows)
        states.append(state)
        validity.append(valid)

    classification_table = pd.DataFrame(classifications)
    feature_table = pd.DataFrame(features)
    window_table = pd.concat(all_windows, ignore_index=True) if all_windows else pd.DataFrame()
    state_matrix = np.vstack(states)
    validity_matrix = np.vstack(validity)

    bounce_indices = classification_table.index[
        classification_table["capture_class"] == "bounce_present"
    ].to_numpy(int)
    clean_indices = classification_table.index[
        classification_table["capture_class"] == "clean_single_transition"
    ].to_numpy(int)
    align_times = classification_table["first_contact_time_s"].to_numpy(float)

    relative_time, bounce_template, bounce_spread = _aligned_template(
        time_s,
        state_matrix,
        align_times,
        bounce_indices,
        config,
    )
    _, clean_template, clean_spread = _aligned_template(
        time_s,
        state_matrix,
        align_times,
        clean_indices,
        config,
    )
    if bounce_template.size and clean_template.size:
        difference_template = bounce_template - clean_template
    else:
        difference_template = np.empty(0)

    counts = classification_table["capture_class"].value_counts()
    a = int(counts.get("bounce_present", 0))
    b = int(counts.get("clean_single_transition", 0))
    transient = int(counts.get("non_bounce_transient", 0))
    failed = int(counts.get("failed_transition", 0))
    uncertain = int(counts.get("uncertain", 0))

    valid_transition_denominator = a + b + transient
    population_summary = pd.DataFrame([{
        "total_captures": len(classification_table),
        "bounce_present_count_A": a,
        "clean_single_transition_count_B": b,
        "non_bounce_transient_count_T": transient,
        "failed_transition_count_F": failed,
        "uncertain_count_U": uncertain,
        "bounce_observation_rate_A_over_A_plus_B_plus_T": (
            a / valid_transition_denominator
            if valid_transition_denominator else math.nan
        ),
        "clean_reference_available": b >= config.minimum_clean_reference_captures,
        "bounce_model_available": a >= config.minimum_bounce_model_captures,
        "median_bounce_duration_s": (
            float(np.nanmedian(
                feature_table.loc[
                    feature_table["capture_class"] == "bounce_present",
                    "bounce_duration_s",
                ]
            )) if a else math.nan
        ),
        "median_extra_edge_count": (
            float(np.nanmedian(
                feature_table.loc[
                    feature_table["capture_class"] == "bounce_present",
                    "extra_edge_count",
                ]
            )) if a else math.nan
        ),
        "low_observability_edge_fraction": (
            float(
                feature_table["edge_timing_low_observability_count"].sum()
                / max(feature_table["extra_edge_count"].sum(), 1)
            )
        ),
        "observability_limited_capture_fraction": float(
            np.mean(feature_table["edge_count_is_observability_limited"])
        ),
    }])

    repeatability = _categorical_repeatability(feature_table, config)
    resampling, bootstrap_diagnostics = _bootstrap_stability(feature_table, config)
    clean_support = (
        "strongly_supported" if b >= 5
        else "supported" if b >= config.minimum_clean_reference_captures
        else "exploratory"
    )
    observability_support = (
        "supported"
        if classification_table["levels_identifiable"].mean() >= 0.80
        else "exploratory"
    )
    support_rank = {"exploratory": 0, "supported": 1, "strongly_supported": 2}
    combined = min(
        [repeatability, resampling, clean_support, observability_support],
        key=support_rank.get,
    )

    if a == 0:
        status = "no_relay_contact_bounce_population_available"
    elif a < config.minimum_bounce_model_captures:
        status = "relay_contact_bounce_detected_insufficient_ensemble"
    elif b < config.minimum_clean_reference_captures:
        status = "relay_contact_bounce_modeled_without_clean_transition_reference"
    else:
        status = "relay_contact_bounce_and_clean_transition_reference_modeled"

    diagnostics = {
        "sample_interval_s": dt,
        "sample_rate_hz": 1.0 / dt,
        "bounce_capture_indices": bounce_indices.tolist(),
        "clean_reference_capture_indices": clean_indices.tolist(),
        "bootstrap": bootstrap_diagnostics,
        "measurement_metadata": asdict(measurement_metadata),
        "configuration": asdict(config),
    }
    evidence = {
        "bounce_population_repeatability": repeatability,
        "resampling_stability": resampling,
        "clean_transition_reference_support": clean_support,
        "state_observability_support": observability_support,
        "provisional_combined_support": combined,
    }

    return RelayBounceResult(
        status=status,
        snr_evaluated=False,
        confidence_status="final_confidence_unavailable_snr_deferred",
        capture_classification=classification_table,
        bounce_features=feature_table,
        window_features=window_table,
        normalized_state_trajectories=state_matrix,
        state_validity_masks=validity_matrix,
        relative_template_time_s=relative_time,
        bounce_state_template=bounce_template,
        bounce_state_spread=bounce_spread,
        clean_state_reference=clean_template,
        clean_state_reference_spread=clean_spread,
        bounce_minus_clean_template=difference_template,
        population_summary=population_summary,
        evidence=evidence,
        diagnostics=diagnostics,
        notes=(
            "SNR is intentionally not calculated in v0.1.0.",
            "A clean single transition is negative only for this seed, not proof of whole-system health.",
            "AC analysis uses half-cycle-local observability and short subwindow derivative median/MAD features.",
            "Signed derivative averaging is forbidden because opposite bounce edges cancel.",
            "Full bounce requires unintended contact-state reversals after one intended transition.",
            "Transient-only activity is separated from full contact bounce.",
            "Zero-crossing events remain detectable only when the contact state is electrically observable; timing uncertainty is reported.",
            "Morphology labels describe behavior and do not uniquely identify a failed component.",
        ),
    )


# ---------------------------------------------------------------------------
# Synthetic validation
# ---------------------------------------------------------------------------

def _state_sequence(
    time_s: Array,
    initial_state: int,
    transitions: list[tuple[float, int]],
) -> Array:
    state = np.full(time_s.size, float(initial_state))
    for transition_time, new_state in transitions:
        state[time_s >= transition_time] = float(new_state)
    return state


def _synthetic_case(
    rng: np.random.Generator,
    family: str,
    *,
    sample_rate_hz: float = 200_000.0,
    duration_s: float = 0.060,
    line_frequency_hz: float = 60.0,
) -> tuple[Array, Array, Array | None, Array, RelayCaptureContext, str]:
    time_s = np.arange(int(round(sample_rate_hz * duration_s))) / sample_rate_hz
    marker = 0.018
    command = np.zeros_like(time_s)
    command[time_s >= marker] = 1.0
    operate = marker + 0.0010

    signal_type: SignalType = "ac"
    topology: Topology = "load_side_voltage"
    final_state: StateName = "closed"
    initial_state: StateName = "open"
    completed: bool | None = True
    expected = "clean_single_transition"
    source: Array | None
    spike_times: list[float] = []

    if family.startswith("dc_"):
        signal_type = "dc"
        source = None
        supply = np.full_like(time_s, 24.0)
    else:
        source = 170.0 * np.sin(2.0 * np.pi * line_frequency_hz * time_s + 0.37)
        supply = source

    if family in {"ac_clean_close", "dc_clean_close"}:
        transitions = [(operate, 1)]
    elif family in {"ac_bounce_close", "dc_bounce_close"}:
        transitions = [
            (operate, 1),
            (operate + 0.00022, 0),
            (operate + 0.00047, 1),
            (operate + 0.00073, 0),
            (operate + 0.00105, 1),
        ]
        expected = "bounce_present"
    elif family == "ac_bounce_open":
        final_state = "open"
        initial_state = "closed"
        command[:] = 1.0
        command[time_s >= marker] = 0.0
        transitions = [
            (operate, 0),
            (operate + 0.00020, 1),
            (operate + 0.00042, 0),
            (operate + 0.00068, 1),
            (operate + 0.00102, 0),
        ]
        expected = "bounce_present"
    elif family == "ac_transient_only":
        transitions = [(operate, 1)]
        spike_times = [operate + 0.00055, operate + 0.00092]
        expected = "non_bounce_transient"
    elif family == "ac_failed":
        transitions = []
        completed = False
        expected = "failed_transition"
    elif family == "ac_uncertain_multiple_commands":
        transitions = [(operate, 1)]
        command[time_s >= marker + 0.004] = 0.0
        command[time_s >= marker + 0.006] = 1.0
        completed = None
        expected = "uncertain"
    elif family == "ac_near_zero_bounce":
        # Shift first contact to the nearest source zero crossing after marker.
        zero_candidates = np.flatnonzero(np.signbit(source[1:]) != np.signbit(source[:-1])) + 1
        zero_time = float(time_s[zero_candidates[zero_candidates > np.searchsorted(time_s, marker)][0]])
        operate = zero_time - 0.00010
        transitions = [
            (operate, 1),
            (operate + 0.00016, 0),
            (operate + 0.00036, 1),
            (operate + 0.00058, 0),
            (operate + 0.00092, 1),
        ]
        expected = "bounce_present"
    else:
        raise ValueError(f"unknown synthetic family: {family}")

    initial_value = 1 if initial_state == "closed" else 0
    state = _state_sequence(time_s, initial_value, transitions)
    contact = state * supply

    for spike_time in spike_times:
        contact += 0.20 * np.max(np.abs(supply)) * np.exp(
            -((time_s - spike_time) / 0.000025) ** 2
        )

    noise_scale = 0.25 if signal_type == "ac" else 0.03
    contact += rng.normal(0.0, noise_scale, contact.size)
    if source is not None:
        source = source + rng.normal(0.0, 0.05, source.size)
    command = command + rng.normal(0.0, 0.002, command.size)

    context = RelayCaptureContext(
        capture_id=f"{family}_{rng.integers(1_000_000)}",
        signal_type=signal_type,
        measurement_topology=topology,
        commanded_final_state=final_state,
        initial_state=initial_state,
        transition_expected=True,
        transition_validated=True,
        transition_completed=completed,
        event_marker_time_s=None,
        line_frequency_hz=line_frequency_hz if signal_type == "ac" else None,
        operating_state="synthetic_relay_actuation",
        relay_or_contactor_id="synthetic_K1",
    )
    return time_s, contact, source, command, context, expected


def run_synthetic_validation(
    output_directory: str | Path,
    *,
    seed: int = 1159745,
    cases_per_family: int = 12,
) -> dict[str, Any]:
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    families = (
        "ac_clean_close",
        "dc_clean_close",
        "ac_bounce_close",
        "dc_bounce_close",
        "ac_bounce_open",
        "ac_transient_only",
        "ac_failed",
        "ac_uncertain_multiple_commands",
        "ac_near_zero_bounce",
    )

    contacts: list[Array] = []
    sources: list[Array] = []
    commands: list[Array] = []
    contexts: list[RelayCaptureContext] = []
    expected: list[str] = []
    family_names: list[str] = []
    time_s: Array | None = None

    for family in families:
        for _ in range(cases_per_family):
            t, contact, source, command, context, expected_class = _synthetic_case(
                rng, family
            )
            time_s = t
            contacts.append(contact)
            sources.append(
                source if source is not None else np.full_like(contact, np.nan)
            )
            commands.append(command)
            contexts.append(context)
            expected.append(expected_class)
            family_names.append(family)

    # The public API accepts one source array for all captures. DC rows are
    # replaced with a benign constant because the DC path ignores the source.
    source_matrix = np.vstack(sources)
    source_matrix[~np.isfinite(source_matrix)] = 1.0

    metadata = RelayMeasurementMetadata(
        contact_channel_name="CH2 contact/load voltage",
        contact_channel_units="V",
        source_reference_channel_name="CH1 source voltage",
        command_channel_name="CH3 relay command",
        scope_model="GW Instek GDS-3504",
        scope_bandwidth_hz=500e6,
        sample_rate_hz=200_000.0,
        probe_bandwidth_hz=100e6,
    )
    result = analyze_relay_contact_bounce(
        time_s,
        np.vstack(contacts),
        contexts,
        metadata,
        source_reference_captures=source_matrix,
        command_captures=np.vstack(commands),
        config=RelayBounceConfig(),
    )

    validation = result.capture_classification.copy()
    validation["synthetic_family"] = family_names
    validation["expected_class"] = expected
    validation["class_match"] = validation["capture_class"] == validation["expected_class"]
    validation = validation.merge(
        result.bounce_features,
        on=["capture_id", "capture_class"],
        how="left",
        suffixes=("", "_feature"),
    )

    validation.to_csv(
        output_directory / "relay_contact_bounce_v010_validation_cases.csv",
        index=False,
    )
    result.capture_classification.to_csv(
        output_directory / "relay_contact_bounce_v010_capture_classification.csv",
        index=False,
    )
    result.bounce_features.to_csv(
        output_directory / "relay_contact_bounce_v010_bounce_features.csv",
        index=False,
    )
    result.window_features.to_csv(
        output_directory / "relay_contact_bounce_v010_half_cycle_window_features.csv",
        index=False,
    )
    result.population_summary.to_csv(
        output_directory / "relay_contact_bounce_v010_population_summary.csv",
        index=False,
    )

    overall = {
        "seed_version": "0.1.0",
        "case_count": int(len(validation)),
        "classification_matches": int(validation["class_match"].sum()),
        "classification_match_rate": float(validation["class_match"].mean()),
        "class_counts": result.capture_classification["capture_class"].value_counts().to_dict(),
        "status": result.status,
        "snr_evaluated": result.snr_evaluated,
        "scope_warning": (
            "Synthetic validation only. Not bench calibration, field validation, "
            "relay qualification, or standards certification."
        ),
    }
    (output_directory / "relay_contact_bounce_v010_summary.json").write_text(
        json.dumps(
            {"validation": overall, "result": result.summary_dict()},
            indent=2,
            default=float,
        ),
        encoding="utf-8",
    )

    # Example AC bounce waveform.
    example_index = family_names.index("ac_bounce_close")
    plt.figure(figsize=(11, 5.5))
    plt.plot(time_s, source_matrix[example_index], label="Source reference")
    plt.plot(time_s, contacts[example_index], label="Contact/load signal")
    plt.xlabel("Time (s)")
    plt.ylabel("Voltage (V)")
    plt.title("Synthetic AC relay make-bounce capture")
    plt.legend()
    plt.tight_layout()
    plt.savefig(
        output_directory / "relay_contact_bounce_v010_example_ac_waveform.png",
        dpi=180,
    )
    plt.close()

    # Normalized state trajectories.
    plt.figure(figsize=(11, 5.5))
    for idx, trajectory in enumerate(result.normalized_state_trajectories):
        cls = result.capture_classification.loc[idx, "capture_class"]
        alpha = 0.22 if cls == "bounce_present" else 0.10
        plt.plot(time_s, trajectory, alpha=alpha)
    plt.xlabel("Time (s)")
    plt.ylabel("Normalized closed-state coordinate")
    plt.title("Relay contact-state trajectories")
    plt.tight_layout()
    plt.savefig(
        output_directory / "relay_contact_bounce_v010_state_trajectories.png",
        dpi=180,
    )
    plt.close()

    # Population templates aligned to first intended contact.
    plt.figure(figsize=(11, 5.5))
    if result.bounce_state_template.size:
        plt.plot(
            result.relative_template_time_s,
            result.bounce_state_template,
            linewidth=2.2,
            label="Bounce population median",
        )
    if result.clean_state_reference.size:
        plt.plot(
            result.relative_template_time_s,
            result.clean_state_reference,
            linewidth=2.2,
            label="Clean transition reference",
        )
    plt.xlabel("Time relative to first intended contact (s)")
    plt.ylabel("Normalized closed-state coordinate")
    plt.title("Bounce versus clean transition population")
    plt.legend()
    plt.tight_layout()
    plt.savefig(
        output_directory / "relay_contact_bounce_v010_population_templates.png",
        dpi=180,
    )
    plt.close()

    # Half-cycle short-window derivative statistics for the same AC example.
    example_id = contexts[example_index].capture_id
    example_windows = result.window_features[
        result.window_features["capture_id"] == example_id
    ]
    plt.figure(figsize=(11, 5.5))
    plt.plot(
        example_windows["window_mid_time_s"],
        example_windows["median_abs_state_derivative_per_s"],
        label="Window median |d(state)/dt|",
    )
    plt.plot(
        example_windows["window_mid_time_s"],
        example_windows["mad_abs_state_derivative_per_s"],
        label="Window MAD |d(state)/dt|",
    )
    plt.xlabel("Time (s)")
    plt.ylabel("Normalized state rate (1/s)")
    plt.title("Half-cycle-local derivative window statistics")
    plt.legend()
    plt.tight_layout()
    plt.savefig(
        output_directory / "relay_contact_bounce_v010_window_derivative_features.png",
        dpi=180,
    )
    plt.close()

    return overall


def package_bundle(directory: str | Path, zip_path: str | Path) -> Path:
    directory = Path(directory)
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.resolve() != zip_path.resolve():
                archive.write(path, arcname=path.relative_to(directory))
    return zip_path


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    print(json.dumps(run_synthetic_validation(here), indent=2))
