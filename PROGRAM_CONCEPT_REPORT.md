# Program Concept Report

Gamma is the overall diagnostic project. ElectroStat is the signal-processing and evidence engine. WC2 is the waveform reference, alignment, and residual layer.

The repository is being shaped into a seed library. A seed is a narrowly named diagnostic hypothesis with evidence rules, validation limits, and cautious reporting language.

## Methodology

```text
raw captures
  -> metadata / precheck
  -> WC2 alignment and reference recovery
  -> residual / feature extraction
  -> seed-specific evidence rules
  -> confidence scoring
  -> cautious report language
```

## Reporting Boundary

Synthetic validation supports implementation behavior under controlled examples. It does not establish field calibration, standards compliance, or final root-cause proof. Preferred report language is: evidence is consistent with a seed under supplied capture conditions.

## Distinctions Kept Explicit

- `missed_short_pulse`: pulse exists electrically but scan/filter/software path misses it.
- `high_speed_input_bounce`: repeated input event creates a repeatable middle-node response that can corrupt downstream interpretation.
- `sensor_threshold_chatter`: analog signal hovers near threshold and digital state toggles.
- `switch_relay_contact_bounce`: mechanical contact changes state several times before settling.
- `slow_edge_late_transition`: slow analog edge causes late or variable threshold crossing.
