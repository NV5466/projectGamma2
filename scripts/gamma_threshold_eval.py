from __future__ import annotations

from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gamma_core.thresholds import default_thresholds, write_threshold_outputs


def _parse_thresholds(value: str | None) -> list[float]:
    if not value:
        return default_thresholds()
    thresholds = [float(item.strip()) for item in value.split(",") if item.strip()]
    if not thresholds:
        raise argparse.ArgumentTypeError("at least one threshold is required")
    for threshold in thresholds:
        if not 0.0 <= threshold <= 1.0:
            raise argparse.ArgumentTypeError(f"threshold out of [0, 1]: {threshold}")
    return thresholds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Gamma campaign confidence thresholds.")
    parser.add_argument("--campaign-dir", required=True, help="Campaign output directory containing cached Gamma CSV/JSON outputs.")
    parser.add_argument("--min-required-tpr", type=float, default=0.90)
    parser.add_argument("--max-allowed-fpr", type=float, default=0.05)
    parser.add_argument("--thresholds", help="Comma-separated thresholds. Default: 0.05,0.10,...,0.95.")
    parser.add_argument("--out", help="Output threshold_evaluation.csv path. Defaults inside --campaign-dir.")
    parser.add_argument("--deployable-out", help="Output deployable_thresholds.csv path. Defaults next to --out.")
    args = parser.parse_args(argv)

    thresholds = _parse_thresholds(args.thresholds)
    threshold_results, deployable = write_threshold_outputs(
        args.campaign_dir,
        thresholds=thresholds,
        min_required_tpr=args.min_required_tpr,
        max_allowed_fpr=args.max_allowed_fpr,
        out=args.out,
        deployable_out=args.deployable_out,
    )
    print(f"wrote {len(threshold_results)} threshold rows")
    print(f"selected {len(deployable)} deployable thresholds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
