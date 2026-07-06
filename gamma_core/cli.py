from __future__ import annotations

from pathlib import Path
import argparse
import logging

from .evidence import write_evidence_outputs
from .io import load_capture_dir, load_capture_npz
from .registry import load_registry
from .runner import run_campaign

LOG = logging.getLogger("gamma")


def _parse_statuses(value: str | None) -> set[str]:
    if not value:
        return {
            "implemented",
            "implemented_synthetic",
            "validated",
            "synthetic_research_prototype",
            "concept_validated_elsewhere",
            "needs_review",
            "scaffolded",
        }
    return {item.strip() for item in value.split(",") if item.strip()}


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Gamma Core v0.1 signature campaign.")
    parser.add_argument("--capture-dir")
    parser.add_argument("--capture")
    parser.add_argument("--registry-root", default=".")
    parser.add_argument("--out", required=True)
    parser.add_argument("--include-status")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--max-cases", type=int)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="[gamma] %(message)s")
    include_status = _parse_statuses(args.include_status)
    signatures, failures = load_registry(args.registry_root, include_status=include_status)
    LOG.info("loaded %d signatures", len(signatures))
    if failures:
        LOG.info("failed to load %d manifests", len(failures))
    if not signatures:
        raise SystemExit("no signatures loaded")

    if args.capture:
        captures = [load_capture_npz(args.capture)]
    elif args.capture_dir:
        captures = load_capture_dir(args.capture_dir)
    else:
        raise SystemExit("--capture or --capture-dir is required")
    if args.max_cases is not None:
        captures = captures[: args.max_cases]
    LOG.info("loaded %d captures", len(captures))
    if not captures:
        raise SystemExit("no captures loaded")

    case_results = run_campaign(captures, signatures)
    output_files = write_evidence_outputs(
        case_results,
        Path(args.out),
        run_config={
            "capture": args.capture,
            "capture_dir": args.capture_dir,
            "registry_root": args.registry_root,
            "include_status": sorted(include_status),
            "max_cases": args.max_cases,
        },
        signatures_failed_to_load=failures,
    )
    for name in output_files:
        LOG.info("wrote %s", name)
    return 0
