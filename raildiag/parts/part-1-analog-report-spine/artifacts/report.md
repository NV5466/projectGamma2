# Signal Diagnostic Report: switch_sensor_noise_test_001

## Capture
- Source file: `C:\Users\dmaca\Documents\JTAStuff\raildiag\examples\synthetic_scope.csv`
- Instrument: GDS-3504
- System: switch_machine
- Event: switch_move_command
- Time column: `Time`
- Channels analyzed: 2
- Estimated sample rate: 1000 Hz
- Estimated sample interval: 0.001 s
- Time-step jitter ratio: 0.000%

## Limitations and Warnings
- No major automatic warnings were generated.

## Channel Results
### CH1: sensor_feedback
- Role: victim_signal
- Warning: Many samples sit exactly at the channel min/max; check for clipping or quantization.
- Warning: Frequency resolution is coarse (~50.00 Hz bins).

| Metric | Value |
|---|---:|
| count | 21 |
| mean | -3.17207e-17 |
| min | -0.951 |
| max | 0.951 |
| std | 0.690106 |
| rms | 0.690106 |
| rms_ac | 0.690106 |
| peak_to_peak | 1.902 |

- Dominant PSD peaks: 95.2381 Hz
- Waveform plot: [plots\CH1_waveform.png](plots/CH1_waveform.png)
- Psd plot: [plots\CH1_psd.png](plots/CH1_psd.png)

### CH2: local_common_to_chassis
- Role: reference_or_common
- Warning: Many samples sit exactly at the channel min/max; check for clipping or quantization.
- Warning: Frequency resolution is coarse (~50.00 Hz bins).

| Metric | Value |
|---|---:|
| count | 21 |
| mean | 0.0328571 |
| min | -0.05 |
| max | 0.1 |
| std | 0.0500612 |
| rms | 0.0598808 |
| rms_ac | 0.0500612 |
| peak_to_peak | 0.15 |

- Dominant PSD peaks: 47.619 Hz, 285.714 Hz
- Waveform plot: [plots\CH2_waveform.png](plots/CH2_waveform.png)
- Psd plot: [plots\CH2_psd.png](plots/CH2_psd.png)

## Interpretation Boundary
This report is deterministic first-pass analysis. It can identify observed signal behavior, data-quality limits, and timing/spectral clues, but it does not claim root cause.
