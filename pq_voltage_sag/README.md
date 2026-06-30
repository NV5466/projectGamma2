# Gamma / ElectroStat Sag Seed v0.1

This bundle implements the agreed synthetic sag worker:

1. align the raw capture to the WaveCompare healthy collective;
2. let the sag seed test several analysis windows;
3. estimate local affine gain, offset, correlation, and RMS ratio;
4. require local gain and RMS to fall abnormally together;
5. apply statistical hysteresis and temporal persistence;
6. construct a bounded event block;
7. measure depth, duration, deficit area, entry/recovery slopes, and amplitude-over-slope timescales;
8. separate ordinary healthy residual modes from unexplained residual structure.

## Synthetic validation

- Healthy training captures: 100
- Validation runs: 900 (100 per scenario)
- Candidate windows: (41, 81, 161, 241)
- Entry/exit thresholds: 3.00σ / 1.25σ
- Entry/exit persistence: 20 ms / 30 ms

The validation is model-designed and synthetic. It proves the implementation behaves coherently on controlled examples; it does not validate field power-quality performance or establish standard thresholds.
