# Gamma / ElectroStat Swell Seed v0.1.3

This is the fully integrated end-to-end swell worker.

Changes from v0.1.2:
- residual energy classifies clean versus distorted behavior;
- residual energy does not erase supported swell evidence;
- a candidate must have an equivalent rectangular excess duration of
  at least 2.0 selected
  analysis windows.

That last rule prevents moving-window smearing from promoting a short
spike or one offset-edge artifact into a sustained swell.

Validation cases: 900
Sensitivity: 0.996667
Specificity: 1.000000
Precision: 1.000000
Balanced accuracy: 0.998333
Runtime: 50.80 s

Synthetic research prototype only; no field calibration claim.
