# ElectroStat Report: rail_event_mixed_noise_scope

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

## Channel Roles
### CH1_command_5V
- Line identity: command signal
- Role: command_or_trigger
- Signal type: digital_like_voltage
- Voltage class: 5V_logic
- Measurement reference: signal_to_common
- Problem observed: unknown

### CH2_motor_current_A_scaled
- Line identity: motor current clamp
- Role: suspected_source
- Signal type: analog_current
- Voltage class: not_applicable
- Measurement reference: current_clamp
- Problem observed: noise

### CH3_common_to_chassis_V
- Line identity: local common to chassis
- Role: reference_or_common
- Signal type: analog_voltage
- Voltage class: low_voltage_dc
- Measurement reference: common_to_chassis
- Problem observed: noise

### CH4_sensor_feedback_24V
- Line identity: TB3-14 sensor feedback
- Role: victim_signal
- Signal type: digital_like_voltage
- Voltage class: 24VDC
- Measurement reference: signal_to_common
- Problem observed: dropout

### CH5_fault_output_5V
- Line identity: fault output
- Role: output_or_consequence
- Signal type: digital_like_voltage
- Voltage class: 5V_logic
- Measurement reference: signal_to_common
- Problem observed: unknown


## Event Timeline
- 0.1 s: command_or_trigger CH1_command_5V rose - command active began
- 0.1 s: reference_or_common CH3_common_to_chassis_V disturbance began - reference/common movement threshold crossed
- 0.10002 s: suspected_source CH2_motor_current_A_scaled activity began - source activity threshold crossed
- 0.14556 s: victim_signal CH4_sensor_feedback_24V transitioned/chattered - unstable until 0.15778 s
- 0.245 s: victim_signal CH4_sensor_feedback_24V dropout detected - low until 0.251 s
- 0.265 s: output_or_consequence CH5_fault_output_5V asserted - output/fault state changed high
- 0.38 s: command_or_trigger CH1_command_5V fell - command active ended

## Analysis Windows
### baseline_pre_command
- Start: 0 s
- End: 0.1 s
- Duration: 100 ms
- Anchor channel: CH1_command_5V
- Anchor event: before_command_rise
- Generated from: detected event
- Purpose: Idle noise floor and baseline spectral reference before the command event.
- Applicable channels: CH1_command_5V, CH2_motor_current_A_scaled, CH3_common_to_chassis_V, CH4_sensor_feedback_24V, CH5_fault_output_5V
- Recommended analyses: baseline_RMS, baseline_PSD, noise_floor

### command_active
- Start: 0.1 s
- End: 0.38 s
- Duration: 280 ms
- Anchor channel: CH1_command_5V
- Anchor event: command_rise_to_fall
- Generated from: detected event
- Purpose: Main event window anchored to command active state.
- Applicable channels: CH2_motor_current_A_scaled, CH3_common_to_chassis_V, CH4_sensor_feedback_24V
- Recommended analyses: event_RMS, event_PSD, baseline_vs_event_PSD, sequence_timing

### source_activity
- Start: 0.10002 s
- End: 0.38 s
- Duration: 279.98 ms
- Anchor channel: CH2_motor_current_A_scaled
- Anchor event: activity began
- Generated from: detected event
- Purpose: Suspected source activity interval for source RMS, PSD, and transient energy checks.
- Applicable channels: CH2_motor_current_A_scaled, CH3_common_to_chassis_V, CH4_sensor_feedback_24V
- Recommended analyses: source_RMS, source_PSD, transient_energy, baseline_vs_event_PSD

### reference_disturbance
- Start: 0.1 s
- End: 0.38 s
- Duration: 280 ms
- Anchor channel: CH3_common_to_chassis_V
- Anchor event: disturbance began
- Generated from: detected event
- Purpose: Reference/common movement interval for common/reference noise analysis.
- Applicable channels: CH2_motor_current_A_scaled, CH3_common_to_chassis_V, CH4_sensor_feedback_24V
- Recommended analyses: reference_RMS, reference_PSD, overlap_check, baseline_vs_event_PSD

### victim_chatter
- Start: 0.14556 s
- End: 0.15778 s
- Duration: 12.22 ms
- Anchor channel: CH4_sensor_feedback_24V
- Anchor event: transitioned/chattered
- Generated from: detected event
- Purpose: Victim instability/chatter interval for edge density and state stability checks.
- Applicable channels: CH2_motor_current_A_scaled, CH3_common_to_chassis_V, CH4_sensor_feedback_24V
- Recommended analyses: edge_density, chatter_detection, state_stability

### victim_dropout
- Start: 0.245 s
- End: 0.251 s
- Duration: 6 ms
- Anchor channel: CH4_sensor_feedback_24V
- Anchor event: dropout detected
- Generated from: detected event
- Purpose: Victim dropout interval for dropout and consequence timing checks.
- Applicable channels: CH4_sensor_feedback_24V, CH5_fault_output_5V
- Recommended analyses: dropout_detection, delay_to_output, state_stability

