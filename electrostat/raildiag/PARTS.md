# ElectroStat Work Parts

This file groups the project by milestone so the work can be found by part number instead of by date.

Folder index:

- `parts/part-1-analog-report-spine`
- `parts/part-2-role-aware-routing`
- `parts/part-3-structured-display-reports`
- `parts/part-4-first-class-analysis-windows`

Each part folder includes local `artifacts/` with representative reports and plots for that milestone.

## Part 1 - Analog Report Spine

Commit: `ed748f3 Initial ElectroStat analog report tool`

Added the first runnable ElectroStat workflow:

- Oscilloscope-style CSV import
- Time column detection
- Sample-rate and time-step jitter estimation
- Per-channel statistics
- Waveform plots
- PSD plots
- Markdown report generation
- Basic metadata YAML support
- Conservative interpretation boundary

## Part 2 - Role-Aware Routing

Commit: `b8c4f40 Add role-aware analysis routing`

Moved the tool from generic channel analysis toward role-aware diagnostic behavior:

- Extended channel metadata fields
- Added channel role table
- Added command/source/reference/victim/output routing
- Added edge timing, chatter, dropout, source activity, reference movement, and output assertion detection
- Added role-aware interpretation
- Added event timeline
- Added rail-event metadata example

## Part 3 - Structured Display Reports

Commit: `349a7d2 Add structured text report display`

Replaced Markdown as the primary display surface:

- Added `report.txt` fixed-width report
- Added `report.estat.json` structured report export
- Kept `report.md` as legacy output
- Added `python -m raildiag.display` for rendering structured reports
- Reduced fragile Markdown table formatting

## Part 4 - First-Class Analysis Windows

Commit: `f11048b Add first-class analysis windows`

Made event windows durable report objects instead of prose-only references:

- Added schema `electrostat.report.v2`
- Added `windows` section to JSON reports
- Added baseline, command-active, source, reference, victim chatter, victim dropout, and post-event windows
- Added baseline-vs-event PSD summaries
- Added spectral window-bank checks
- Improved digital-like rail/state warnings
- Corrected dropout-to-fault timing language
- Added conservative cross-channel relationship statements

## Current Verification Target

Role-aware rail-event verification output:

```text
C:\Users\dmaca\Documents\JTAStuff\projectGamma\FakeScopeData\raildiag_reports\rail_event_windows_verify
```

Primary files:

- `report.txt`
- `report.estat.json`
- `display_render.txt`
