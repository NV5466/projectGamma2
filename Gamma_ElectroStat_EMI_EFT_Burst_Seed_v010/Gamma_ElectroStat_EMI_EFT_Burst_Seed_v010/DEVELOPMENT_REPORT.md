# Gamma / ElectroStat EMI EFT Burst Seed v0.1.0

## Development verdict

The first implementation is complete as a synthetic research prototype.

It treats EFT as a hierarchy rather than one universal waveform:

1. acquisition observability,
2. individual fast-pulse geometry,
3. aligned empirical pulse template and residuals,
4. post-pulse dynamic modes,
5. pulse-train timing and drift,
6. burst-level consequence.

SNR is deliberately excluded from this version. Every result carries
`snr_evaluated = false`, and the worker refuses to emit calibrated confidence
percentages.

## Core design decisions

### Preserve the explicit waveform

The measured and aligned pulse waveforms remain first-class outputs. Rise time,
width, integrals, pole clusters, and burst statistics are compressed
descriptions only.

### Separate segmentation from decomposition

A physical pulse window is detected once. Its geometry and post-pulse modes are
then analyzed inside that window. Derivative crossings are not counted as
separate events.

### Do not concatenate captures

Every pulse capture is fitted independently. Matching matrix-pencil poles are
clustered across captures. Capture boundaries are never treated as real time
continuity.

### Dual-scale acquisition

The worker accepts high-rate detail captures and an optional lower-rate
overview capture. This avoids demanding that one oscilloscope record preserve
nanosecond morphology and millisecond burst duration simultaneously.

### Confidence stays provisional

Version 0.1.0 uses four evidence sources:

- acquisition observability,
- repeatability,
- bootstrap resampling stability,
- independent-method agreement.

These produce categorical support only. Noise-aware SNR and calibrated
probabilities are later gates.

## Implemented measurements

### Individual pulse

- polarity,
- signed peak and peak-to-peak voltage,
- interpolated 10–90% rise time,
- 50% width,
- fall time,
- maximum absolute `dv/dt`,
- signed area,
- squared-voltage integral,
- overshoot/rebound,
- secondary peak count,
- baseline shift,
- recovery time,
- template residual fraction.

### Post-pulse dynamics

For each pulse, the tail is fitted independently using a matrix pencil. Stable
real and oscillatory modes are retained and clustered across pulses.

The output includes:

- frequency,
- decay rate,
- time constant,
- four-time-constant settling estimate,
- damping ratio,
- amplitude,
- phase,
- model order,
- reconstruction NRMSE,
- mode occurrence fraction.

### Train and burst

The optional overview capture provides:

- pulse arrival times,
- pulse interval,
- repetition frequency,
- interval spread,
- expected-frequency match,
- missing-pulse inference,
- burst grouping,
- burst duration,
- amplitude drift through each burst.

## Acquisition behavior

Acquisition validity is checked before feature interpretation:

- uniform increasing timestamps,
- sample interval and sampling rate,
- effective analog/probe bandwidth,
- samples across nominal 5 ns edge,
- real-time versus equivalent-time acquisition,
- clipping against supplied vertical rails,
- averaging/bandwidth-limit metadata.

A high sampling rate does not automatically create high confidence. It only
contributes to observability.

## Synthetic validation

- Version: 0.1.0
- Families: 8
- Cases: 24
- Intended-status matches: 24/24
- Status match rate: 1.000
- Median planted ring-frequency relative error: 5.7099e-05
- Median repetition-frequency relative error: 2.61934e-15
- SNR evaluated: false

The validation families were:

- amplitude_drift_burst
- broad_step_negative
- missing_pulses
- no_event_negative
- nominal_100khz
- nominal_5khz
- nonoscillatory_burst
- single_fast_pulse_no_overview

These results validate implementation behavior on synthetic cases only. They do
not estimate field sensitivity, field specificity, standards conformity, or
calibrated confidence.

## What worked

- Fast pulse morphology and slow train behavior remain separated.
- Explicit pulse templates and residuals are preserved.
- Repeated oscillatory modes are recovered by independent fits and clustering.
- The synthetic 5 kHz and 100 kHz overview trains are resolved.
- Missing-pulse and amplitude-drift evidence remain visible.
- A slow broad step is not forced into the fast-transient class.
- A single fast pulse is reported as insufficient ensemble evidence rather than
  upgraded into a burst claim.
- SNR is absent by construction, not silently approximated.

## What remains unresolved

- Noise-aware feature SNR and uncertainty.
- Probe/fixture transfer-function compensation.
- Standards-grade uncertainty budgets.
- Real GDS-3504 exported waveform parsing.
- Segmented-memory acquisition import.
- Polarity-alternating and mixed-polarity burst validation.
- Composite EFT plus commutation-notch windows.
- Bench testing with a known generator and controlled DUT.
- Calibration of categorical evidence into honest probabilities.
- Cross-channel response latency and propagation analysis.

## Next gate

The next mathematically defensible addition is feature-specific SNR:

1. robust pre-event noise model,
2. pulse-amplitude SNR,
3. derivative SNR,
4. tail/ring-band SNR,
5. feature uncertainty,
6. calibration against held-out bench captures.

SNR should modify feature confidence, not erase a physically observed event.
