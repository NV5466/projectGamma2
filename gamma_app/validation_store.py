from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import csv
import json
import sqlite3
import time
import uuid


@dataclass
class ValidationCase:
    capture_id: str
    source_file_path: str
    seed_label: str | None = None
    no_fault_control: bool = False
    channel_labels: str | None = None
    sample_rate_hz: float | None = None
    capture_duration_s: float | None = None
    notes: str | None = None
    operator_tags: str | None = None
    environment_notes: str | None = None


class ValidationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            create table if not exists captures (
              capture_id text primary key,
              source_file_path text not null,
              seed_label text,
              no_fault_control integer not null default 0,
              channel_labels text,
              sample_rate_hz real,
              capture_duration_s real,
              notes text,
              operator_tags text,
              environment_notes text,
              created_at real not null
            );
            create table if not exists analyzer_runs (
              id integer primary key autoincrement,
              session_id text not null,
              capture_id text not null,
              signature_id text not null,
              family text,
              confidence real not null,
              threshold real not null,
              raw_matched integer not null,
              threshold_pass integer not null,
              pass_fail text,
              fp_fn_marking text,
              analyzer_outputs_json text,
              threshold_profile text,
              created_at real not null,
              foreign key(capture_id) references captures(capture_id)
            );
            """
        )
        self.conn.commit()

    def add_capture(self, case: ValidationCase) -> None:
        self.conn.execute(
            """
            insert or replace into captures (
              capture_id, source_file_path, seed_label, no_fault_control, channel_labels,
              sample_rate_hz, capture_duration_s, notes, operator_tags, environment_notes, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case.capture_id,
                case.source_file_path,
                case.seed_label,
                int(case.no_fault_control),
                case.channel_labels,
                case.sample_rate_hz,
                case.capture_duration_s,
                case.notes,
                case.operator_tags,
                case.environment_notes,
                time.time(),
            ),
        )
        self.conn.commit()

    def list_captures(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("select * from captures order by capture_id"))

    def record_result_rows(self, rows: list[dict[str, Any]], *, session_id: str | None = None) -> str:
        session_id = session_id or str(uuid.uuid4())
        now = time.time()
        for row in rows:
            truth = row.get("truth_label")
            prediction_positive = bool(row.get("threshold_pass"))
            is_truth = truth == row.get("signature_id")
            fp_fn = ""
            if prediction_positive and is_truth:
                fp_fn = "TP"
            elif prediction_positive and not is_truth:
                fp_fn = "FP"
            elif (not prediction_positive) and is_truth:
                fp_fn = "FN"
            else:
                fp_fn = "TN"
            self.conn.execute(
                """
                insert into analyzer_runs (
                  session_id, capture_id, signature_id, family, confidence, threshold,
                  raw_matched, threshold_pass, pass_fail, fp_fn_marking, analyzer_outputs_json,
                  threshold_profile, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    row.get("capture_id"),
                    row.get("signature_id"),
                    row.get("family"),
                    float(row.get("confidence", 0.0)),
                    float(row.get("threshold", 0.0)),
                    int(bool(row.get("raw_matched"))),
                    int(prediction_positive),
                    "pass" if fp_fn in {"TP", "TN"} else "fail",
                    fp_fn,
                    json.dumps(row, sort_keys=True),
                    row.get("threshold_profile"),
                    now,
                ),
            )
        self.conn.commit()
        return session_id

    def summarize_latest(self) -> list[dict[str, Any]]:
        session_row = self.conn.execute("select session_id from analyzer_runs order by created_at desc limit 1").fetchone()
        if not session_row:
            return []
        return self.summarize_session(str(session_row["session_id"]))

    def summarize_session(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "select signature_id, family, fp_fn_marking from analyzer_runs where session_id = ?",
            (session_id,),
        ).fetchall()
        buckets: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            key = (str(row["signature_id"]), str(row["family"] or "unknown"))
            bucket = buckets.setdefault(
                key,
                {"signature_id": key[0], "family": key[1], "TP": 0, "FP": 0, "TN": 0, "FN": 0},
            )
            mark = str(row["fp_fn_marking"])
            if mark in {"TP", "FP", "TN", "FN"}:
                bucket[mark] += 1
        return [self._metrics(bucket) for bucket in buckets.values()]

    def export_summary(self, out_prefix: str | Path, *, session_id: str | None = None) -> tuple[Path, Path]:
        rows = self.summarize_session(session_id) if session_id else self.summarize_latest()
        prefix = Path(out_prefix)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        csv_path = prefix.with_suffix(".csv")
        json_path = prefix.with_suffix(".json")
        fieldnames = sorted({key for row in rows for key in row.keys()}) or ["signature_id"]
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        json_path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
        return csv_path, json_path

    @staticmethod
    def _metrics(row: dict[str, Any]) -> dict[str, Any]:
        tp, fp, tn, fn = row["TP"], row["FP"], row["TN"], row["FN"]
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        specificity = _safe_div(tn, tn + fp)
        row.update(
            {
                "total_cases": tp + fp + tn + fn,
                "precision": precision,
                "recall": recall,
                "sensitivity": recall,
                "specificity": specificity,
                "balanced_accuracy": (recall + specificity) / 2.0,
            }
        )
        return row


def _safe_div(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0
