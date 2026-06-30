# high_speed_input_bounce

## Seed purpose

High-speed input bounce is a discrete-input seed for a fast input-related event that creates a repeatable middle-node response capable of corrupting downstream interpretation.

## What this folder should contain

- Chunk-level synthetic generator or capture set
- Repeated CH1 digital input captures
- Repeated CH2 middle-node candidate captures
- Expected classifier summary and confidence output

## Diagnostic markers

- Repeated CH1 input event exists
- CH2 response survives ensemble recovery after CH1-based alignment
- Recovered CH2 response is localized and relevant to downstream interpretation
- Can produce false edge, multi-crossing, stretched active time, or invalid count behavior

## Best Gamma/ElectroStat modules

- WC2-style alignment/reference recovery
- source-victim comparison
- threshold/consequence model
- coherence or cross-correlation as evidence support

## Confidence rule

High confidence requires input-caused repeatable CH2 behavior plus downstream interpretation risk. Low confidence if there is only chatter, only coherence, only a waveform shape match, or no consequence model.

## Not equivalent to

- missed_short_pulse
- sensor_threshold_chatter
- nanosecond offset measurement
- single-waveform shape matching
