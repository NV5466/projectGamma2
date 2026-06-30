from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence
import math

import numpy as np
import pandas as pd


RELAY_WEIGHTS = {
    "command_lock": 0.30,
    "coil_corroboration": 0.25,
    "compact_burst": 0.20,
    "settling_decay": 0.15,
    "rail_switching": 0.10,
}

SENSOR_WEIGHTS_V3 = {
    "threshold_occupancy": 0.15,
    "threshold_crossings": 0.20,
    "state_sensor_consistency": 0.35,
    "sensor_timing": 0.20,
    "position_lock": 0.10,
}

@dataclass
class Capture:
    t: np.ndarray
    state_v: np.ndarray
    command_v: Optional[np.ndarray] = None
    coil_i: Optional[np.ndarray] = None
    sensor_v: Optional[np.ndarray] = None
    position: Optional[np.ndarray] = None
    label: str = ""


@dataclass
class Episode:
    start_idx: int
    end_idx: int
    edge_indices: np.ndarray

    @property
    def edge_count(self) -> int:
        return int(len(self.edge_indices))


@dataclass
class SensorCandidate:
    source: str
    start_s: float
    end_s: float
    first_edge_s: float
    duration_s: float
    edge_count: int
    threshold_occupancy: float
    threshold_crossings: float
    state_sensor_consistency: float
    sensor_timing: float
    event_position: Optional[float]

    @property
    def local_score(self) -> float:
        weights = {
            "threshold_occupancy": 0.15,
            "threshold_crossings": 0.25,
            "state_sensor_consistency": 0.35,
            "sensor_timing": 0.25,
        }
        values = {
            "threshold_occupancy": self.threshold_occupancy,
            "threshold_crossings": self.threshold_crossings,
            "state_sensor_consistency": self.state_sensor_consistency,
            "sensor_timing": self.sensor_timing,
        }
        return sum(weights[key] * values[key] for key in weights)


@dataclass
class RelayEvidence:
    start_s: float
    end_s: float
    first_edge_s: float
    duration_s: float
    edge_count: int
    command_lock: Optional[float]
    coil_corroboration: Optional[float]
    compact_burst: Optional[float]
    settling_decay: Optional[float]
    rail_switching: Optional[float]
    coil_event_s: Optional[float]


@dataclass
class CaptureV4Result:
    label: str
    relay: RelayEvidence
    sensor: Optional[SensorCandidate]
    sensor_source: str
    sensor_precedes_coil: Optional[float]
    coil_precedes_contact: Optional[float]


def clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))

def robust_binary_state(
    voltage: np.ndarray,
    low_threshold: Optional[float] = None,
    high_threshold: Optional[float] = None,
) -> tuple[np.ndarray, float, float, float, float]:
    """
    Convert a noisy digital-voltage waveform into a Schmitt-style binary state.

    Returns:
        state, low_threshold, high_threshold, estimated_low_rail, estimated_high_rail
    """
    v = np.asarray(voltage, dtype=float)
    low_rail = float(np.quantile(v, 0.05))
    high_rail = float(np.quantile(v, 0.95))
    span = max(high_rail - low_rail, 1e-9)

    if low_threshold is None:
        low_threshold = low_rail + 0.40 * span
    if high_threshold is None:
        high_threshold = low_rail + 0.60 * span

    state = np.zeros_like(v, dtype=np.int8)
    state[0] = int(v[0] >= (low_threshold + high_threshold) / 2.0)

    for i in range(1, len(v)):
        if v[i] >= high_threshold:
            state[i] = 1
        elif v[i] <= low_threshold:
            state[i] = 0
        else:
            state[i] = state[i - 1]

    return state, float(low_threshold), float(high_threshold), low_rail, high_rail