### post_event_recovery
- Start: 0.38 s
- End: 0.49999 s
- Duration: 119.99 ms
- Anchor channel: CH1_command_5V
- Anchor event: after_command_or_fault
- Generated from: detected event
- Purpose: Post-event recovery/stability interval after command fall or fault assertion.
- Applicable channels: CH1_command_5V, CH2_motor_current_A_scaled, CH3_common_to_chassis_V, CH4_sensor_feedback_24V, CH5_fault_output_5V
- Recommended analyses: recovery_stability, post_event_RMS, post_event_PSD


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
- CH2_motor_current_A_scaled source activity began 0.02 ms after CH1_command_5V command rose.
- Evidence supports an event-aligned relationship, but does not prove root cause.

### CH3_common_to_chassis_V: local common to chassis
- Route: reference_or_common / analog_voltage
- Routed analyses: reference_movement, RMS_noise, event_window_PSD, overlap_check
- Reference/common movement began around 0.1 s.
- During CH1_command_5V active window, strongest PSD peaks are near 18017.6 Hz, 48.8281 Hz, 41650.4 Hz.
- Reference/common disturbance began 0 ms after CH1_command_5V command rose.
- Reference/common movement overlaps the command window and victim disturbance; common-mode or shared-reference disturbance remains possible.
- Reference/common disturbance overlaps victim event 'transitioned/chattered' at 0.14556 s.
- Evidence supports an event-aligned relationship, but does not prove root cause.

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
- Fault output asserted 20 ms after victim dropout began.
- Evidence supports an event-aligned relationship, but does not prove root cause.
- PSD on digital-like state lines is secondary; edge timing and state duration are primary evidence.


## Channel Results
### CH1_command_5V: command signal
- Role: command_or_trigger
- Warning: Samples sit near stable rails/states; expected for digital-like state behavior.

- count: 50000
- mean: 2.8
- min: 0
- max: 5
- std: 2.48193
- rms: 3.74166
- rms_ac: 2.48193
- peak_to_peak: 5

- Global PSD overview peaks: 48.8281 Hz
- Waveform plot: [plots/CH1_command_5V_waveform.png](plots/CH1_command_5V_waveform.png)
- Psd plot: [plots/CH1_command_5V_psd.png](plots/CH1_command_5V_psd.png)

### CH2_motor_current_A_scaled: motor current clamp
- Role: suspected_source

- count: 50000
- mean: 0.0250063
- min: -3.96469
- max: 4.7418
- std: 0.998124
- rms: 0.998437
- rms_ac: 0.998124
- peak_to_peak: 8.70649

- Global PSD overview peaks: 48.8281 Hz, 195.312 Hz, 18017.6 Hz, 830.078 Hz, 18359.4 Hz
- Windowed spectral results:
  - command_active: Event-linked spectral component near 18017.6 Hz grows relative to baseline and appears in blackmanharris, flattop, hann, tukey. Frequency presence is stronger than amplitude precision.
    - Stable peaks: 48.8281 Hz, 18017.6 Hz
    - Event-linked peaks: 48.8281 Hz (+120 dB), 18017.6 Hz (+120 dB), 14697.3 Hz (+120 dB), 30908.2 Hz (+120 dB)
  - source_activity: Event-linked spectral component near 18017.6 Hz grows relative to baseline and appears in blackmanharris, flattop, hann, tukey. Frequency presence is stronger than amplitude precision.
    - Stable peaks: 48.8281 Hz, 18017.6 Hz
    - Event-linked peaks: 48.8281 Hz (+120 dB), 18017.6 Hz (+120 dB), 14697.3 Hz (+120 dB), 30908.2 Hz (+120 dB)
  - reference_disturbance: Event-linked spectral component near 18017.6 Hz grows relative to baseline and appears in blackmanharris, flattop, hann, tukey. Frequency presence is stronger than amplitude precision.
    - Stable peaks: 48.8281 Hz, 18017.6 Hz
    - Event-linked peaks: 48.8281 Hz (+120 dB), 18017.6 Hz (+120 dB), 14697.3 Hz (+120 dB), 30908.2 Hz (+120 dB)
  - post_event_recovery: Event-linked spectral component near 40625 Hz grows relative to baseline and appears in blackmanharris, flattop, hann, tukey. Frequency presence is stronger than amplitude precision.
    - Stable peaks: 40625 Hz, 28906.2 Hz, 46289.1 Hz
    - Event-linked peaks: 40625 Hz (+120 dB), 28906.2 Hz (+120 dB), 46289.1 Hz (+120 dB), 7934.57 Hz (+120 dB), 28466.8 Hz (+120 dB)
