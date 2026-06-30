Missed Short Pulse Seed
=======================

Core classification order
-------------------------
1. Measurement confidence
2. Observed pulse morphology
3. Candidate mechanism compatibility
4. System consequence

Observed classes
----------------
- valid pulse propagation
- complete pulse non-propagation
- subthreshold pulse suppression
- pulse-width collapse
- late pulse propagation
- pulse merging
- pulse splitting
- pulse stretching
- possible acquisition miss
- unresolved pulse miss

Mechanism handling
------------------
The analyzer does not force a root cause.

- RC time constant and cutoff are estimated only when a subthreshold analog
  response is compatible with first-order attenuation.
- Q is considered only when a decaying oscillatory response is actually found.
- Acquisition-limited pulses are not blamed on the hardware.

Validation
----------
The included validation used 1,000 randomized synthetic trials:
100 trials for each of 10 classes.

Result for seed 6262026:
1000 / 1000 passed.

This proves regression behavior across the included synthetic parameter ranges.
It does not prove field accuracy on unknown hardware. Real captures are still
required to calibrate thresholds, latency windows, sampling requirements, and
mechanism confidence.
