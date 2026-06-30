# HSIB classification notes

This expanded trial has two regions.

## HSIB region

Chunks 1-100 are all HSIB.

The hidden CH1-to-CH2 nuisance delay increases linearly:

```text
chunk 1   -> 1 ns
chunk 2   -> 2 ns
chunk 3   -> 3 ns
...
chunk 100 -> 100 ns
```

The classifier must not classify by measuring that delay. The delay is only a stress condition.

## Non-HSIB control region

Chunks 101-131 are actual negative controls. They are genuine output waveforms, not quick HSIB transients.

The hidden nuisance delay also increases linearly inside the control region:

```text
chunk 101 -> 1 ns
chunk 102 -> 2 ns
chunk 103 -> 3 ns
...
chunk 131 -> 31 ns
```

The controls cycle through these sustained/correct waveform families:

```text
square wave with noise
sinusoid with noise
triangle wave with noise
sustained correct response with noise
PWM-like correct output with noise
```

These controls may cross voltage thresholds, but they are rejected because they are sustained or correct-like waveforms rather than localized transients tied to the input event.

## HSIB recovery rule

HSIB is recovered from the chunk-level ensemble relationship:

```text
CH1 repeated digital event
  -> CH2 repeatable localized middle-node transient
  -> downstream interpretation risk
```

Therefore HSIB is not equivalent to chatter, dropout, coherence alone, source-victim comparison alone, missed short pulse, nanosecond offset measurement, or single-waveform shape matching.
