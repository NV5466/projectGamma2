
# RandomExtract prototype

This prototype takes already-aligned repeated captures from WaveCompare 2, removes the WaveCompare 2 collective waveform, then analyzes the residuals without throwing them away.

## Core model

For aligned capture \(x_k[n]\) and WaveCompare 2 waveform \(m[n]\):

\[
r_k[n] = x_k[n] - m[n]
\]

The piecewise-linear residual vectors are:

\[
\Delta r_k[n] = r_k[n+1] - r_k[n]
\]

The residual complex FFT is:

\[
R_k[f] = \operatorname{FFT}\{r_k[n]\}
\]

## What it produces

- Residual waveform matrix
- Piecewise-linear sample-to-sample vector matrix
- Pointwise residual median and MAD
- Pointwise vector median and MAD
- Complex FFT for every residual capture
- Capture-frequency magnitude matrix
- Peak observations for each capture
- Frequency tracks across capture index
- Occupancy, frequency jitter, phase coherence, amplitude trend, and classification
- Per-capture RMS, vector roughness, spectral flatness, crest factor, and peak count

## Why both views matter

The vector geometry detects local waveform movement, intermittent jumps, and roughness.

The FFT tracking detects frequency-organized content even when its phase changes between captures and therefore cancels out of WaveCompare 2.

## Quick test

```bash
python random_extract_prototype.py --demo --output-dir demo_output
```

## CSV input format

The first column is time in seconds. Every later column is one aligned capture.

```text
time_s,capture_0,capture_1,capture_2,...
0.000000,...
0.000244,...
...
```

Run:

```bash
python random_extract_prototype.py \
  --input-csv aligned_captures.csv \
  --output-dir random_extract_output
```

To use the exact WaveCompare 2 waveform instead of the prototype median fallback:

```bash
python random_extract_prototype.py \
  --input-csv aligned_captures.csv \
  --baseline-csv wavecompare2_collective.csv \
  --output-dir random_extract_output
```

## Main output files

- `frequency_tracks.csv`
- `peak_observations.csv`
- `capture_metrics.csv`
- `pointwise_residual_geometry.csv`
- `pointwise_vector_geometry.csv`
- `random_extract_arrays.npz`
- `summary.json`
- `capture_frequency_matrix.png`
- `residual_overlay.png`
- `pointwise_geometry.png`

## Important limits

This prototype assumes WaveCompare 2 has already aligned all captures.

The labels describe residual morphology, not physical root cause. A persistent 60 Hz residual can be line-frequency interference, but it should not be called a ground loop without ground-reference or return-current evidence.

The peak tracker is intentionally simple and transparent. It is suitable for testing the idea before replacing it with a more elaborate assignment or Bayesian tracker.


## Synthetic validation included

The packaged demo contains:

- asynchronous 60 Hz interference with random phase between captures
- a 310 Hz component whose signed complex FFT coefficient grows across capture index
- broadband white noise
- intermittent impulse contamination

The expected top classifications are:

- 60 Hz: persistent asynchronous narrowband
- 310 Hz: persistent phase-axis narrowband with growth

The phase-axis test matters because subtracting the WC2 collective waveform can make a growing, fixed-phase component cross zero. Its ordinary FFT phase then flips by \(\pi\), so plain phase coherence alone would falsely call it asynchronous. RandomExtract therefore also tests axial phase coherence and the geometry of the complex FFT coefficient trajectory.
