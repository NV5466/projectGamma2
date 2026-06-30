# Sorted Main Notes

Branch: `sort/codex-seed-library-layout`

This branch intentionally does not rename the project to DIH. Gamma remains the project name; ElectroStat remains the evidence engine; WC2 remains the waveform reference/residual layer.

## Sorting Rule

Files were moved only when there was clear evidence from filename, README context, imports, outputs, and bundle naming. Unclear files were preserved under `_unsorted_review/`.

## Major Moves

- `Gamma_ElectroStat_Sag_Seed_v01/` -> `pq_voltage_sag/`
- `Gamma_ElectroStat_Swell_Seed_v013/` -> `pq_voltage_swell/`
- `Gamma_ElectroStat_Short_Interruption_Seed_v011/` -> `pq_short_interruption/`
- `Gamma_ElectroStat_Harmonic_Distortion_Seed_v010/` -> `pq_harmonic_distortion/`
- `ElectroStat_sharp_event_bundle(1)/` -> `pq_commutation_notch/`
- `ElectroStat_ensemble_hankel_bundle(2)/` -> `pq_oscillatory_transient/`
- `Gamma_ElectroStat_EMI_EFT_Burst_Seed_v010/.../` -> `emi_eft_burst/`
- `Gamma_ElectroStat_Current_Inrush_Seed_v010/` -> `current_inrush/`
- `Gamma_ElectroStat_Relay_Contact_Bounce_Seed_v010(1)/.../` -> `switch_relay_contact_bounce/`
- `CommonMode_multispectral_test_bundle/` -> `common_mode_noise/`
- `PWM_VFD_final_damping_head_bundle/` -> `pwm_vfd_edge_coupled_noise/`
- `Missed_Short_Pulse_Seed_1000_Case_Bundle/` -> `missed_short_pulse/`
- `experiments/hsib_chunk_recovery/` -> `high_speed_input_bounce/`

Each seed now uses `src/`, `tests/`, `fixtures/`, `expected_outputs/`, `plots/`, and `notes/` where applicable.
