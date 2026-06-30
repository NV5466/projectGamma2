# ElectroStat v0.02

Small first-pass rail/electrical signal diagnostic tool.

This version imports one CSV capture, estimates sample rate, computes basic channel statistics, writes waveform and PSD plots, and generates a fixed-width text report with conservative warnings. It also writes a structured `report.estat.json` export that can be fed into a custom display program.

## Run

```powershell
cd C:\Users\dmaca\Documents\JTAStuff\raildiag
python -m raildiag.cli path\to\scope_capture.csv --metadata examples\metadata_example.yaml
```

Primary outputs:

- `report.txt`: fixed-width human-readable report
- `report.estat.json`: structured report export for display/import tools, including first-class analysis windows
- `report.md`: legacy Markdown export
- `plots\`: waveform and PSD images

Display an existing structured report:

```powershell
python -m raildiag.display path\to\report.estat.json
```

Optional event-window analysis:

```powershell
python -m raildiag.cli path\to\scope_capture.csv --window 0.1 0.25
```

## Expected CSV Shape

The first version expects a header row containing a time-like column and one or more numeric analog channel columns.

Example:

```csv
Time,CH1,CH2
0.000000,24.1,0.02
0.000001,24.0,0.01
```

Real oscilloscope exports often include preamble rows. The importer skips rows before a header that looks like time/channel labels.

## Metadata Rule

The user defines what the line is. ElectroStat defines what the signal did.

ElectroStat does not infer physical line identity from waveform shape. Role-aware analysis requires metadata such as channel role, signal type, voltage class, measurement reference, problem observed, and event context.

## Boundary

This tool does not diagnose root cause. It reports observed signal behavior, data-quality warnings, and basic timing/spectral evidence.
