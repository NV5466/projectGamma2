from __future__ import annotations

from pathlib import Path

from gamma_core.io import load_capture_npz
from gamma_core.schema import CaptureRecord


SUPPORTED_CAPTURE_SUFFIXES = {".npz"}


def discover_capture_files(input_path: str | Path) -> tuple[list[Path], list[str]]:
    path = Path(input_path)
    warnings: list[str] = []
    if path.is_file():
        if path.suffix.lower() in SUPPORTED_CAPTURE_SUFFIXES:
            return [path], warnings
        return [], [f"unsupported capture file type: {path}"]
    if not path.exists():
        return [], [f"input path does not exist: {path}"]
    captures: list[Path] = []
    for child in sorted(path.rglob("*")):
        if not child.is_file():
            continue
        if child.suffix.lower() in SUPPORTED_CAPTURE_SUFFIXES:
            captures.append(child)
        else:
            warnings.append(f"skipped unsupported file: {child}")
    return captures, warnings


def load_captures(input_path: str | Path, *, max_cases: int | None = None) -> tuple[list[CaptureRecord], list[str]]:
    files, warnings = discover_capture_files(input_path)
    captures: list[CaptureRecord] = []
    for file_path in files[:max_cases]:
        try:
            capture = load_capture_npz(file_path)
            capture.metadata.setdefault("source_file", str(file_path))
            captures.append(capture)
        except Exception as exc:
            warnings.append(f"failed to load {file_path}: {exc!r}")
    return captures, warnings
