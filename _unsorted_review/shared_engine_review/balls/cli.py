from __future__ import annotations

import argparse
from pathlib import Path

from .analysis import analyze_capture
from .io import read_analog_csv
from .plots import write_plots
from .report import write_report


def main() -> int:
    parser = argparse.ArgumentParser(description="ElectroStat v0.02 role-aware oscilloscope CSV diagnostic report")
    parser.add_argument("csv_path", type=Path, help="Oscilloscope CSV export")
    parser.add_argument("--metadata", type=Path, help="Optional YAML metadata file")
    parser.add_argument("--output", type=Path, help="Output directory for report and plots")
    parser.add_argument("--window", nargs=2, type=float, metavar=("START_S", "END_S"), help="Optional event window in seconds")
    args = parser.parse_args()

    csv_path = args.csv_path.resolve()
    output_dir = args.output.resolve() if args.output else csv_path.with_suffix("").parent / f"{csv_path.stem}_report"
    event_window = tuple(args.window) if args.window else None

    capture = read_analog_csv(csv_path, args.metadata.resolve() if args.metadata else None)
    results, warnings = analyze_capture(capture, event_window=event_window)
    write_plots(capture, results, output_dir)
    report = write_report(capture, results, warnings, output_dir)

    print(f"Wrote report: {report.text_path}")
    print(f"Wrote structured report: {report.json_path}")
    if report.markdown_path:
        print(f"Wrote legacy markdown: {report.markdown_path}")
    print(f"Wrote plots: {report.output_dir / 'plots'}")
    if report.warnings:
        print(f"Warnings: {len(report.warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
