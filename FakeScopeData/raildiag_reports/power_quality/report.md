# Signal Diagnostic Report: power_quality_scope

## Capture
- Source file: `C:\Users\dmaca\Documents\JTAStuff\projectGamma\FakeScopeData\power_quality_scope.csv`
- Instrument: unknown
- System: unknown
- Event: unknown
- Time column: `time_s`
- Channels analyzed: 4
- Estimated sample rate: 20000 Hz
- Estimated sample interval: 5e-05 s
- Time-step jitter ratio: 0.000%

## Limitations and Warnings
- Instrument is unknown.
- System under test is unknown.
- Captured event is unknown.

## Channel Results
### CH1_clean_120VAC_peak_V: CH1_clean_120VAC_peak_V
- Role: unknown

| Metric | Value |
|---|---:|
| count | 10000 |
| mean | 1.09139e-15 |
| min | -170 |
| max | 170 |
| std | 120.208 |
| rms | 120.208 |
| rms_ac | 120.208 |
| peak_to_peak | 340 |

- Dominant PSD peaks: 58.5938 Hz, 9.76563 Hz
- Waveform plot: [plots\CH1_clean_120VAC_peak_V_waveform.png](plots/CH1_clean_120VAC_peak_V_waveform.png)
- Psd plot: [plots\CH1_clean_120VAC_peak_V_psd.png](plots/CH1_clean_120VAC_peak_V_psd.png)

### CH2_harmonic_distortion_V: CH2_harmonic_distortion_V
- Role: unknown

| Metric | Value |
|---|---:|
| count | 10000 |
| mean | 0.028658 |
| min | -166.153 |
| max | 166.613 |
| std | 121.063 |
| rms | 121.063 |
| rms_ac | 121.063 |
| peak_to_peak | 332.766 |

- Dominant PSD peaks: 58.5938 Hz, 175.781 Hz, 302.734 Hz, 9.76563 Hz, 986.328 Hz
- Waveform plot: [plots\CH2_harmonic_distortion_V_waveform.png](plots/CH2_harmonic_distortion_V_waveform.png)
- Psd plot: [plots\CH2_harmonic_distortion_V_psd.png](plots/CH2_harmonic_distortion_V_psd.png)

### CH3_voltage_sag_event_V: CH3_voltage_sag_event_V
- Role: unknown

| Metric | Value |
|---|---:|
| count | 10000 |
| mean | 0.284062 |
| min | -170 |
| max | 170 |
| std | 109.753 |
| rms | 109.754 |
| rms_ac | 109.753 |
| peak_to_peak | 340 |

- Dominant PSD peaks: 58.5938 Hz
- Waveform plot: [plots\CH3_voltage_sag_event_V_waveform.png](plots/CH3_voltage_sag_event_V_waveform.png)
- Psd plot: [plots\CH3_voltage_sag_event_V_psd.png](plots/CH3_voltage_sag_event_V_psd.png)

### CH4_switching_transient_V: CH4_switching_transient_V
- Role: unknown

| Metric | Value |
|---|---:|
| count | 10000 |
| mean | 0.0193046 |
| min | -190.944 |
| max | 240.922 |
| std | 120.301 |
| rms | 120.301 |
| rms_ac | 120.301 |
| peak_to_peak | 431.866 |

- Dominant PSD peaks: 58.5938 Hz, 9.76563 Hz, 2500 Hz, 136.719 Hz, 166.016 Hz
- Waveform plot: [plots\CH4_switching_transient_V_waveform.png](plots/CH4_switching_transient_V_waveform.png)
- Psd plot: [plots\CH4_switching_transient_V_psd.png](plots/CH4_switching_transient_V_psd.png)

## Interpretation Boundary
This report is deterministic first-pass analysis. It can identify observed signal behavior, data-quality limits, and timing/spectral clues, but it does not claim root cause.
