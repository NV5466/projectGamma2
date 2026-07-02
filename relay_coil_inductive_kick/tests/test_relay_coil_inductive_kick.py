import numpy as np

from relay_coil_inductive_kick.classifier import classify_inductive_kick
from relay_coil_inductive_kick.generator import generate_inductive_case, generate_inductive_cases


def test_true_inductive_cases_pass():
    cases = generate_inductive_cases(25, seed=1234, source_mode="current")
    positives = 0
    for time_s, source, victim, meta in cases:
        decision = classify_inductive_kick(time_s, source, victim, source_mode=meta.source_mode)
        positives += int(decision.is_relay_coil_inductive_kick)
    assert positives >= 23


def test_voltage_source_mode_passes():
    time_s, source, victim, meta = generate_inductive_case(seed=99, source_mode="voltage")
    decision = classify_inductive_kick(time_s, source, victim, source_mode="voltage")
    assert decision.is_relay_coil_inductive_kick


def test_repeated_source_edges_reject_like_bounce_boundary():
    # Minimal boundary fixture only. This is not a replacement for the real
    # high_speed_input_bounce seed. It verifies that repeated source events
    # cannot sneak through as inductive kickback.
    fs = 250_000.0
    duration_s = 0.020
    t = np.arange(int(fs * duration_s)) / fs
    source = np.zeros_like(t)
    victim = np.zeros_like(t)

    event_times = [0.0060, 0.00635, 0.0068, 0.0074]
    rng = np.random.default_rng(7)

    for n, et in enumerate(event_times):
        idx = np.argmin(np.abs(t - et))
        amp = 1.0 if n % 2 == 0 else -0.9
        source[idx:min(idx+3, len(source))] += amp
        tail = np.maximum(t - et, 0.0)
        victim += 0.4 * np.exp(-6000.0 * tail) * np.cos(2*np.pi*18000.0*tail) * (tail > 0)

    source += rng.normal(0, 0.002, size=len(t))
    victim += rng.normal(0, 0.01, size=len(t))

    decision = classify_inductive_kick(t, source, victim, source_mode="voltage")
    assert not decision.is_relay_coil_inductive_kick
    assert decision.features["source_event_count"] > 3


def test_uncoupled_noise_rejects():
    fs = 250_000.0
    duration_s = 0.020
    rng = np.random.default_rng(12)
    t = np.arange(int(fs * duration_s)) / fs
    source = rng.normal(0, 0.01, size=len(t))
    victim = rng.normal(0, 0.01, size=len(t))
    source[int(0.007 * fs)] = 3.0
    # victim has unrelated spike elsewhere
    victim[int(0.014 * fs)] = 1.0
    decision = classify_inductive_kick(t, source, victim, source_mode="voltage")
    assert not decision.is_relay_coil_inductive_kick
