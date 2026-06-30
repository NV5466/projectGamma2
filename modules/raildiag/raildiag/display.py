from __future__ import annotations

import argparse
import json
from pathlib import Path

from .report import render_text_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Display an ElectroStat structured report")
    parser.add_argument("report_json", type=Path, help="Path to report.estat.json")
    parser.add_argument("--width", type=int, default=100, help="Text display width")
    args = parser.parse_args()

    document = json.loads(args.report_json.read_text(encoding="utf-8"))
    print(render_text_report(document, width=args.width), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
