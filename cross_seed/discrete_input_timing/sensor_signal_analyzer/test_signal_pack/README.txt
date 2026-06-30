Sensor Signal Analyzer Test-Signal Pack
========================================

All files use a 50 kHz sample rate.

Mode 1 files
------------
Required columns:
  time_s
  sensor_output_v

Mode 2 files
------------
Required columns:
  time_s
  sensor_output_v
  command_v

Mode 3 files
------------
Required columns:
  time_s
  sensor_output_v
  position

Mode 4 files
------------
Required columns:
  time_s
  sensor_output_v
  command_v
  actuator_current_a
  position
  analog_sensor_v

Included fault cases
--------------------
Mode 1:
  healthy, slow edge, chatter, incomplete high rail

Mode 2:
  healthy, late chain, slow output, late and slow

Mode 3:
  healthy, threshold drift, wide hysteresis

Mode 4:
  healthy, actuation delay, mechanical travel delay, sensor decision delay

The file analyzer_results.csv contains the measured outputs produced by the
current sensor_signal_analyzer.py implementation.

These are synthetic engineering test signals. They are intended for algorithm
verification, UI testing, and regression testing. They are not substitutes for
real sensor captures.
