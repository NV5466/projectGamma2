from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gamma_core.cli import run_from_args


if __name__ == "__main__":
    raise SystemExit(run_from_args())
