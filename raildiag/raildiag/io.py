from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from .metadata import load_metadata
from .models import AnalogChannel, Capture


TIME_HINTS = ("time", "sec", "second", "s")


def read_analog_csv(path: Path, metadata_path: Path | None = None) -> Capture:
    header_line_index, header = _find_header(path)
    rows = _read_numeric_rows(path, header_line_index, header)

    if rows.size == 0:
        raise ValueError("No numeric rows were found in the CSV.")

    time_index = _detect_time_column(header, rows)
    time_values = rows[:, time_index].astype(float)
    channel_indices = [i for i in range(len(header)) if i != time_index and _is_useful_numeric(rows[:, i])]
    if not channel_indices:
        raise ValueError("No numeric analog channels were found after detecting the time column.")

    metadata = load_metadata(metadata_path, path.stem)
    sample_rate_hz, sample_interval_s, jitter_ratio = estimate_sample_rate(time_values)

    channels: list[AnalogChannel] = []
    for index in channel_indices:
        channel_id = header[index].strip() or f"CH{index + 1}"
        channels.append(
            AnalogChannel(
                channel_id=channel_id,
                time_s=time_values,
                values=rows[:, index].astype(float),
                metadata=metadata.channels.get(channel_id),
            )
        )

    return Capture(
        source_path=path,
        time_column=header[time_index],
        channels=channels,
        metadata=metadata,
        sample_rate_hz=sample_rate_hz,
        sample_interval_s=sample_interval_s,
        time_jitter_ratio=jitter_ratio,
    )


def estimate_sample_rate(time_s: np.ndarray) -> tuple[float | None, float | None, float | None]:
    if len(time_s) < 2:
        return None, None, None

    diffs = np.diff(time_s)
    diffs = diffs[np.isfinite(diffs)]
    diffs = diffs[diffs > 0]
    if len(diffs) == 0:
        return None, None, None

    dt = float(np.median(diffs))
    if dt <= 0:
        return None, None, None

    jitter = float(np.std(diffs) / dt)
    return 1.0 / dt, dt, jitter


def _find_header(path: Path) -> tuple[int, list[str]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        for line_index, row in enumerate(csv.reader(handle)):
            cleaned = [cell.strip() for cell in row]
            if len(cleaned) < 2:
                continue
            lower = [cell.lower() for cell in cleaned]
            has_time_hint = any(any(hint in cell for hint in TIME_HINTS) for cell in lower)
            has_channel_hint = any(cell.startswith(("ch", "channel")) for cell in lower)
            if has_time_hint or has_channel_hint:
                return line_index, cleaned

    raise ValueError("Could not find a CSV header row with time/channel columns.")


def _read_numeric_rows(path: Path, header_line_index: int, header: list[str]) -> np.ndarray:
    parsed: list[list[float]] = []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        for _ in range(header_line_index + 1):
            next(reader, None)
        for row in reader:
            if len(row) < len(header):
                continue
            values: list[float] = []
            ok = True
            for cell in row[: len(header)]:
                try:
                    values.append(float(cell.strip()))
                except ValueError:
                    ok = False
                    break
            if ok:
                parsed.append(values)

    return np.asarray(parsed, dtype=float)


def _detect_time_column(header: list[str], rows: np.ndarray) -> int:
    for index, name in enumerate(header):
        if "time" in name.lower():
            return index

    best_index = 0
    best_score = -1.0
    for index in range(rows.shape[1]):
        values = rows[:, index]
        diffs = np.diff(values)
        positive_ratio = float(np.mean(diffs > 0)) if len(diffs) else 0.0
        span = float(np.nanmax(values) - np.nanmin(values))
        score = positive_ratio + (0.25 if span > 0 else 0.0)
        if score > best_score:
            best_score = score
            best_index = index
    return best_index


def _is_useful_numeric(values: np.ndarray) -> bool:
    finite = values[np.isfinite(values)]
    if len(finite) < 2:
        return False
    return float(np.nanmax(finite) - np.nanmin(finite)) > 0.0
