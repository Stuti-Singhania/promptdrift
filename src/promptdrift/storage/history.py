"""Bounded, project-local monitoring history. Never stores provider payloads."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from promptdrift.errors import PromptDriftError
from promptdrift.models.monitor import MonitorReport


def history_path(config_path: Path) -> Path:
    return config_path.parent / ".promptdrift" / "history.sqlite3"


def save_monitor_report(report: MonitorReport, path: Path, *, retention: int = 1000) -> None:
    if retention < 1:
        raise ValueError("retention must be positive")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=5)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS monitor_runs (run_id TEXT PRIMARY KEY, report_json TEXT NOT NULL)"
            )
            db.execute(
                "INSERT INTO monitor_runs VALUES (?, ?)", (report.run_id, report.model_dump_json())
            )
            db.execute(
                "DELETE FROM monitor_runs WHERE rowid NOT IN (SELECT rowid FROM monitor_runs ORDER BY rowid DESC LIMIT ?)",
                (retention,),
            )
    except (OSError, sqlite3.Error) as exc:
        raise PromptDriftError(
            "Monitoring completed but local history could not be saved."
        ) from exc


def load_monitor_history(path: Path, *, limit: int = 20) -> list[dict]:
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    if not path.exists():
        return []
    try:
        with closing(
            sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
        ) as db:
            rows = db.execute(
                "SELECT report_json FROM monitor_runs ORDER BY rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise PromptDriftError(
            "Monitoring history is unreadable; back up or remove the local history database."
        ) from exc
