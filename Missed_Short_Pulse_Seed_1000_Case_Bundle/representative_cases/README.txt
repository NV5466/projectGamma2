Missed Short Pulse Seed Bundle
==============================

Files
-----
- One CSV and plot for each synthetic validation case
- event_results.csv
- validation_summary.csv
- diagnostics.json
- IMPLEMENTATION_NOTES.txt
- missed_short_pulse_analyzer.py

Test cases
----------
healthy
complete_absence
subthreshold_rc
width_collapse
late
merge
split
stretched
extra_spurious
acquisition_limited

CSV columns
-----------
time_s
source_v
output_v

Default test configuration
--------------------------
Source threshold: 12 V
Output threshold: 12 V
Expected latency window: 0.2 ms to 3 ms
Minimum valid output width: 150 us, except acquisition-limited case
