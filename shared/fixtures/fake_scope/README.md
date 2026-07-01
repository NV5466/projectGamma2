# Fake Oscilloscope CSV Training Data

These files are synthetic test captures for developing an in-house signal/noise analysis tool.

## Files

1. `basic_fft_sanity_scope.csv`
   - Sample rate: 50 kSa/s
   - Duration: 0.20 s
   - Known spectral peaks:
     - CH1: 1 kHz
     - CH2: 60 Hz, 1 kHz, 3 kHz
     - CH3: 500 Hz square wave with odd harmonics
     - CH4: event ringing near 4.2 kHz after 0.080 s

2. `rail_event_mixed_noise_scope.csv`
   - Sample rate: 100 kSa/s
   - Duration: 0.50 s
   - Simulates:
     - command signal
     - motor current/source line
     - common/reference movement
     - 24 V sensor victim line
     - fault/output consequence
   - Useful for:
     - event windows
     - PSD
     - coherence/CSD prototypes
     - thresholding
     - chatter/dropout detection
     - timeline reports

3. `power_quality_scope.csv`
   - Sample rate: 20 kSa/s
   - Duration: 0.50 s
   - Simulates:
     - clean 60 Hz 120 VAC waveform
     - harmonic distortion
     - voltage sag
     - switching transient

## CSV shape

All CSVs use:

```csv
time_s,CH1...,CH2...
0.000000,...
```

The first column is always `time_s`. All other columns are numeric channels.

## Warning

These are fake development files. They are not real oscilloscope data and should not be used as safety references.
