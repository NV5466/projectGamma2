# Signal Diagnostic Report: rail_event_mixed_noise_scope

## Capture
- Source file: `C:\Users\dmaca\Documents\JTAStuff\projectGamma\FakeScopeData\rail_event_mixed_noise_scope.csv`
- Instrument: synthetic
- System: rail_control_test_fixture
- Event: switch_move_command
- Time column: `time_s`
- Channels analyzed: 5
- Estimated sample rate: 100000 Hz
- Estimated sample interval: 1e-05 s
- Time-step jitter ratio: 0.000%

## Limitations and Warnings
- No major automatic warnings were generated.

## Channel Role Table
| Channel | Line Identity | Role | Signal Type | Voltage Class | Measurement Reference | Problem Observed |
|---|---|---|---|---|---|---|
| CH1_command_5V | command signal | command_or_trigger | digital_like_voltage | 5V_logic | signal_to_common | unknown |
| CH2_motor_current_A_scaled | motor current clamp | suspected_source | analog_current | not_applicable | current_clamp | noise |
| CH3_common_to_chassis_V | local common to chassis | reference_or_common | analog_voltage | low_voltage_dc | common_to_chassis | noise |
| CH4_sensor_feedback_24V | TB3-14 sensor feedback | victim_signal | digital_like_voltage | 24VDC | signal_to_common | dropout |
| CH5_fault_output_5V | fault output | output_or_consequence | digital_like_voltage | 5V_logic | signal_to_common | unknown |

## Event Timeline
- 0.1 s: command_or_trigger CH1_command_5V rose - command active began
- 0.1 s: reference_or_common CH3_common_to_chassis_V disturbance began - reference/common movement threshold crossed
- 0.10002 s: suspected_source CH2_motor_current_A_scaled activity began - source activity threshold crossed
- 0.14556 s: victim_signal CH4_sensor_feedback_24V transitioned/chattered - unstable until 0.15778 s
- 0.245 s: victim_signal CH4_sensor_feedback_24V dropout detected - low until 0.251 s
- 0.265 s: output_or_consequence CH5_fault_output_5V asserted - output/fault state changed high
- 0.38 s: command_or_trigger CH1_command_5V fell - command active ended

## Role-Aware Interpretation
### CH1_command_5V: command signal
- Route: command_or_trigger / digital_like_voltage
- Routed analyses: threshold_edges, command_active_window, pulse_duration
- Command threshold set at 2.5 from channel percentiles.
- Detected 2 threshold edges: rising at 0.1 s, falling at 0.38 s.
- First high/active interval: 0.1 s to 0.38 s (280 ms).
- Command active window detected from 0.1 s to 0.38 s (280 ms).
- PSD on digital-like state lines is secondary; edge timing and state duration are primary evidence.

### CH2_motor_current_A_scaled: motor current clamp
- Route: suspected_source / analog_current
- Routed analyses: activity_onset, event_window_RMS, event_window_PSD, transient_energy
- Suspected source activity began around 0.10002 s.
- During CH1_command_5V active window, strongest PSD peaks are near 48.8281 Hz, 195.312 Hz, 18017.6 Hz.

### CH3_common_to_chassis_V: local common to chassis
- Route: reference_or_common / analog_voltage
- Routed analyses: reference_movement, RMS_noise, event_window_PSD, overlap_check
- Reference/common movement began around 0.1 s.
- During CH1_command_5V active window, strongest PSD peaks are near 18017.6 Hz, 48.8281 Hz, 41650.4 Hz.
- Reference/common movement overlaps the command window and victim disturbance; common-mode or shared-reference disturbance remains possible.

### CH4_sensor_feedback_24V: TB3-14 sensor feedback
- Route: victim_signal / digital_like_voltage
- Routed analyses: threshold_edges, chatter_detection, dropout_detection, state_stability
- Victim threshold set at 12.09 from channel percentiles.
- Detected 25 threshold edges: rising at 0.14556 s, falling at 0.14612 s, rising at 0.14667 s, falling at 0.14723 s, rising at 0.14778 s, falling at 0.14834 s.
- First high/active interval: 0.14556 s to 0.14612 s (0.56 ms).
- Victim chatter/instability detected from 0.14556 s to 0.15778 s (23 edges).
- Victim dropout/low-state interval detected from 0.245 s to 0.251 s.
- PSD on digital-like state lines is secondary; edge timing and state duration are primary evidence.

### CH5_fault_output_5V: fault output
- Route: output_or_consequence / digital_like_voltage
- Routed analyses: threshold_edges, state_change_timing, fault_assertion_time
- Output/Consequence threshold set at 2.49941 from channel percentiles.
- Detected 1 threshold edges: rising at 0.265 s.
- First high/active interval: 0.265 s to 0.49999 s (235 ms).
- Output/consequence asserted at 0.265 s.
- Output/consequence event occurred 20 ms after first relevant victim event.
- PSD on digital-like state lines is secondary; edge timing and state duration are primary evidence.

## Channel Results
### CH1_command_5V: command signal
- Role: command_or_trigger
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

### CH2_motor_current_A_scaled: motor current clamp
- Role: suspected_source

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

### CH3_common_to_chassis_V: local common to chassis
- Role: reference_or_common

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

### CH4_sensor_feedback_24V: TB3-14 sensor feedback
- Role: victim_signal

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

### CH5_fault_output_5V: fault output
- Role: output_or_consequence

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
The user-supplied metadata defines line identity and role. Waveform shape may support behavior observations, but ElectroStat does not infer physical line identity from shape alone.
