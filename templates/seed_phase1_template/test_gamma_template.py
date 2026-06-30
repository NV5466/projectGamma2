"""Architecture smoke tests. These do not validate physical localization."""

import unittest
import numpy as np

from gamma_inference_template import (
    AttachmentSite,
    BackboneGraph,
    GraphEdge,
    GraphNode,
    HealthyBaseline,
    Hypothesis,
    HypothesisScorer,
    InferenceTemplate,
    MeasurementSpec,
    ParameterSpec,
    SeedLibrary,
    SeedModel,
    choose_next_measurement_by_hypothesis_separation,
)


class ToyBackend:
    """Deterministic placeholder used only to exercise the plumbing."""

    def simulate(self, *, graph, measurement, seed, attachment, parameters, input_waveform):
        n = input_waveform.size
        t = np.arange(n) * measurement.sample_interval
        if attachment.site_kind == "node":
            attach_node = attachment.site_id
        else:
            edge = graph.edges[attachment.site_id]
            attach_node = edge.node_b
        distance = graph.shortest_path_distance(measurement.node_id, attach_node)
        if distance is None:
            return np.full(n, np.nan)
        attenuation = 1.0 / (1.0 + distance)
        tau = parameters["tau"]
        if seed.family == "RC":
            signature = 1.0 - np.exp(-t / tau)
        else:
            signature = np.exp(-t / tau)
        return attenuation * signature


class GammaTemplateTests(unittest.TestCase):
    def setUp(self):
        nodes = [
            GraphNode("S", kind="source"),
            GraphNode("J"),
            GraphNode("P1", kind="measurement"),
            GraphNode("P2", kind="measurement"),
            GraphNode("A", kind="boundary"),
        ]
        edges = [
            GraphEdge("E1", "S", "J"),
            GraphEdge("E2", "J", "P1"),
            GraphEdge("E3", "J", "P2"),
            GraphEdge("E4", "J", "A"),
        ]
        self.graph = BackboneGraph(nodes, edges)
        self.measurement = MeasurementSpec("M1", "P1", "voltage", 0.001)
        seeds = [
            SeedModel(
                "rc_demo",
                "RC",
                (ParameterSpec("tau", 0.005, 0.2, "s", nominal=0.05),),
                order=1,
            ),
            SeedModel(
                "rl_demo",
                "RL",
                (ParameterSpec("tau", 0.005, 0.2, "s", nominal=0.05),),
                order=1,
            ),
        ]
        self.library = SeedLibrary(seeds)
        self.backend = ToyBackend()

        rng = np.random.default_rng(7)
        t = np.arange(200) * 0.001
        mean = 0.5 * (1.0 - np.exp(-t / 0.05))
        mode = np.sin(2 * np.pi * 20 * t)
        captures = np.vstack([
            mean + rng.normal(0, 0.004, t.size) + rng.normal(0, 0.01) * mode
            for _ in range(40)
        ])
        self.baseline = HealthyBaseline.fit(captures, variance_threshold=0.9, max_modes=5)
        self.input_waveform = np.ones(200)

    def test_graph_reachability(self):
        self.assertEqual(self.graph.reachable_nodes("P1"), {"S", "J", "P1", "P2", "A"})
        self.assertEqual(self.graph.shortest_path_distance("P1", "A"), 2)

    def test_sites_have_no_model_location_rules(self):
        sites = self.graph.candidate_attachment_sites("P1")
        self.assertIn(AttachmentSite("node", "A"), sites)
        self.assertIn(AttachmentSite("edge", "E4"), sites)
        template = InferenceTemplate(
            graph=self.graph,
            seed_library=self.library,
            forward_backend=self.backend,
        )
        pairs = template.enumerate_hypothesis_sites(self.measurement)
        pair_set = {(seed.seed_id, site.site_kind, site.site_id) for seed, site in pairs}
        self.assertIn(("rc_demo", "node", "A"), pair_set)
        self.assertIn(("rl_demo", "node", "A"), pair_set)

    def test_baseline_decomposition_reconstructs_residual(self):
        waveform = self.baseline.mean_waveform + 0.03 * self.baseline.noise_basis[:, 0]
        coordinates, known, unknown = self.baseline.decompose(waveform)
        residual = waveform - self.baseline.mean_waveform
        np.testing.assert_allclose(known + unknown, residual, atol=1e-10)
        self.assertEqual(coordinates.ndim, 1)

    def test_out_of_bounds_parameter_is_rejected(self):
        seed = self.library.get("rc_demo")
        with self.assertRaises(ValueError):
            seed.validate_parameters({"tau": 1.0})

    def test_evaluate_returns_sorted_scores(self):
        hypotheses = [
            Hypothesis("rc_demo", AttachmentSite("node", "A"), {"tau": 0.05}),
            Hypothesis("rl_demo", AttachmentSite("node", "A"), {"tau": 0.05}),
        ]
        observed = self.backend.simulate(
            graph=self.graph,
            measurement=self.measurement,
            seed=self.library.get("rc_demo"),
            attachment=AttachmentSite("node", "A"),
            parameters={"tau": 0.05},
            input_waveform=self.input_waveform,
        )
        template = InferenceTemplate(
            graph=self.graph,
            seed_library=self.library,
            forward_backend=self.backend,
            scorer=HypothesisScorer(noise_excursion_weight=0.0),
        )
        ranked = template.evaluate(
            measurement=self.measurement,
            baseline=self.baseline,
            observed_waveform=observed,
            input_waveform=self.input_waveform,
            hypotheses=hypotheses,
        )
        self.assertEqual(ranked[0][0].seed_id, "rc_demo")
        self.assertLessEqual(ranked[0][1].total, ranked[1][1].total)

    def test_next_measurement_returns_ranking(self):
        hypotheses = [
            Hypothesis("rc_demo", AttachmentSite("node", "A"), {"tau": 0.05}),
            Hypothesis("rl_demo", AttachmentSite("node", "A"), {"tau": 0.05}),
        ]
        candidates = [
            self.measurement,
            MeasurementSpec("M2", "P2", "voltage", 0.001),
        ]
        ranked = choose_next_measurement_by_hypothesis_separation(
            graph=self.graph,
            candidate_measurements=candidates,
            top_hypotheses=hypotheses,
            seed_library=self.library,
            forward_backend=self.backend,
            input_waveform=self.input_waveform,
        )
        self.assertEqual(len(ranked), 2)
        self.assertGreaterEqual(ranked[0][1], ranked[1][1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
