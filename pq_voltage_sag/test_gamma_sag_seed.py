import unittest
import numpy as np

from gamma_sag_seed_v01 import (
    SagConfig,
    fit_sag_baseline,
    make_reference_waveform,
    make_healthy_population,
    make_synthetic_case,
    run_sag_seed,
)


class SagSeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dt = 0.001
        cls.t = np.arange(0.0, 2.0, cls.dt)
        cls.rng = np.random.default_rng(230626)
        cls.reference = make_reference_waveform(cls.t)
        healthy = make_healthy_population(cls.reference, cls.dt, 70, cls.rng)
        cls.config = SagConfig(
            candidate_windows=(41, 81, 161, 241),
            enter_sigma=3.0,
            exit_sigma=1.25,
            enter_persistence_s=0.020,
            exit_persistence_s=0.030,
            minimum_event_s=0.035,
        )
        cls.baseline = fit_sag_baseline(healthy, cls.dt, cls.config)

    def test_clean_sag_detected(self):
        wave, _ = make_synthetic_case(self.reference, self.dt, self.rng, "clean_sag")
        result = run_sag_seed(self.baseline, wave, self.config)
        self.assertIn(result.status, {"clean_sag_supported", "distorted_sag_supported"})
        self.assertGreaterEqual(len(result.events), 1)

    def test_offset_step_not_clean_sag(self):
        wave, _ = make_synthetic_case(self.reference, self.dt, self.rng, "offset_step")
        result = run_sag_seed(self.baseline, wave, self.config)
        self.assertNotEqual(result.status, "clean_sag_supported")

    def test_swell_rejected(self):
        wave, _ = make_synthetic_case(self.reference, self.dt, self.rng, "swell")
        result = run_sag_seed(self.baseline, wave, self.config)
        self.assertEqual(result.status, "rejected")

    def test_short_dip_rejected_by_persistence(self):
        wave, _ = make_synthetic_case(self.reference, self.dt, self.rng, "short_dip")
        result = run_sag_seed(self.baseline, wave, self.config)
        self.assertEqual(result.status, "rejected")

    def test_amplitude_over_slope_has_time_units(self):
        wave, _ = make_synthetic_case(self.reference, self.dt, self.rng, "clean_sag")
        result = run_sag_seed(self.baseline, wave, self.config)
        event = result.events[0]
        self.assertGreaterEqual(event.entry_timescale_s, 0.0)
        self.assertGreaterEqual(event.recovery_timescale_s, 0.0)
        self.assertGreater(event.deficit_area_s, 0.0)


if __name__ == "__main__":
    unittest.main()