- Waveform plot: [plots/CH2_motor_current_A_scaled_waveform.png](plots/CH2_motor_current_A_scaled_waveform.png)
- Psd plot: [plots/CH2_motor_current_A_scaled_psd.png](plots/CH2_motor_current_A_scaled_psd.png)

### CH3_common_to_chassis_V: local common to chassis
- Role: reference_or_common

- count: 50000
- mean: 2.63055e-05
- min: -0.378933
- max: 0.405911
- std: 0.106932
- rms: 0.106932
- rms_ac: 0.106932
- peak_to_peak: 0.784844

- Global PSD overview peaks: 18017.6 Hz, 48.8281 Hz, 16992.2 Hz, 16699.2 Hz, 19335.9 Hz
- Windowed spectral results:
  - command_active: Event-linked spectral component near 18017.6 Hz grows relative to baseline and appears in blackmanharris, flattop, hann, tukey. Frequency presence is stronger than amplitude precision.
    - Stable peaks: 48.8281 Hz, 18017.6 Hz, 22851.6 Hz, 27197.3 Hz, 41650.4 Hz
    - Event-linked peaks: 18017.6 Hz (+120 dB), 22851.6 Hz (+120 dB), 27197.3 Hz (+120 dB), 41650.4 Hz (+120 dB)
  - source_activity: Event-linked spectral component near 18017.6 Hz grows relative to baseline and appears in blackmanharris, flattop, hann, tukey. Frequency presence is stronger than amplitude precision.
    - Stable peaks: 48.8281 Hz, 18017.6 Hz, 22851.6 Hz, 27197.3 Hz, 41650.4 Hz
    - Event-linked peaks: 18017.6 Hz (+120 dB), 22851.6 Hz (+120 dB), 27197.3 Hz (+120 dB), 41650.4 Hz (+120 dB)
  - reference_disturbance: Event-linked spectral component near 18017.6 Hz grows relative to baseline and appears in blackmanharris, flattop, hann, tukey. Frequency presence is stronger than amplitude precision.
    - Stable peaks: 48.8281 Hz, 18017.6 Hz, 22851.6 Hz, 27197.3 Hz, 41650.4 Hz
    - Event-linked peaks: 18017.6 Hz (+120 dB), 22851.6 Hz (+120 dB), 27197.3 Hz (+120 dB), 41650.4 Hz (+120 dB)
  - post_event_recovery: Event-linked spectral component near 22070.3 Hz grows relative to baseline and appears in blackmanharris, flattop, hann, tukey. Frequency presence is stronger than amplitude precision.
    - Stable peaks: 48.8281 Hz, 22070.3 Hz, 31347.7 Hz, 25732.4 Hz, 37548.8 Hz
    - Event-linked peaks: 22070.3 Hz (+120 dB), 31347.7 Hz (+120 dB), 25732.4 Hz (+120 dB), 37548.8 Hz (+120 dB), 30712.9 Hz (+120 dB)
- Waveform plot: [plots/CH3_common_to_chassis_V_waveform.png](plots/CH3_common_to_chassis_V_waveform.png)
- Psd plot: [plots/CH3_common_to_chassis_V_psd.png](plots/CH3_common_to_chassis_V_psd.png)

### CH4_sensor_feedback_24V: TB3-14 sensor feedback
- Role: victim_signal

- count: 50000
- mean: 16.505
- min: -0.890988
- max: 25.0201
- std: 11.0655
- rms: 19.8711
- rms_ac: 11.0655
- peak_to_peak: 25.9111

- Global PSD overview peaks: 48.8281 Hz, 878.906 Hz, 2685.55 Hz, 244.141 Hz, 4492.19 Hz
- Waveform plot: [plots/CH4_sensor_feedback_24V_waveform.png](plots/CH4_sensor_feedback_24V_waveform.png)
- Psd plot: [plots/CH4_sensor_feedback_24V_psd.png](plots/CH4_sensor_feedback_24V_psd.png)

### CH5_fault_output_5V: fault output
- Role: output_or_consequence

- count: 50000
- mean: 2.35003
- min: -0.0820594
- max: 5.08436
- std: 2.49551
- rms: 3.42786
- rms_ac: 2.49551
- peak_to_peak: 5.16642

- Global PSD overview peaks: 48.8281 Hz, 2441.41 Hz, 2636.72 Hz, 2978.52 Hz, 3222.66 Hz
- Waveform plot: [plots/CH5_fault_output_5V_waveform.png](plots/CH5_fault_output_5V_waveform.png)
- Psd plot: [plots/CH5_fault_output_5V_psd.png](plots/CH5_fault_output_5V_psd.png)

## Interpretation Boundary
- This report is deterministic first-pass analysis. It can identify observed signal behavior, data-quality limits, and timing/spectral clues, but it does not claim root cause.
- The user-supplied metadata defines line identity and role. Waveform shape may support behavior observations, but ElectroStat does not infer physical line identity from shape alone.
