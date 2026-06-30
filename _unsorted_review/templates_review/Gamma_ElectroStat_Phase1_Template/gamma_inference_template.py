"""Gamma / ElectroStat phase-1 inference template.

This module deliberately does *not* attempt to recreate a complete circuit.
It defines the mathematical and software grammar for combining:

1. a coarse, known connection backbone (the roads),
2. location-agnostic seed model families (possible electrical behaviors),
3. a WaveCompare-derived healthy waveform and residual/noise subspace,
4. a forward-model backend (later SPICE or another simulator), and
5. ranked hypotheses over seed type, parameters, and unknown attachment site.

Nothing in the seed model schema assigns a model family to an "allowed"
location. Candidate sites come only from graph connectivity and the selected
measurement context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol, Sequence
from collections import deque
import math
import numpy as np

Array = np.ndarray


# ---------------------------------------------------------------------------
# Coarse connection backbone
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GraphNode:
    node_id: str
    label: str = ""
    kind: str = "junction"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    node_a: str
    node_b: str
    label: str = ""
    kind: str = "connection"
    directed: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AttachmentSite:
    """A latent site at which an unknown effective behavior may attach."""

    site_kind: str  # "node" or "edge"
    site_id: str

    def __post_init__(self) -> None:
        if self.site_kind not in {"node", "edge"}:
            raise ValueError("site_kind must be 'node' or 'edge'")


class BackboneGraph:
    """Small graph implementation for the known roads/intersections only."""

    def __init__(self, nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]):
        node_list = list(nodes)
        edge_list = list(edges)
        self.nodes = {n.node_id: n for n in node_list}
        self.edges = {e.edge_id: e for e in edge_list}

        if len(self.nodes) != len(node_list):
            raise ValueError("Duplicate node_id detected")
        if len(self.edges) != len(edge_list):
            raise ValueError("Duplicate edge_id detected")

        self._adj: dict[str, list[tuple[str, str]]] = {
            node_id: [] for node_id in self.nodes
        }
        for edge in self.edges.values():
            if edge.node_a not in self.nodes or edge.node_b not in self.nodes:
                raise ValueError(
                    f"Edge {edge.edge_id!r} references an unknown node"
                )
            self._adj[edge.node_a].append((edge.node_b, edge.edge_id))
            if not edge.directed:
                self._adj[edge.node_b].append((edge.node_a, edge.edge_id))

    def reachable_nodes(self, start_node: str) -> set[str]:
        if start_node not in self.nodes:
            raise KeyError(f"Unknown start node: {start_node}")
        seen = {start_node}
        queue = deque([start_node])
        while queue:
            current = queue.popleft()
            for neighbor, _ in self._adj[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        return seen

    def reachable_edges(self, start_node: str) -> set[str]:
        nodes = self.reachable_nodes(start_node)
        return {
            edge.edge_id
            for edge in self.edges.values()
            if edge.node_a in nodes and edge.node_b in nodes
        }

    def shortest_path_distance(self, start_node: str, end_node: str) -> int | None:
        if start_node not in self.nodes or end_node not in self.nodes:
            raise KeyError("Unknown start or end node")
        queue = deque([(start_node, 0)])
        seen = {start_node}
        while queue:
            current, distance = queue.popleft()
            if current == end_node:
                return distance
            for neighbor, _ in self._adj[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append((neighbor, distance + 1))
        return None

    def candidate_attachment_sites(
        self,
        measurement_node: str,
        *,
        include_nodes: bool = True,
        include_edges: bool = True,
    ) -> list[AttachmentSite]:
        """Return every connected site that could influence the measurement.

        This method imposes no seed-family/location rule. It only enforces the
        known connection skeleton: disconnected sites are not candidates.
        """
        reachable_nodes = self.reachable_nodes(measurement_node)
        reachable_edges = self.reachable_edges(measurement_node)
        sites: list[AttachmentSite] = []
        if include_nodes:
            sites.extend(
                AttachmentSite("node", node_id)
                for node_id in sorted(reachable_nodes)
            )
        if include_edges:
            sites.extend(
                AttachmentSite("edge", edge_id)
                for edge_id in sorted(reachable_edges)
            )
        return sites


# ---------------------------------------------------------------------------
# Measurement and healthy statistical model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MeasurementSpec:
    measurement_id: str
    node_id: str
    quantity: str  # e.g. voltage, current
    sample_interval: float
    reference_node_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sample_interval <= 0:
            raise ValueError("sample_interval must be positive")
        if not self.quantity:
            raise ValueError("quantity cannot be empty")


@dataclass(frozen=True)
class HealthyBaseline:
    """Expected waveform plus learned normal residual/noise geometry."""

    mean_waveform: Array
    pointwise_std: Array
    noise_basis: Array  # shape: (samples, modes)
    noise_score_mean: Array
    noise_score_cov: Array
    explained_variance_ratio: Array
    captures_used: int

    @classmethod
    def fit(
        cls,
        aligned_healthy_captures: Array,
        *,
        variance_threshold: float = 0.95,
        max_modes: int | None = None,
        epsilon: float = 1e-10,
    ) -> "HealthyBaseline":
        captures = np.asarray(aligned_healthy_captures, dtype=float)
        if captures.ndim != 2:
            raise ValueError("aligned_healthy_captures must be 2D")
        if captures.shape[0] < 2:
            raise ValueError("At least two healthy captures are required")
        if not 0 < variance_threshold <= 1:
            raise ValueError("variance_threshold must lie in (0, 1]")
        if not np.isfinite(captures).all():
            raise ValueError("Healthy captures must be finite before fitting")

        mean_waveform = captures.mean(axis=0)
        pointwise_std = captures.std(axis=0, ddof=1)
        centered = captures - mean_waveform

        # SVD of residual rows. Right singular vectors are waveform modes.
        _, singular_values, vt = np.linalg.svd(centered, full_matrices=False)
        variance = singular_values**2
        total = float(variance.sum())
        if total <= epsilon:
            mode_count = 0
            ratios = np.empty(0)
            basis = np.empty((captures.shape[1], 0))
            scores = np.empty((captures.shape[0], 0))
        else:
            ratios_all = variance / total
            cumulative = np.cumsum(ratios_all)
            mode_count = int(np.searchsorted(cumulative, variance_threshold) + 1)
            if max_modes is not None:
                mode_count = min(mode_count, max_modes)
            basis = vt[:mode_count].T
            ratios = ratios_all[:mode_count]
            scores = centered @ basis

        if mode_count == 0:
            score_mean = np.empty(0)
            score_cov = np.empty((0, 0))
        elif mode_count == 1:
            score_mean = scores.mean(axis=0)
            score_cov = np.array([[float(np.var(scores[:, 0], ddof=1))]])
        else:
            score_mean = scores.mean(axis=0)
            score_cov = np.cov(scores, rowvar=False, ddof=1)

        return cls(
            mean_waveform=mean_waveform,
            pointwise_std=np.maximum(pointwise_std, epsilon),
            noise_basis=basis,
            noise_score_mean=score_mean,
            noise_score_cov=score_cov,
            explained_variance_ratio=ratios,
            captures_used=captures.shape[0],
        )

    @classmethod
    def from_wavecompare(
        cls,
        aligned_stack: Array,
        *,
        collective_waveform: Array | None = None,
        variance_threshold: float = 0.95,
        max_modes: int | None = None,
    ) -> "HealthyBaseline":
        """Adapter for WaveCompare 2's aligned capture stack."""
        baseline = cls.fit(
            aligned_stack,
            variance_threshold=variance_threshold,
            max_modes=max_modes,
        )
        if collective_waveform is None:
            return baseline
        collective = np.asarray(collective_waveform, dtype=float)
        if collective.shape != baseline.mean_waveform.shape:
            raise ValueError("collective_waveform has the wrong shape")
        return cls(
            mean_waveform=collective,
            pointwise_std=baseline.pointwise_std,
            noise_basis=baseline.noise_basis,
            noise_score_mean=baseline.noise_score_mean,
            noise_score_cov=baseline.noise_score_cov,
            explained_variance_ratio=baseline.explained_variance_ratio,
            captures_used=baseline.captures_used,
        )

    def decompose(self, waveform: Array) -> tuple[Array, Array, Array]:
        """Return (noise coordinates, known-noise reconstruction, unknown residual)."""
        y = np.asarray(waveform, dtype=float)
        if y.shape != self.mean_waveform.shape:
            raise ValueError("waveform has the wrong shape")
        residual = y - self.mean_waveform
        if self.noise_basis.shape[1] == 0:
            coordinates = np.empty(0)
            known_noise = np.zeros_like(residual)
        else:
            coordinates = self.noise_basis.T @ residual
            known_noise = self.noise_basis @ coordinates
        unknown = residual - known_noise
        return coordinates, known_noise, unknown


