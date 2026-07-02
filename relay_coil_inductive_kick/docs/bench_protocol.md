# Relay Coil Inductive Kickback Bench Protocol

## Goal

Classify `relay_coil_inductive_kick` using source-coupled physics, not generic ringing.

Primary model:

```math
v_{victim}(t) \approx k \frac{di_{coil}}{dt}
```

or, when using coil voltage as source channel:

```math
v_{victim}(t) \approx k v_{coil}(t)
```

The unknown constant \(k\) is fitted. It may represent inductance, mutual inductance, geometry, probe loading, wiring layout, or all of the above wearing one ugly coat.

## Hardware

Use low voltage only.

- 12 V or 24 V relay coil
- bench supply with current limit
- MOSFET or relay driver
- current shunt resistor, preferred
- optional flyback diode
- optional TVS clamp
- optional RC snubber
- oscilloscope, 2 channels minimum
- victim wire loop / nearby signal line

## Preferred scope setup

- CH1: current shunt voltage, converted to coil current
- CH2: victim line voltage

Alternate setup:

- CH1: coil node / MOSFET drain / coil voltage
- CH2: victim line voltage

## Test matrix

| Condition | Clamp | Victim geometry | Expected |
|---|---|---|---|
| A | flyback diode | near coil wire | slow current decay, lower victim transient |
| B | TVS clamp | near coil wire | faster collapse, stronger transient |
| C | RC snubber | near coil wire | reduced HF energy |
| D | TVS clamp | 1 cm / 5 cm / 10 cm | fitted k drops with distance |
| E | TVS clamp | twisted pair victim | fitted k and WC2 drop |
| F | no coil, bouncing contact only | same victim line | reject as not inductive kick |

## Capture settings

- sample rate: >= 100 kS/s, better >= 1 MS/s
- chunk length: 10 ms to 50 ms
- trigger: coil de-energization
- captures per condition: 20 minimum, 100 ideal
- save time, source, victim, condition metadata

## Pass conditions

For true inductive cases:

- one dominant source event
- source/victim lag inside configured window
- victim fits unknown-gain source derivative or source voltage
- WC2/correlation support passes threshold
- ringdown tail may support confidence, but cannot decide the class alone

For contact bounce negative:

- repeated edge cluster should reject
- ringing alone should not produce positive classification