def detect_instability_episodes(
    t: np.ndarray,
    state: np.ndarray,
    max_interedge_gap_s: float = 0.006,
    min_edges: int = 3,
    padding_s: float = 0.0005,
) -> list[Episode]:
    """
    Cluster rapid state reversals into instability episodes.
    """
    edge_indices = np.flatnonzero(np.diff(state) != 0) + 1
    if len(edge_indices) == 0:
        return []

    edge_times = t[edge_indices]
    split_points = np.flatnonzero(np.diff(edge_times) > max_interedge_gap_s) + 1
    groups = np.split(edge_indices, split_points)

    dt = float(np.median(np.diff(t)))
    pad = max(1, int(round(padding_s / dt)))

    episodes: list[Episode] = []
    for group in groups:
        if len(group) < min_edges:
            continue
        start = max(0, int(group[0]) - pad)
        end = min(len(t) - 1, int(group[-1]) + pad)
        episodes.append(Episode(start, end, group))

    return episodes

def choose_primary_episode(episodes: Sequence[Episode], t: np.ndarray) -> Optional[Episode]:
    if not episodes:
        return None
    # Prefer many edges, then longer burst.
    return max(
        episodes,
        key=lambda ep: (
            ep.edge_count,
            float(t[ep.end_idx] - t[ep.start_idx]),
        ),
    )

def edge_times(t: np.ndarray, waveform: np.ndarray, threshold: Optional[float] = None) -> np.ndarray:
    x = np.asarray(waveform, dtype=float)
    if threshold is None:
        threshold = float((np.quantile(x, 0.05) + np.quantile(x, 0.95)) / 2.0)
    state = x >= threshold
    idx = np.flatnonzero(np.diff(state.astype(np.int8)) != 0) + 1
    return t[idx]

def nearest_time_score(reference_time: float, candidates: np.ndarray, tau_s: float) -> Optional[float]:
    if candidates is None or len(candidates) == 0:
        return None
    dt = float(np.min(np.abs(candidates - reference_time)))
    return clip01(math.exp(-dt / max(tau_s, 1e-12)))