# ---------------------------------------------------------------------------
# Location-agnostic seed library
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParameterSpec:
    name: str
    lower: float
    upper: float
    unit: str = ""
    nominal: float | None = None
    log_scale: bool = False

    def __post_init__(self) -> None:
        if not self.lower < self.upper:
            raise ValueError(f"Invalid bounds for {self.name}")
        if self.nominal is not None and not self.lower <= self.nominal <= self.upper:
            raise ValueError(f"Nominal value for {self.name} is outside bounds")
        if self.log_scale and self.lower <= 0:
            raise ValueError("Log-scale parameters require a positive lower bound")

    def normalized_distance_from_nominal(self, value: float) -> float:
        if not self.lower <= value <= self.upper:
            return math.inf
        nominal = self.nominal
        if nominal is None:
            nominal = math.sqrt(self.lower * self.upper) if self.log_scale else (
                0.5 * (self.lower + self.upper)
            )
        if self.log_scale:
            span = math.log(self.upper) - math.log(self.lower)
            return (math.log(value) - math.log(nominal)) / max(span, 1e-12)
        span = self.upper - self.lower
        return (value - nominal) / span


@dataclass(frozen=True)
class SeedModel:
    seed_id: str
    family: str
    parameters: tuple[ParameterSpec, ...]
    order: int
    complexity: float = 1.0
    description: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def validate_parameters(self, values: Mapping[str, float]) -> None:
        expected = {p.name for p in self.parameters}
        supplied = set(values)
        if expected != supplied:
            missing = expected - supplied
            extra = supplied - expected
            raise ValueError(f"Parameter mismatch; missing={missing}, extra={extra}")
        for spec in self.parameters:
            value = float(values[spec.name])
            if not np.isfinite(value):
                raise ValueError(f"Non-finite parameter {spec.name}")
            if not spec.lower <= value <= spec.upper:
                raise ValueError(
                    f"{spec.name}={value} outside [{spec.lower}, {spec.upper}]"
                )


