# Seed Implementation Matrix

| seed_id | README | manifest | src | tests | fixtures | expected_outputs | plots | validation_status | notes |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| pq_voltage_sag | True | True | 2 | 1 | 1 | 4 | 5 | 900 synthetic validation runs reported in README | notes.md: True |
| pq_voltage_swell | True | True | 2 | 0 | 1 | 3 | 0 | 900 cases; sensitivity 0.996667; specificity 1.000000; precision 1.000000; balanced accuracy 0.998333; runtime 50.80 s; synthetic research prototype only | notes.md: True |
| pq_short_interruption | True | True | 2 | 0 | 1 | 4 | 1 | 330 synthetic cases; sensitivity/specificity/precision/balanced accuracy 1.000000 | notes.md: True |
| pq_harmonic_distortion | True | True | 2 | 0 | 4 | 3 | 2 | 270 synthetic cases; sensitivity/specificity/precision/balanced accuracy 1.000000 | notes.md: True |
| pq_flicker_am_mod | True | True | 0 | 0 | 0 | 0 | 0 | none | notes.md: True |
| pq_commutation_notch | True | True | 1 | 0 | 1 | 5 | 2 | needs_review; sharp-event bundle assigned by commutation notch evidence | notes.md: True |
| pq_impulsive_transient | True | True | 0 | 0 | 0 | 0 | 0 | none | notes.md: True |
| pq_oscillatory_transient | True | True | 1 | 0 | 1 | 7 | 2 | needs_review; ensemble hankel bundle assigned by oscillatory/pole evidence | notes.md: True |
| emi_eft_burst | True | True | 3 | 1 | 6 | 4 | 3 | 24/24 synthetic outcomes, 6/6 tests reported | notes.md: True |
| current_inrush | True | True | 2 | 1 | 4 | 4 | 1 | synthetic families reported; SNR deferred | notes.md: True |
| switch_relay_contact_bounce | True | True | 2 | 1 | 2 | 5 | 4 | 108/108 population captures and 114 pytest cases reported | notes.md: True |
| relay_coil_inductive_kick | True | True | 0 | 0 | 0 | 0 | 0 | none | notes.md: True |
| ground_loop_hum | True | True | 0 | 0 | 0 | 0 | 0 | none | notes.md: True |
| common_mode_noise | True | True | 0 | 1 | 1 | 3 | 5 | controlled synthetic multi-spectral validation documented | notes.md: True |
| pwm_vfd_edge_coupled_noise | True | True | 1 | 0 | 1 | 4 | 3 | needs_review; PWM/VFD damping bundle assigned by filename and README | notes.md: True |
| sensor_threshold_chatter | True | True | 0 | 0 | 0 | 0 | 0 | sensor analyzer material kept in cross_seed/discrete_input_timing because it spans multiple sensor seeds | notes.md: True |
| slow_edge_late_transition | True | True | 0 | 0 | 0 | 0 | 0 | sensor analyzer material kept in cross_seed/discrete_input_timing because it spans multiple sensor seeds | notes.md: True |
| missed_short_pulse | True | True | 2 | 0 | 14 | 5 | 11 | 1000/1000 randomized synthetic trials reported | notes.md: True |
| high_speed_input_bounce | True | True | 0 | 1 | 0 | 0 | 0 | HSIB chunk recovery experiment reports 100/100 recovered and 31/31 controls rejected | notes.md: True |
| bearing_fault_vibration_envelope | True | True | 0 | 0 | 0 | 0 | 0 | none | notes.md: True |
| bearing_fault_current_signature | True | True | 0 | 0 | 0 | 0 | 0 | none | notes.md: True |
| broken_rotor_bar_sidebands | True | True | 0 | 0 | 0 | 0 | 0 | none | notes.md: True |