def rank_correlation(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2 or len(y) < 2:
        return 0.0
    xr = pd.Series(x).rank(method="average").to_numpy()
    yr = pd.Series(y).rank(method="average").to_numpy()
    if np.std(xr) < 1e-12 or np.std(yr) < 1e-12:
        return 0.0
    return float(np.corrcoef(xr, yr)[0, 1])

def moving_average(x: np.ndarray, samples: int) -> np.ndarray:
    samples = max(1, int(samples))
    if samples == 1:
        return np.asarray(x, dtype=float)
    kernel = np.ones(samples, dtype=float) / samples
    return np.convolve(np.asarray(x, dtype=float), kernel, mode="same")

def robust_mad(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    med = float(np.median(x))
    return float(np.median(np.abs(x - med))) + 1e-12

def significant_level_event_times_v3(
    t: np.ndarray,
    x: np.ndarray,
    smoothing_s: float = 0.00025,
    fraction_of_span: float = 0.18,
    min_abs_span: float = 0.02,
    min_snr: float = 20.0,
) -> np.ndarray:
    """
    Detect meaningful analog level transitions, but reject flat/noise-only channels.
    """
    dt = float(np.median(np.diff(t)))
    smoothed = moving_average(x, max(1, round(smoothing_s / dt)))

    baseline_n = max(20, int(0.15 * len(smoothed)))
    baseline_segment = smoothed[:baseline_n]
    baseline = float(np.median(baseline_segment))
    noise_sigma = 1.4826 * robust_mad(baseline_segment)

    lo = float(np.quantile(smoothed, 0.05))
    hi = float(np.quantile(smoothed, 0.95))
    span = hi - lo

    if span < min_abs_span or span < min_snr * noise_sigma:
        return np.array([], dtype=float)

    upward_excursion = hi - baseline
    downward_excursion = baseline - lo

    if upward_excursion >= downward_excursion:
        active = smoothed >= baseline + fraction_of_span * span
    else:
        active = smoothed <= baseline - fraction_of_span * span

    idx = np.flatnonzero(np.diff(active.astype(np.int8)) != 0) + 1
    return t[idx]

def inferred_sensor_threshold(
    sensor: np.ndarray,
    state_edge_indices: np.ndarray,
) -> float:
    """
    Estimate the effective switching threshold from the analog sensor values
    observed exactly where the measured discrete state reverses.
    """
    if len(state_edge_indices) > 0:
        values = sensor[state_edge_indices]
        return float(np.median(values))
    return float((np.quantile(sensor, 0.05) + np.quantile(sensor, 0.95)) / 2.0)

def nearest_preceding_time(reference_time: float, candidates: np.ndarray, max_lag_s: float) -> Optional[float]:
    candidates = np.asarray(candidates, dtype=float)
    preceding = candidates[(candidates <= reference_time) & ((reference_time - candidates) <= max_lag_s)]
    if len(preceding) == 0:
        return None
    return float(preceding[-1])

def greedy_time_match(
    reference_times: np.ndarray,
    candidate_times: np.ndarray,
    tolerance_s: float,
) -> tuple[int, list[float]]:
    """
    One-to-one nearest matching. A single analog crossing cannot explain ten state edges.
    """
    refs = list(np.asarray(reference_times, dtype=float))
    candidates = list(np.asarray(candidate_times, dtype=float))
    used = set()
    lags: list[float] = []

    for ref in refs:
        best_j = None
        best_lag = None
        for j, candidate in enumerate(candidates):
            if j in used:
                continue
            lag = abs(candidate - ref)
            if lag <= tolerance_s and (best_lag is None or lag < best_lag):
                best_j = j
                best_lag = lag
        if best_j is not None and best_lag is not None:
            used.add(best_j)
            lags.append(float(best_lag))

    return len(lags), lags

def sensor_state_consistency_score(
    sensor: np.ndarray,
    state: np.ndarray,
    threshold: float,
    i0: int,
    i1: int,
    exclusion_band: float,
) -> float:
    """
    Tests whether analog sensor amplitude actually predicts measured discrete state.
    This rejects an unrelated analog line that merely crosses a threshold nearby in time.
    """
    s = np.asarray(sensor[i0 : i1 + 1], dtype=float)
    y = np.asarray(state[i0 : i1 + 1], dtype=np.int8)

    usable = np.abs(s - threshold) > exclusion_band
    if np.sum(usable) < 10 or len(np.unique(y[usable])) < 2:
        return 0.0

    pred_rising = (s[usable] >= threshold).astype(np.int8)
    accuracy_rising = float(np.mean(pred_rising == y[usable]))
    accuracy_falling = float(np.mean((1 - pred_rising) == y[usable]))
    directional_accuracy = max(accuracy_rising, accuracy_falling)
    accuracy_score = clip01(2.0 * (directional_accuracy - 0.5))

    high_values = s[(y == 1) & usable]
    low_values = s[(y == 0) & usable]
    if len(high_values) < 3 or len(low_values) < 3:
        separation_score = 0.0
    else:
        separation = abs(float(np.median(high_values) - np.median(low_values)))
        pooled_noise = 1.4826 * (
            robust_mad(high_values) + robust_mad(low_values)
        ) / 2.0
        effect = separation / max(pooled_noise, 1e-12)
        separation_score = clip01(1.0 - math.exp(-effect / 3.0))

    return clip01(0.65 * accuracy_score + 0.35 * separation_score)

def analyze_sensor_candidate(
    t: np.ndarray,
    discrete_v: np.ndarray,
    sensor_v: np.ndarray,
    position: Optional[np.ndarray],
    source: str,
) -> Optional[SensorCandidate]:
    state, _, _, _, _ = robust_binary_state(discrete_v)
    episodes = detect_instability_episodes(
        t,
        state,
        max_interedge_gap_s=0.006,
        min_edges=3,
        padding_s=0.00035,
    )
    episode = choose_primary_episode(episodes, t)
    if episode is None:
        return None

    i0, i1 = episode.start_idx, episode.end_idx
    measured_edges = t[episode.edge_indices]
    threshold = inferred_sensor_threshold(sensor_v, episode.edge_indices)

    dt = float(np.median(np.diff(t)))
    expand = int(round(0.003 / dt))
    expanded0 = max(0, i0 - expand)
    expanded1 = min(len(t) - 1, i1 + expand)
    local_sensor = sensor_v[expanded0 : expanded1 + 1]
    local_span = max(
        float(np.quantile(local_sensor, 0.95) - np.quantile(local_sensor, 0.05)),
        1e-9,
    )
    band = 0.12 * local_span

    occupancy = clip01(
        float(np.mean(np.abs(sensor_v[i0 : i1 + 1] - threshold) <= band))
    )

    smooth_sensor = moving_average(sensor_v, max(1, round(0.00018 / dt)))
    analog_crossings = edge_times(t, smooth_sensor, threshold=threshold)
    local_crossings = analog_crossings[
        (analog_crossings >= t[i0] - 0.0005)
        & (analog_crossings <= t[i1] + 0.0005)
    ]

    matched_count, matched_lags = greedy_time_match(
        measured_edges,
        local_crossings,
        tolerance_s=0.00055,
    )
    crossing_score = clip01(matched_count / max(episode.edge_count, 1))

    if matched_lags:
        timing_score = clip01(
            crossing_score
            * math.exp(-float(np.median(matched_lags)) / 0.00025)
        )
    else:
        timing_score = 0.0

    consistency = sensor_state_consistency_score(
        sensor=sensor_v,
        state=state,
        threshold=threshold,
        i0=i0,
        i1=i1,
        exclusion_band=0.35 * band,
    )

    event_position = None
    if position is not None:
        event_position = float(position[episode.edge_indices[0]])

    return SensorCandidate(
        source=source,
        start_s=float(t[i0]),
        end_s=float(t[i1]),
        first_edge_s=float(measured_edges[0]),
        duration_s=float(t[i1] - t[i0]),
        edge_count=episode.edge_count,
        threshold_occupancy=occupancy,
        threshold_crossings=crossing_score,
        state_sensor_consistency=consistency,
        sensor_timing=timing_score,
        event_position=event_position,
    )

def analyze_relay_evidence(capture: Capture) -> Optional[RelayEvidence]:
    t = capture.t
    state, _, _, low_rail, high_rail = robust_binary_state(capture.state_v)
    episodes = detect_instability_episodes(
        t,
        state,
        max_interedge_gap_s=0.006,
        min_edges=3,
        padding_s=0.00035,
    )
    episode = choose_primary_episode(episodes, t)
    if episode is None:
        return None

    i0, i1 = episode.start_idx, episode.end_idx
    measured_edges = t[episode.edge_indices]
    first_edge = float(measured_edges[0])
    duration = float(t[i1] - t[i0])
    intervals = np.diff(measured_edges)

    command_lock = None
    if capture.command_v is not None:
        command_edges = edge_times(t, capture.command_v)
        command_lock = nearest_time_score(first_edge, command_edges, tau_s=0.003)

    coil_event = None
    coil_corroboration = None
    if capture.coil_i is not None:
        coil_events = significant_level_event_times_v3(t, capture.coil_i)
        if len(coil_events) > 0:
            coil_event = nearest_preceding_time(first_edge, coil_events, max_lag_s=0.010)
            if coil_event is not None:
                coil_corroboration = clip01(
                    math.exp(-(first_edge - coil_event) / 0.003)
                )

    compact = clip01(math.exp(-duration / 0.012))

    if len(intervals) >= 2:
        rho = rank_correlation(np.arange(len(intervals)), intervals)
        decay = clip01((rho + 1.0) / 2.0)
    else:
        decay = None

    rail_span = max(high_rail - low_rail, 1e-9)
    ep_v = capture.state_v[i0 : i1 + 1]
    nearest_rail_error = np.minimum(np.abs(ep_v - low_rail), np.abs(ep_v - high_rail))
    rails = clip01(
        math.exp(-float(np.median(nearest_rail_error)) / (0.08 * rail_span))
    )

    return RelayEvidence(
        start_s=float(t[i0]),
        end_s=float(t[i1]),
        first_edge_s=first_edge,
        duration_s=duration,
        edge_count=episode.edge_count,
        command_lock=command_lock,
        coil_corroboration=coil_corroboration,
        compact_burst=compact,
        settling_decay=decay,
        rail_switching=rails,
        coil_event_s=coil_event,
    )

def analyze_capture_v4(capture: Capture) -> Optional[CaptureV4Result]:
    relay = analyze_relay_evidence(capture)
    if relay is None:
        return None

    candidates: list[SensorCandidate] = []

    if capture.sensor_v is not None:
        state_candidate = analyze_sensor_candidate(
            t=capture.t,
            discrete_v=capture.state_v,
            sensor_v=capture.sensor_v,
            position=capture.position,
            source="measured_state",
        )
        if state_candidate is not None:
            candidates.append(state_candidate)

        if capture.command_v is not None:
            command_candidate = analyze_sensor_candidate(
                t=capture.t,
                discrete_v=capture.command_v,
                sensor_v=capture.sensor_v,
                position=capture.position,
                source="upstream_command",
            )
            if command_candidate is not None:
                candidates.append(command_candidate)

    sensor = max(candidates, key=lambda c: c.local_score) if candidates else None
    sensor_source = "none" if sensor is None else sensor.source

    sensor_precedes_coil = None
    coil_precedes_contact = None

    # Compound interpretation only makes sense when the sensor-like instability
    # is observed on an upstream line distinct from the contact waveform.
    if (
        sensor is not None
        and sensor.source == "upstream_command"
        and relay.coil_event_s is not None
    ):
        lag1 = relay.coil_event_s - sensor.first_edge_s
        if lag1 >= 0:
            sensor_precedes_coil = clip01(math.exp(-lag1 / 0.004))

        lag2 = relay.first_edge_s - relay.coil_event_s
        if lag2 >= 0:
            coil_precedes_contact = clip01(math.exp(-lag2 / 0.003))

    return CaptureV4Result(
        label=capture.label,
        relay=relay,
        sensor=sensor,
        sensor_source=sensor_source,
        sensor_precedes_coil=sensor_precedes_coil,
        coil_precedes_contact=coil_precedes_contact,
    )

def mean_available(values: Sequence[Optional[float]]) -> Optional[float]:
    valid = [float(v) for v in values if v is not None and not np.isnan(v)]
    return None if not valid else float(np.mean(valid))

def weighted_score(features: dict[str, Optional[float]], weights: dict[str, float]) -> tuple[float, float]:
    numerator = 0.0
    denominator = 0.0
    total_weight = sum(weights.values())

    for name, weight in weights.items():
        value = features.get(name)
        if value is not None and not np.isnan(value):
            numerator += weight * clip01(float(value))
            denominator += weight

    if denominator == 0:
        return float("nan"), 0.0

    return numerator / denominator, denominator / total_weight

def position_lock_score(event_positions: Sequence[Optional[float]]) -> Optional[float]:
    valid = np.asarray(
        [p for p in event_positions if p is not None and not np.isnan(p)],
        dtype=float,
    )
    if len(valid) < 2:
        return None

    spread = float(np.std(valid))
    scale = max(float(np.ptp(valid)), 0.02)
    return clip01(math.exp(-spread / scale))

def aggregate_v4(name: str, captures: Sequence[Capture]) -> tuple[pd.DataFrame, dict, dict]:
    rows = []
    sensor_positions = []
    relay_durations = []
    relay_edges = []
    sensor_durations = []
    sensor_edges = []

    for capture in captures:
        result = analyze_capture_v4(capture)
        if result is None:
            continue

        relay = result.relay
        sensor = result.sensor

        relay_durations.append(relay.duration_s)
        relay_edges.append(relay.edge_count)

        if sensor is not None:
            sensor_durations.append(sensor.duration_s)
            sensor_edges.append(sensor.edge_count)
            sensor_positions.append(sensor.event_position)

        rows.append(
            {
                "Case": name,
                "label": result.label,
                "sensor_source": result.sensor_source,

                "relay_duration_s": relay.duration_s,
                "relay_edge_count": relay.edge_count,
                "command_lock": relay.command_lock,
                "coil_corroboration": relay.coil_corroboration,
                "compact_burst": relay.compact_burst,
                "settling_decay": relay.settling_decay,
                "rail_switching": relay.rail_switching,

                "sensor_duration_s": None if sensor is None else sensor.duration_s,
                "sensor_edge_count": None if sensor is None else sensor.edge_count,
                "threshold_occupancy": None if sensor is None else sensor.threshold_occupancy,
                "threshold_crossings": None if sensor is None else sensor.threshold_crossings,
                "state_sensor_consistency": None if sensor is None else sensor.state_sensor_consistency,
                "sensor_timing": None if sensor is None else sensor.sensor_timing,
                "sensor_event_position": None if sensor is None else sensor.event_position,

                "sensor_precedes_coil": result.sensor_precedes_coil,
                "coil_precedes_contact": result.coil_precedes_contact,
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError(f"No usable captures for {name}")

    def colmean(column: str) -> Optional[float]:
        return mean_available(frame[column].tolist())

    relay_aggregate = {
        "command_lock": colmean("command_lock"),
        "coil_corroboration": colmean("coil_corroboration"),
        "compact_burst": colmean("compact_burst"),
        "settling_decay": colmean("settling_decay"),
        "rail_switching": colmean("rail_switching"),
    }

    sensor_aggregate = {
        "threshold_occupancy": colmean("threshold_occupancy"),
        "threshold_crossings": colmean("threshold_crossings"),
        "state_sensor_consistency": colmean("state_sensor_consistency"),
        "sensor_timing": colmean("sensor_timing"),
        "position_lock": position_lock_score(sensor_positions),
    }

    relay_score, relay_coverage = weighted_score(relay_aggregate, RELAY_WEIGHTS)
    sensor_score, sensor_coverage = weighted_score(sensor_aggregate, SENSOR_WEIGHTS_V3)

    sensor_to_coil = colmean("sensor_precedes_coil")
    coil_to_contact = colmean("coil_precedes_contact")

    # Repeatability of each layer.
    relay_repeatability = clip01(
        math.exp(
            -(
                np.std(relay_durations) / (np.mean(relay_durations) + 1e-12)
                + np.std(relay_edges) / (np.mean(relay_edges) + 1e-12)
            )
        )
    )

    sensor_repeatability = None
    if len(sensor_durations) >= 2:
        sensor_repeatability = clip01(
            math.exp(
                -(
                    np.std(sensor_durations) / (np.mean(sensor_durations) + 1e-12)
                    + np.std(sensor_edges) / (np.mean(sensor_edges) + 1e-12)
                )
            )
        )

    compound_terms = [
        sensor_score if sensor_score >= 0.55 else None,
        relay_score if relay_score >= 0.55 else None,
        sensor_to_coil,
        coil_to_contact,
        relay_repeatability,
        sensor_repeatability,
    ]

    if all(term is not None and not np.isnan(term) for term in compound_terms):
        compound_score = float(
            np.exp(np.mean(np.log(np.clip(compound_terms, 1e-9, 1.0))))
        )
        compound_coverage = 1.0
    else:
        compound_score = float("nan")
        compound_coverage = sum(
            term is not None and not np.isnan(term) for term in compound_terms
        ) / len(compound_terms)

    source_counts = frame["sensor_source"].value_counts().to_dict()
    dominant_source = max(source_counts, key=source_counts.get)

    # Classification with compound taking precedence when the full chain is supported.
    if not np.isnan(compound_score) and compound_score >= 0.60:
        classification = "Compound: sensor chatter → coil response → relay/contact bounce"
    else:
        classification = classify_scores(relay_score, sensor_score, compound_score)

    summary = {
        "Case": name,
        "Captures generated": len(captures),
        "Captures analyzed": len(frame),
        "Dominant sensor source": dominant_source,
        "Relay score": relay_score,
        "Sensor score": sensor_score,
        "Compound score": compound_score,
        "Relay coverage": relay_coverage,
        "Sensor coverage": sensor_coverage,
        "Compound coverage": compound_coverage,
        "Classification": classification,
    }

    evidence = {
        **{f"relay_{k}": v for k, v in relay_aggregate.items()},
        **{f"sensor_{k}": v for k, v in sensor_aggregate.items()},
        "sensor_precedes_coil": sensor_to_coil,
        "coil_precedes_contact": coil_to_contact,
        "relay_repeatability": relay_repeatability,
        "sensor_repeatability": sensor_repeatability,
        "dominant_sensor_source": dominant_source,
    }

    return frame, summary, evidence


if __name__ == "__main__":
    print(
        "DIH Hunger Games V4 core loaded. "
        "Create Capture objects and pass repeated captures to aggregate_v4()."
    )
