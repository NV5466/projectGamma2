"""Minimal WaveCompare 2 -> Harmonic Distortion Seed adapter."""

from gamma_harmonic_distortion_seed_v010 import (
    HarmonicConfig,
    analyze_wavecompare2_harmonics,
)

config = HarmonicConfig(
    minimum_frequency_hz=50.0,
    maximum_frequency_hz=70.0,
    maximum_harmonic_order=15,
)

evidence = analyze_wavecompare2_harmonics(
    expected_waveform=expected_waveform,  # singular WC2 output
    new_capture=new_capture,
    sample_interval_s=dt,
    old_captures=old_captures,           # optional, stored only
    config=config,
)

print(evidence.summary_dict())
