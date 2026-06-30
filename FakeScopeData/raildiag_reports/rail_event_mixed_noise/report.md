# Signal Diagnostic Report: rail_event_mixed_noise_scope

## Capture
- Source file: `C:\Users\dmaca\Documents\JTAStuff\projectGamma\FakeScopeData\rail_event_mixed_noise_scope.csv`
- Instrument: unknown
- System: unknown
- Event: unknown
- Time column: `time_s`
- Channels analyzed: 5
- Estimated sample rate: 100000 Hz
- Estimated sample interval: 1e-05 s
- Time-step jitter ratio: 0.000%

## Limitations and Warnings
- Instrument is unknown.
- System under test is unknown.
- Captured event is unknown.

## Channel Results
### CH1_command_5V: CH1_command_5V
- Role: unknown
- Warning: Many samples sit exactly at the channel min/max; check for clipping or quantization.

| Metric | Value |
|---|---:|
| count | 50000 |
| mean | 2.8 |
| min | 0 |
| max | 5 |
| std | 2.48193 |
| rms | 3.74166 |
| rms_ac | 2.48193 |
| peak_to_peak | 5 |

- Dominant PSD peaks: 48.8281 Hz
- Waveform plot: [plots\CH1_command_5V_waveform.png](plots/CH1_command_5V_waveform.png)
- Psd plot: [plots\CH1_command_5V_psd.png](plots/CH1_command_5V_psd.png)

### CH2_motor_current_A_scaled: CH2_motor_current_A_scaled
- Role: unknown

| Metric | Value |
|---|---:|
| count | 50000 |
| mean | 0.0250063 |
| min | -3.96469 |
| max | 4.7418 |
| std | 0.998124 |
| rms | 0.998437 |
| rms_ac | 0.998124 |
| peak_to_peak | 8.70649 |

- Dominant PSD peaks: 48.8281 Hz, 195.312 Hz, 18017.6 Hz, 830.078 Hz, 18359.4 Hz
- Waveform plot: [plots\CH2_motor_current_A_scaled_waveform.png](plots/CH2_motor_current_A_scaled_waveform.png)
- Psd plot: [plots\CH2_motor_current_A_scaled_psd.png](plots/CH2_motor_current_A_scaled_psd.png)

### CH3_common_to_chassis_V: CH3_common_to_chassis_V
- Role: unknown

| Metric | Value |
|---|---:|
| count | 50000 |
| mean | 2.63055e-05 |
| min | -0.378933 |
| max | 0.405911 |
| std | 0.106932 |
| rms | 0.106932 |
| rms_ac | 0.106932 |
| peak_to_peak | 0.784844 |

- Dominant PSD peaks: 18017.6 Hz, 48.8281 Hz, 16992.2 Hz, 16699.2 Hz, 19335.9 Hz
- Waveform plot: [plots\CH3_common_to_chassis_V_waveform.png](plots/CH3_common_to_chassis_V_waveform.png)
- Psd plot: [plots\CH3_common_to_chassis_V_psd.png](plots/CH3_common_to_chassis_V_psd.png)

### CH4_sensor_feedback_24V: CH4_sensor_feedback_24V
- Role: unknown

| Metric | Value |
|---|---:|
| count | 50000 |
| mean | 16.505 |
| min | -0.890988 |
| max | 25.0201 |
| std | 11.0655 |
| rms | 19.8711 |
| rms_ac | 11.0655 |
| peak_to_peak | 25.9111 |

- Dominant PSD peaks: 48.8281 Hz, 878.906 Hz, 2685.55 Hz, 244.141 Hz, 4492.19 Hz
- Waveform plot: [plots\CH4_sensor_feedback_24V_waveform.png](plots/CH4_sensor_feedback_24V_waveform.png)
- Psd plot: [plots\CH4_sensor_feedback_24V_psd.png](plots/CH4_sensor_feedback_24V_psd.png)

### CH5_fault_output_5V: CH5_fault_output_5V
- Role: unknown

| Metric | Value |
|---|---:|
| count | 50000 |
| mean | 2.35003 |
| min | -0.0820594 |
| max | 5.08436 |
| std | 2.49551 |
| rms | 3.42786 |
| rms_ac | 2.49551 |
| peak_to_peak | 5.16642 |

- Dominant PSD peaks: 48.8281 Hz, 2441.41 Hz, 2636.72 Hz, 2978.52 Hz, 3222.66 Hz
- Waveform plot: [plots\CH5_fault_output_5V_waveform.png](plots/CH5_fault_output_5V_waveform.png)
- Psd plot: [plots\CH5_fault_output_5V_psd.png](plots/CH5_fault_output_5V_psd.png)

## Interpretation Boundary
This report is deterministic first-pass analysis. It can identify observed signal behavior, data-quality limits, and timing/spectral clues, but it does not claim root cause.
