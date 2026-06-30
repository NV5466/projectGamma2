# HSIB Chunk Recovery Synthetic Trial

This experiment adds a blind synthetic stress test for the `high_speed_input_bounce` seed/class.

## Definition

`high_speed_input_bounce` is classified only when a repeated digital input event produces a repeated middle-node response that creates downstream interpretation risk.

It is **not** equivalent to these nearby Gamma concepts:

| Nearby concept | Why HSIB is different |
|---|---|
| Chatter | Chatter is an output symptom. HSIB requires an input-caused middle-node response. |
| Dropout | Dropout is signal loss. HSIB is dangerous fast-event pass-through or reshaping. |
| Coherence/CSD | Coherence/CSD is evidence machinery, not the fault class. |
| Source-victim comparison | Source-victim comparison is the measurement frame. HSIB adds downstream interpretation risk. |
| Missed short pulse | Missed short pulse is under-response or safe rejection. HSIB requires recovered downstream danger. |

## Chunk model

A chunk is one repeated experiment condition:

```text
131 chunks total
100 waveform pairs per chunk
13,100 waveform pairs total

waveform pair:
  CH1 = one digital input line
  CH2 = one HSIB/middle-node candidate line or control output line
```

Inside one chunk, the hidden clean input-response behavior is fixed. Only noise, baseline junk, small amplitude variation, and measurement noise vary per waveform.

Between chunks, the hidden clean response changes, noise changes with chunk index, and the hidden CH1-to-CH2 nuisance delay changes linearly.

## Case layout

Chunks 1-100 are HSIB cases. All one hundred should classify as `HSIB`.

- Chunk 1 has 1 ns hidden CH1-to-CH2 nuisance delay.
- Chunk 2 has 2 ns hidden CH1-to-CH2 nuisance delay.
- This continues linearly through chunk 100, which has 100 ns hidden nuisance delay.

Chunks 101-131 are non-HSIB controls. These are genuine output waveforms, not quick HSIB transients.

- Chunk 101 has 1 ns hidden nuisance delay.
- Chunk 102 has 2 ns hidden nuisance delay.
- This continues linearly through chunk 131, which has 31 ns hidden nuisance delay.

The control families cycle through:

```text
noisy square-wave output
noisy sinusoidal output
noisy triangle-wave output
sustained correct-response output
PWM-like correct output
```

## Classification gates

A chunk is classified as HSIB only if all gates pass:

1. Repeated CH1 input event is recovered.
2. CH2 response is repeatable after CH1-based alignment.
3. Recovered CH2 response is localized to the input event.
4. Recovered CH2 response threatens downstream interpretation through threshold crossing, active dwell, ringing, or multi-crossing behavior.
5. Sustained/correct waveforms are rejected even if they cross voltage thresholds.

The detector does **not** measure the nanosecond delay. Delay is a hidden stress condition, not the classification target.

## Run

```bash
python experiments/hsib_chunk_recovery/hsib_chunk_recovery_test.py
```

Optional JSON output:

```bash
python experiments/hsib_chunk_recovery/hsib_chunk_recovery_test.py --json
```

The script exits non-zero if the expected synthetic trial fails unless `--no-assert` is supplied.

## Expected result

The default seed should recover all one hundred HSIB chunks and reject all thirty-one genuine-waveform controls:

```text
hsib_recovered=100/100
controls_rejected=31/31
false_pos=0
false_neg=0
accuracy=1.000
```
