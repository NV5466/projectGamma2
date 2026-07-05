from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import re
import shutil
import time

from .io import SUPPORTED_CAPTURE_SUFFIXES, discover_capture_files


DEFAULT_WAVEFORM_LIBRARY = Path("waveform_sets")


@dataclass
class WaveformSet:
    set_id: str
    root: Path
    captures_dir: Path
    manifest_path: Path
    notes_path: Path


def create_waveform_set(
    set_id: str,
    *,
    library_root: str | Path = DEFAULT_WAVEFORM_LIBRARY,
    notes: str = "",
) -> WaveformSet:
    clean_id = sanitize_set_id(set_id)
    if not clean_id:
        raise ValueError("waveform set name must contain at least one letter or number")
    root = Path(library_root) / clean_id
    captures_dir = root / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    notes_path = root / "notes.md"
    manifest_path = root / "manifest.json"
    if not notes_path.exists():
        notes_path.write_text((notes or f"# {clean_id}\n").rstrip() + "\n", encoding="utf-8")
    if not manifest_path.exists():
        write_manifest(
            manifest_path,
            {
                "schema": "gamma.waveform_set.v1",
                "set_id": clean_id,
                "created_at_unix": time.time(),
                "captures_dir": "captures",
                "supported_formats": sorted(SUPPORTED_CAPTURE_SUFFIXES),
                "captures": [],
                "notes": notes,
            },
        )
    return WaveformSet(clean_id, root, captures_dir, manifest_path, notes_path)


def import_waveforms(
    sources: list[str | Path],
    set_id: str,
    *,
    library_root: str | Path = DEFAULT_WAVEFORM_LIBRARY,
    copy_files: bool = True,
    notes: str = "",
) -> tuple[WaveformSet, list[dict[str, Any]], list[str]]:
    waveform_set = create_waveform_set(set_id, library_root=library_root, notes=notes)
    manifest = read_manifest(waveform_set.manifest_path)
    existing = {capture["stored_path"] for capture in manifest.get("captures", [])}
    imported: list[dict[str, Any]] = []
    warnings: list[str] = []
    for source in sources:
        files, source_warnings = discover_capture_files(source)
        warnings.extend(source_warnings)
        for file_path in files:
            destination = waveform_set.captures_dir / unique_capture_name(file_path, waveform_set.captures_dir)
            relative_destination = destination.relative_to(waveform_set.root).as_posix()
            if relative_destination in existing:
                warnings.append(f"already imported: {file_path}")
                continue
            if copy_files:
                shutil.copy2(file_path, destination)
            else:
                destination = file_path
                relative_destination = str(file_path)
            record = {
                "capture_id": destination.stem,
                "original_path": str(file_path),
                "stored_path": relative_destination,
                "suffix": file_path.suffix.lower(),
                "bytes": file_path.stat().st_size,
                "imported_at_unix": time.time(),
            }
            manifest.setdefault("captures", []).append(record)
            imported.append(record)
            existing.add(relative_destination)
    manifest["updated_at_unix"] = time.time()
    manifest["capture_count"] = len(manifest.get("captures", []))
    write_manifest(waveform_set.manifest_path, manifest)
    return waveform_set, imported, warnings


def list_waveform_sets(library_root: str | Path = DEFAULT_WAVEFORM_LIBRARY) -> list[WaveformSet]:
    root = Path(library_root)
    if not root.exists():
        return []
    sets: list[WaveformSet] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "manifest.json").exists():
            sets.append(
                WaveformSet(
                    set_id=child.name,
                    root=child,
                    captures_dir=child / "captures",
                    manifest_path=child / "manifest.json",
                    notes_path=child / "notes.md",
                )
            )
    return sets


def sanitize_set_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._-")


def unique_capture_name(source: Path, captures_dir: Path) -> str:
    stem = sanitize_set_id(source.stem) or "capture"
    suffix = source.suffix.lower()
    candidate = f"{stem}{suffix}"
    index = 2
    while (captures_dir / candidate).exists():
        candidate = f"{stem}_{index}{suffix}"
        index += 1
    return candidate


def read_manifest(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(path: str | Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
