# EMI EFT Burst Seed v0.1.0 Validation Report

## Outcome

The `emi_eft_burst` worker is implemented as a dual-scale, hierarchical seed for Gamma / ElectroStat.

- Synthetic validation cases: **24**
- Synthetic families: **8**
- Expected status matches: **24/24**
- Status match rate: **100.0%**
- Median oscillatory-mode frequency relative error: **0.003757%**
- Median repetition-frequency relative error: **0.000000%**
- SNR evaluated: **No**
- Unit/regression tests: **6 passed**

These results are synthetic implementation validation only. They do not represent field calibration, IEC conformity, sensitivity, specificity, or calibrated confidence.

## Implemented analysis chain

1. Validate real-time sampling, time monotonicity, clipping metadata, analog bandwidth, probe bandwidth, and samples across the nominal 5 ns edge.
2. Detect fast transient regions using robust amplitude and derivative activity gates.
3. Extract pulse morphology: rise time, half-height width, fall time, peak, area, squared-voltage integral, rebound, secondary peaks, baseline shift, and recovery.
4. Align pulse-local windows while retaining the explicit median waveform and every residual.
5. Fit post-pulse tails with matrix pencil modes, then cluster shared real-decay and oscillatory poles across repeated pulses.
6. Independently compare the dominant oscillatory mode against a derivative-FFT estimate.
7. Analyze the lower-rate overview capture for pulse interval, repetition frequency, missing events, amplitude drift, burst grouping, and burst duration.
8. Return categorical provisional evidence only. Final confidence remains unavailable until SNR is added.

## GDS-3504 behavior

The adapter is configured around the GW Instek GDS-3504 and leaves probe-specific fields explicit. At 4 GSa/s, a nominal 5 ns rise spans 20 sample intervals. The worker treats this as acquisition observability evidence, not a guarantee of waveform truth.

The required real measurement metadata includes:

- actual sample rate and time array,
- scope and probe bandwidth,
- enabled bandwidth limit,
- acquisition mode,
- input impedance and coupling,
- probe ratio/model,
- vertical rails or clipping limits,
- averaging state.

## Synthetic families

| case_family                   |   cases |   status_matches |   status_match_rate |   median_ring_relative_error |   median_repetition_relative_error | snr_ever_evaluated   |
|:------------------------------|--------:|-----------------:|--------------------:|-----------------------------:|-----------------------------------:|:---------------------|
| amplitude_drift_burst         |       3 |                3 |                   1 |                  3.17307e-05 |                        2.61934e-15 | False                |
| broad_step_negative           |       3 |                3 |                   1 |                nan           |                        2.61934e-15 | False                |
| missing_pulses                |       3 |                3 |                   1 |                  8.82969e-05 |                        0.00497512  | False                |
| no_event_negative             |       3 |                3 |                   1 |                nan           |                      nan           | False                |
| nominal_100khz                |       3 |                3 |                   1 |                  2.17546e-05 |                        2.61934e-15 | False                |
| nominal_5khz                  |       3 |                3 |                   1 |                  0.000124065 |                        0.00373599  | False                |
| nonoscillatory_burst          |       3 |                3 |                   1 |                nan           |                        2.61934e-15 | False                |
| single_fast_pulse_no_overview |       3 |                3 |                   1 |                  0.493687    |                      nan           | False                |

## Important decisions

- A single fast pulse is reported as `fast_pulse_detected_insufficient_ensemble`, not as a confirmed EFT burst.
- A fast pulse without an overview capture can support pulse morphology but cannot resolve burst timing.
- SNR is deliberately absent in v0.1.0. The result always reports `snr_evaluated: false`.
- The pulse source is preserved empirically. Matrix pencil is applied to the post-pulse response rather than forced across the complete event.
- The raw waveform, aligned pulse windows, template, and residuals remain explicit.
- Pole clusters describe effective dynamic modes, not automatically identified physical components.

## Fixed during validation

A regression test now prevents pulse-template baseline estimation from subtracting part of the leading edge. The template reuses the pre-event baseline found during segmentation, preserving the measured peak scale.

The independent spectral check differentiates the post-pulse tail before FFT analysis. This suppresses the large nonoscillatory recovery term that otherwise masks the faster ring.

## Deferred work

- SNR and noise-aware uncertainty calibration.
- Field capture validation using actual GDS-3504 exports.
- Probe/fixture de-embedding.
- Threshold calibration against known EFT generator settings.
- Integration into the current Gamma seed registry and WaveCompare data model.