class SeedLibrary:
    def __init__(self, seeds: Iterable[SeedModel] = ()): 
        self._seeds: dict[str, SeedModel] = {}
        for seed in seeds:
            self.register(seed)

    def register(self, seed: SeedModel) -> None:
        if seed.seed_id in self._seeds:
            raise ValueError(f"Duplicate seed_id: {seed.seed_id}")
        self._seeds[seed.seed_id] = seed

    def get(self, seed_id: str) -> SeedModel:
        return self._seeds[seed_id]

    def all(self) -> tuple[SeedModel, ...]:
        return tuple(self._seeds.values())


# ---------------------------------------------------------------------------
# Forward-model and scoring interfaces
# ---------------------------------------------------------------------------

class ForwardModelBackend(Protocol):
    """Implemented later by SPICE, a reduced-order solver, or another engine."""

    def simulate(
        self,
        *,
        graph: BackboneGraph,
        measurement: MeasurementSpec,
        seed: SeedModel,
        attachment: AttachmentSite,
        parameters: Mapping[str, float],
        input_waveform: Array,
    ) -> Array:
        ...


@dataclass(frozen=True)
class Hypothesis:
    seed_id: str
    attachment: AttachmentSite
    parameters: Mapping[str, float]


@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    unknown_residual_energy: float
    known_noise_excursion: float
    parameter_penalty: float
    complexity_penalty: float
    noise_coordinates: Array
    predicted_waveform: Array
    unknown_residual: Array


