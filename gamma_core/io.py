from __future__ import annotations

from pathlib import Path
import json

import numpy as np

from .schema import CaptureRecord


def _opt_str(data: np.lib.npyio.NpzFile, key: str) -> str | None:
    if key not in data:
        return None
    val = data[key]
    try:
        return str(val.item())
    except Exception:
        return str(val)


def load_capture_npz(path: str | Path) -> CaptureRecord:
    path = Path(path)
    data = np.load(path, allow_pickle=True)
    metadata = {}
    if "metadata_json" in data:
        metadata = json.loads(str(data["metadata_json"].item()))

    references: dict[str, np.ndarray] = {}
    if "references_json" in data:
        mapping = json.loads(str(data["references_json"].item()))
        for label, arr_key in mapping.items():
            references[str(label)] = np.asarray(data[str(arr_key)], dtype=float)
    else:
        for key in data.files:
            if key.startswith("reference_"):
                references[key.removeprefix("reference_")] = np.asarray(data[key], dtype=float)

    secondary = np.asarray(data["secondary"], dtype=float) if "secondary" in data else None
    capture = CaptureRecord(
        sample_rate_hz=float(data["sample_rate_hz"]),
        primary=np.asarray(data["primary"], dtype=float),
        secondary=secondary,
        references=references,
        time_s=np.asarray(data["time_s"], dtype=float) if "time_s" in data else None,
        capture_id=_opt_str(data, "capture_id") or path.stem,
        truth_label=_opt_str(data, "truth_label"),
        primary_label=_opt_str(data, "primary_label"),
        metadata=metadata,
    )
    capture.validate()
    return capture


def load_capture_dir(path: str | Path) -> list[CaptureRecord]:
    path = Path(path)
    return [load_capture_npz(p) for p in sorted(path.glob("*.npz"))]
