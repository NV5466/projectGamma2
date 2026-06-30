# PWM/VFD Damping Head

## Architecture

The frozen PWM/VFD edge-coupled ringing classifier is unchanged.

Classification and parameter estimation are separate:

1. The classifier determines whether the waveform is PWM/VFD edge-coupled ringing.
2. The damping head estimates a physical pole only after classification.
3. A damping value is accepted only when the response behaves as one stationary damped mode.

## Damping pipeline

1. Regularize detected switching edges onto their periodic timing grid.
2. Estimate the edge-to-victim impulse response by regularized convolutional deconvolution.
3. Fit the dominant damped mode by nonlinear variable projection.
4. Independently estimate decay by logarithmic decrement.
5. Independently estimate poles with Cadzow-denoised ESPRIT.
6. Form a weighted-median decay estimate.
7. Audit event-to-event pole stationarity.
8. Publish the damping value only when the acceptance gate passes.

## Acceptance gate

- Three physical estimators must participate.
- Event-frequency MAD / median must be <= 1%.
- Event timing-shift MAD must be <= 0.5 sample.
- Secondary spectral mode must be <= 10% of the dominant mode.
- The deconvolved impulse-response fit and reconstruction must pass their frozen quality gates.

## Returned quantities

For decay envelope

    exp(-alpha t)

the head returns:

- decay rate alpha in s^-1
- damped ringing frequency f_d in Hz
- damping ratio zeta

    zeta = alpha / sqrt(alpha^2 + (2 pi f_d)^2)

- quality factor Q

    Q = sqrt(alpha^2 + (2 pi f_d)^2) / (2 alpha)

## Final untouched confirmation battery

- Positive scenarios: 200
- Accepted damping values: 39
- Acceptance rate: 19.5%
- Median accepted decay-rate error: 6.16%
- 90th-percentile accepted error: 21.03%
- 95th-percentile accepted error: 30.33%
- Accepted values within 10%: 66.7%
- Accepted values within 20%: 87.2%
- Accepted values within 30%: 94.9%
- Conservative +/-50% interval coverage: 100.0%
- Median ringing-frequency error: 0.50%

## Interpretation

A rejected damping value does not reverse the classification. It means the measured response does not support one defensible scalar damping constant. The likely causes are:

- event-to-event frequency variation
- delay variation
- multiple resonant modes
- inadequate transient signal-to-noise ratio

In those cases Gamma should retain the PWM/VFD edge-coupled ringing classification and report a pole distribution or multiple modes rather than inventing one damping number.

## Limitation

This is synthetic validation. Real VFD, cable, motor, grounding, probe, and operating-state measurements remain necessary.
