ElectroStat Shared Sharp-Event Detector

Architecture
------------
One detector first segments physical sharp-event windows. It does not count each
derivative crossing as a separate event.

Each event is then labeled:
    commutation_notch
        Short, inward-toward-zero event aligned to a repeating 60-degree grid.

    singular_event
        A real sharp event that is not phase-locked as a commutation notch.
        The next development step will fit transient poles and divide these into:
            impulsive_transient
            oscillatory_transient
            unknown_sharp_event

Pipeline
--------
1. FFT estimates the line fundamental.
2. Harmonic regression builds an expected baseline.
3. Residual and residual derivative find sharp activity.
4. Nearby crossings are merged into one physical event window.
5. Every event receives time, phase, width, peak, area, polarity,
   inward fraction, derivative severity, and residual sign-change metrics.
6. A 60-degree phase-grid classifier identifies commutation notches.
7. Everything else is retained as a singular event candidate.

Expected real CSV columns
-------------------------
time_s
voltage_v

Synthetic validation
--------------------
The bundled validation waveform contains six-pulse notches, persistent 3rd/5th/7th
harmonics, measurement noise, and three irregular double-exponential impulses.

The full impulse pole fitter is intentionally not included yet. This bundle creates
the common segmentation and counting layer that the pole classifier will consume.


Validation note
---------------
One synthetic impulse was intentionally placed nearly on top of a commutation
notch. The shared segmentation layer merges those overlapping signatures into
one physical event window instead of double-counting derivative crossings.
The later pole/decomposition stage can decide whether a composite event contains
both an impulse and a notch.
