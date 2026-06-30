# Signal Diagnostic Report: basic_fft_sanity_scope

## Capture
- Source file: `C:\Users\dmaca\Documents\JTAStuff\projectGamma\FakeScopeData\basic_fft_sanity_scope.csv`
- Instrument: unknown
- System: unknown
- Event: unknown
- Time column: `time_s`
- Channels analyzed: 4
- Estimated sample rate: 50000 Hz
- Estimated sample interval: 2e-05 s
- Time-step jitter ratio: 0.000%

## Limitations and Warnings
- Instrument is unknown.
- System under test is unknown.
- Captured event is unknown.

## Channel Results
### CH1_clean_1kHz_V: CH1_clean_1kHz_V
- Role: unknown
- Warning: Many samples sit exactly at the channel min/max; check for clipping or quantization.

| Metric | Value |
|---|---:|
| count | 10000 |
| mean | -7.67386e-17 |
| min | -1.99605 |
| max | 1.99605 |
| std | 1.41421 |
| rms | 1.41421 |
| rms_ac | 1.41421 |
| peak_to_peak | 3.99211 |

- Dominant PSD peaks: 1000.98 Hz, 24.4141 Hz
- Waveform plot: [plots\CH1_clean_1kHz_V_waveform.png](plots/CH1_clean_1kHz_V_waveform.png)
- Psd plot: [plots\CH1_clean_1kHz_V_psd.png](plots/CH1_clean_1kHz_V_psd.png)

### CH2_1kHz_3kHz_60Hz_noise_V: CH2_1kHz_3kHz_60Hz_noise_V
- Role: unknown

| Metric | Value |
|---|---:|
| count | 10000 |
| mean | -0.00102499 |
| min | -2.06158 |
| max | 2.0966 |
| std | 1.18828 |
| rms | 1.18828 |
| rms_ac | 1.18828 |
| peak_to_peak | 4.15818 |

- Dominant PSD peaks: 1000.98 Hz, 3002.93 Hz, 48.8281 Hz, 12426.8 Hz, 4809.57 Hz
- Waveform plot: [plots\CH2_1kHz_3kHz_60Hz_noise_V_waveform.png](plots/CH2_1kHz_3kHz_60Hz_noise_V_waveform.png)
- Psd plot: [plots\CH2_1kHz_3kHz_60Hz_noise_V_psd.png](plots/CH2_1kHz_3kHz_60Hz_noise_V_psd.png)

### CH3_square_500Hz_V: CH3_square_500Hz_V
- Role: unknown
- Warning: Many samples sit exactly at the channel min/max; check for clipping or quantization.

| Metric | Value |
|---|---:|
| count | 10000 |
| mean | 0.00125 |
| min | -2.5 |
| max | 2.5 |
| std | 2.49987 |
| rms | 2.49987 |
| rms_ac | 2.49987 |
| peak_to_peak | 5 |

- Dominant PSD peaks: 488.281 Hz, 1489.26 Hz, 2490.23 Hz, 3491.21 Hz, 4492.19 Hz
- Waveform plot: [plots\CH3_square_500Hz_V_waveform.png](plots/CH3_square_500Hz_V_waveform.png)
- Psd plot: [plots\CH3_square_500Hz_V_psd.png](plots/CH3_square_500Hz_V_psd.png)

### CH4_ringing_event_4p2kHz_V: CH4_ringing_event_4p2kHz_V
- Role: unknown

| Metric | Value |
|---|---:|
| count | 10000 |
| mean | 0.00175754 |
| min | -3.9705 |
| max | 3.9927 |
| std | 0.5509 |
| rms | 0.550903 |
| rms_ac | 0.5509 |
| peak_to_peak | 7.9632 |

- Dominant PSD peaks: 4199.22 Hz, 3442.38 Hz, 3369.14 Hz, 4931.64 Hz, 3222.66 Hz
- Waveform plot: [plots\CH4_ringing_event_4p2kHz_V_waveform.png](plots/CH4_ringing_event_4p2kHz_V_waveform.png)
- Psd plot: [plots\CH4_ringing_event_4p2kHz_V_psd.png](plots/CH4_ringing_event_4p2kHz_V_psd.png)

## Interpretation Boundary
This report is deterministic first-pass analysis. It can identify observed signal behavior, data-quality limits, and timing/spectral clues, but it does not claim root cause.
