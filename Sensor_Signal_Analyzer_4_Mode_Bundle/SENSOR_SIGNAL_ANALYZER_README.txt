Sensor Signal Analyzer, Four Modes
==================================

Mode 1: Sensor output only
Measures edge time, slew, overshoot, settling, chatter, and output rails.
It can call an edge slow or unstable. It cannot call it late.

Mode 2: Command + sensor output
Measures command-to-output latency and edge quality separately.
Latency is whole-chain delay, not proof of a bad sensor.

Mode 3: Position/distance + sensor output
Measures ON position, OFF position, repeatability, and physical hysteresis.
This is the strongest mode for switching-distance drift and mounting changes.

Mode 4: Command + actuator current + position + analog sensor + digital output
Separates:
  command -> current
  current -> motion
  motion -> threshold crossing
  threshold crossing -> digital output
and reports total chain latency.

Validation uses synthetic healthy and faulted captures. Real hardware testing is
still required to calibrate thresholds, smoothing windows, and severity limits.
