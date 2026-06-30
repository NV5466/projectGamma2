
# Gamma / ElectroStat EMI EFT Burst Seed v0.1.0

## Purpose

This worker analyzes electrical-fast-transient / burst measurements as a
nested dynamic system:

1. acquisition observability,
2. individual fast-pulse morphology,
3. aligned explicit pulse template and pulse residuals,
4. post-pulse real-decay and oscillatory matrix-pencil modes,
5. pulse-train timing, missing events, and amplitude drift,
6. burst grouping and burst-scale summary.

It reports **EFT-like measured behavior**, not IEC compliance and not a guilty
component.

## Deliberate v0.1.0 exclusion

SNR is not calculated yet.

Every result contains:

```text
snr_evaluated: false
confidence_status: final_confidence_unavailable_snr_deferred
```

The worker uses categorical provisional evidence:

- rejected
- exploratory
- supported
- strongly supported

These are not probabilities.

## Why two acquisition scales are accepted

A full burst cannot generally be stored at maximum real-time sample rate with
the GDS-3504 record depth. The worker therefore accepts:

- **detail captures** at the highest available real-time sample rate for pulse
  rise time, width, overshoot, residuals, and post-pulse modes;
- an optional **overview capture** at a lower sample rate for pulse spacing,
  missing pulses, amplitude drift, burst duration, and burst recurrence.

The two time arrays are independent.

## GDS-3504 metadata

The supplied adapter starts with:

```text
scope: GW Instek GDS-3504
analog bandwidth: 500 MHz
ADC: 8 bit
acquisition mode: real time
```

The actual probe model, probe bandwidth, input termination, enabled bandwidth
limit, coupling, and vertical rails must be recorded for real measurements.

At 4 GSa/s, a nominal 5 ns rise contains 20 sample intervals. The seed reports
this as acquisition observability evidence. It does not convert it into a
calibrated confidence percentage.

## Mathematical structure

An individual pulse is retained empirically. The post-pulse response is
represented as repeated dynamic modes:

```math
r_i(t)=\sum_m A_{im}e^{\alpha_m t}\cos(\omega_m t+\phi_{im})+\epsilon_i(t)
```

Each pulse window is fitted independently. Matching modes are then clustered
across pulses. Raw captures are never concatenated into one false continuous
time series.

For a complex continuous-time pole:

```math
p_m=\alpha_m+j\omega_m
```

the worker reports:

```math
f_m=\frac{|\omega_m|}{2\pi},\qquad
\tau_m=-\frac{1}{\alpha_m}
```

for stable modes with `alpha_m < 0`.

## Public entry point

```python
result = analyze_emi_eft_burst(
    detail_time_s,
    detail_captures_v,
    metadata,
    overview_time_s=overview_time_s,
    overview_waveform_v=overview_waveform_v,
)
```

Important outputs:

- `result.pulse_features`
- `result.pulse_template_time_s`
- `result.pulse_template_v`
- `result.pulse_residuals_v`
- `result.modes`
- `result.mode_clusters`
- `result.train_summary`
- `result.burst_summary`
- `result.evidence`
- `result.summary_dict()`

## Run validation

```bash
python gamma_emi_eft_burst_seed_v010.py
pytest -q
```

The validation harness generates eight synthetic families:

- nominal 100 kHz burst,
- nominal 5 kHz burst,
- nonoscillatory pulse burst,
- amplitude-drifting burst,
- missing-pulse burst,
- single fast pulse without overview,
- broad-step adversarial negative,
- no-event negative.

Synthetic results validate implementation behavior only. They do not estimate
field sensitivity, specificity, IEC conformity, or calibrated confidence.

## Known limitations

- SNR and noise-aware feature uncertainty are deferred.
- Fixed robust activity multipliers are provisional.
- Very low-amplitude ring modes may be unstable without later SNR gating.
- Probe loading and fixture transfer functions are metadata only in v0.1.0.
- The pulse source and measured DUT response may be convolved.
- Matrix-pencil modes are effective modes, not automatic component values.
- Overview captures may miss pulse morphology by design.
- Hardware bench validation is still required.

## Verified v0.1.0 results

- 24/24 expected synthetic status outcomes matched.
- 6/6 unit and regression tests passed.
- Median synthetic ring-frequency relative error: 0.003757%.
- SNR remained disabled in every validation run.

See `VALIDATION_REPORT.md` for the full breakdown.