class HypothesisScorer:
    """Score a physical hypothesis while respecting learned normal noise."""

    def __init__(
        self,
        *,
        unknown_weight: float = 1.0,
        noise_excursion_weight: float = 0.15,
        parameter_weight: float = 0.05,
        complexity_weight: float = 0.01,
        epsilon: float = 1e-9,
    ) -> None:
        self.unknown_weight = unknown_weight
        self.noise_excursion_weight = noise_excursion_weight
        self.parameter_weight = parameter_weight
        self.complexity_weight = complexity_weight
        self.epsilon = epsilon

    def score(
        self,
        *,
        observed_waveform: Array,
        predicted_waveform: Array,
        baseline: HealthyBaseline,
        seed: SeedModel,
        parameters: Mapping[str, float],
    ) -> ScoreBreakdown:
        observed = np.asarray(observed_waveform, dtype=float)
        predicted = np.asarray(predicted_waveform, dtype=float)
        if observed.shape != baseline.mean_waveform.shape:
            raise ValueError("observed_waveform has the wrong shape")
        if predicted.shape != observed.shape:
            raise ValueError("predicted_waveform has the wrong shape")
        seed.validate_parameters(parameters)

        # Residual remaining after the physical candidate has explained the signal.
        residual = observed - predicted
        if baseline.noise_basis.shape[1] == 0:
            noise_coordinates = np.empty(0)
            known_noise = np.zeros_like(residual)
            noise_excursion = 0.0
        else:
            noise_coordinates = baseline.noise_basis.T @ residual
            known_noise = baseline.noise_basis @ noise_coordinates
            centered_scores = noise_coordinates - baseline.noise_score_mean
            cov = baseline.noise_score_cov
            regularized = cov + self.epsilon * np.eye(cov.shape[0])
            noise_excursion = float(
                centered_scores @ np.linalg.pinv(regularized) @ centered_scores
            ) / max(cov.shape[0], 1)

        unknown = residual - known_noise
        standardized_unknown = unknown / (baseline.pointwise_std + self.epsilon)
        unknown_energy = float(np.mean(standardized_unknown**2))

        parameter_terms = []
        for spec in seed.parameters:
            distance = spec.normalized_distance_from_nominal(
                float(parameters[spec.name])
            )
            parameter_terms.append(distance**2)
        parameter_penalty = float(np.mean(parameter_terms)) if parameter_terms else 0.0

        n = observed.size
        complexity_penalty = float(seed.complexity * math.log(max(n, 2)) / n)

        total = (
            self.unknown_weight * unknown_energy
            + self.noise_excursion_weight * noise_excursion
            + self.parameter_weight * parameter_penalty
            + self.complexity_weight * complexity_penalty
        )
        return ScoreBreakdown(
            total=float(total),
            unknown_residual_energy=unknown_energy,
            known_noise_excursion=noise_excursion,
            parameter_penalty=parameter_penalty,
            complexity_penalty=complexity_penalty,
            noise_coordinates=noise_coordinates,
            predicted_waveform=predicted,
            unknown_residual=unknown,
        )


class InferenceTemplate:
    """Orchestrates graph enumeration, forward simulation, and scoring."""

    def __init__(
        self,
        *,
        graph: BackboneGraph,
        seed_library: SeedLibrary,
        forward_backend: ForwardModelBackend,
        scorer: HypothesisScorer | None = None,
    ) -> None:
        self.graph = graph
        self.seed_library = seed_library
        self.forward_backend = forward_backend
        self.scorer = scorer or HypothesisScorer()

    def enumerate_hypothesis_sites(
        self, measurement: MeasurementSpec
    ) -> list[tuple[SeedModel, AttachmentSite]]:
        sites = self.graph.candidate_attachment_sites(measurement.node_id)
        return [(seed, site) for seed in self.seed_library.all() for site in sites]

    def evaluate(
        self,
        *,
        measurement: MeasurementSpec,
        baseline: HealthyBaseline,
        observed_waveform: Array,
        input_waveform: Array,
        hypotheses: Sequence[Hypothesis],
    ) -> list[tuple[Hypothesis, ScoreBreakdown]]:
        results: list[tuple[Hypothesis, ScoreBreakdown]] = []
        for hypothesis in hypotheses:
            seed = self.seed_library.get(hypothesis.seed_id)
            seed.validate_parameters(hypothesis.parameters)
            predicted = self.forward_backend.simulate(
                graph=self.graph,
                measurement=measurement,
                seed=seed,
                attachment=hypothesis.attachment,
                parameters=hypothesis.parameters,
                input_waveform=np.asarray(input_waveform, dtype=float),
            )
            score = self.scorer.score(
                observed_waveform=observed_waveform,
                predicted_waveform=predicted,
                baseline=baseline,
                seed=seed,
                parameters=hypothesis.parameters,
            )
            results.append((hypothesis, score))
        return sorted(results, key=lambda pair: pair[1].total)


def fuse_independent_measurement_scores(
    score_sets: Sequence[Sequence[tuple[Hypothesis, ScoreBreakdown]]],
) -> list[tuple[Hypothesis, float]]:
    """Fuse the same hypothesis across multiple measurement locations.

    Scores are added as a first approximation to negative log-likelihood fusion.
    A later version should use calibrated likelihoods and cross-location covariance.
    """
    totals: dict[tuple[str, str, str, tuple[tuple[str, float], ...]], float] = {}
    canonical: dict[
        tuple[str, str, str, tuple[tuple[str, float], ...]], Hypothesis
    ] = {}
    for score_set in score_sets:
        for hypothesis, score in score_set:
            key = (
                hypothesis.seed_id,
                hypothesis.attachment.site_kind,
                hypothesis.attachment.site_id,
                tuple(sorted((k, float(v)) for k, v in hypothesis.parameters.items())),
            )
            totals[key] = totals.get(key, 0.0) + score.total
            canonical[key] = hypothesis
    return sorted(
        [(canonical[key], total) for key, total in totals.items()],
        key=lambda pair: pair[1],
    )


def choose_next_measurement_by_hypothesis_separation(
    *,
    graph: BackboneGraph,
    candidate_measurements: Sequence[MeasurementSpec],
    top_hypotheses: Sequence[Hypothesis],
    seed_library: SeedLibrary,
    forward_backend: ForwardModelBackend,
    input_waveform: Array,
) -> list[tuple[MeasurementSpec, float]]:
    """Rank next probe points by disagreement among current top hypotheses."""
    ranked: list[tuple[MeasurementSpec, float]] = []
    for measurement in candidate_measurements:
        predictions = []
        for hypothesis in top_hypotheses:
            seed = seed_library.get(hypothesis.seed_id)
            prediction = forward_backend.simulate(
                graph=graph,
                measurement=measurement,
                seed=seed,
                attachment=hypothesis.attachment,
                parameters=hypothesis.parameters,
                input_waveform=np.asarray(input_waveform, dtype=float),
            )
            predictions.append(np.asarray(prediction, dtype=float))
        if len(predictions) < 2:
            separation = 0.0
        else:
            stack = np.vstack(predictions)
            separation = float(np.mean(np.var(stack, axis=0, ddof=1)))
        ranked.append((measurement, separation))
    return sorted(ranked, key=lambda pair: pair[1], reverse=True)
