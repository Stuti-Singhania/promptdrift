"""Local SQLite storage for runs, captures, and scenarios."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from promptdrift.models import RegressionReport
from promptdrift.models.capture import Interaction


def _get_db(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or (Path.home() / ".promptdrift" / "promptdrift.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    _migrate_db(conn)
    return conn


def _migrate_db(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            created_at TEXT,
            provider TEXT,
            model TEXT,
            report_json TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            provider TEXT,
            model TEXT,
            prompt TEXT,
            system_prompt TEXT,
            input TEXT,
            variables_json TEXT,
            output TEXT,
            latency_ms REAL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            estimated_cost_usd REAL,
            tags_json TEXT,
            source TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS scenarios (
            id TEXT PRIMARY KEY,
            prompt TEXT,
            input TEXT,
            variables_json TEXT,
            category TEXT,
            tags_json TEXT,
            source TEXT,
            status TEXT,
            assertions_json TEXT,
            thresholds_json TEXT,
            created_at TEXT
        )
    """)
    db.commit()


def record_report(
    report: RegressionReport,
    path: Path | None = None,
    *,
    store_raw_output: bool = False,
) -> None:
    """Persist local history without raw prompts/outputs unless explicitly requested."""
    try:
        stored = report.model_copy(deep=True)
        if not store_raw_output:
            for test in stored.tests:
                test.input = "[suppressed]"
                test.output = "[suppressed]"
                for evaluation in test.evaluations:
                    evaluation.expected = None
                    evaluation.actual = None
                    evaluation.reason = (
                        "Passed." if evaluation.passed else "Contract not satisfied."
                    )
        with _get_db(path) as db:
            db.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?)",
                (
                    report.generated_at.isoformat(),
                    report.provider,
                    report.model,
                    stored.model_dump_json(),
                ),
            )
    except (sqlite3.Error, OSError):
        pass


def record_interaction(interaction: Interaction, path: Path | None = None) -> None:
    """Persist a captured interaction."""
    try:
        with _get_db(path) as db:
            db.execute(
                """
                INSERT OR REPLACE INTO interactions (
                    id, timestamp, provider, model, prompt, system_prompt, input,
                    variables_json, output, latency_ms, input_tokens, output_tokens,
                    estimated_cost_usd, tags_json, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    interaction.id,
                    interaction.timestamp.isoformat(),
                    interaction.provider,
                    interaction.model,
                    interaction.prompt,
                    interaction.system_prompt,
                    interaction.input,
                    json.dumps(interaction.variables),
                    interaction.output,
                    interaction.latency_ms,
                    interaction.input_tokens,
                    interaction.output_tokens,
                    interaction.estimated_cost_usd,
                    json.dumps(interaction.tags),
                    interaction.source,
                ),
            )
    except (sqlite3.Error, OSError):
        pass


def get_interactions(limit: int = 1000, path: Path | None = None) -> list[Interaction]:
    """Retrieve captured interactions."""
    try:
        with _get_db(path) as db:
            cursor = db.execute(
                """
                SELECT id, timestamp, provider, model, prompt, system_prompt, input,
                       variables_json, output, latency_ms, input_tokens, output_tokens,
                       estimated_cost_usd, tags_json, source
                FROM interactions ORDER BY timestamp DESC LIMIT ?
                """,
                (limit,),
            )
            interactions = []
            for row in cursor.fetchall():
                interactions.append(
                    Interaction(
                        id=row[0],
                        timestamp=datetime.fromisoformat(row[1]) if row[1] else datetime.now(UTC),
                        provider=row[2],
                        model=row[3],
                        prompt=row[4],
                        system_prompt=row[5],
                        input=row[6],
                        variables=json.loads(row[7]) if row[7] else {},
                        output=row[8],
                        latency_ms=row[9] or 0.0,
                        input_tokens=row[10],
                        output_tokens=row[11],
                        estimated_cost_usd=row[12],
                        tags=json.loads(row[13]) if row[13] else [],
                        source=row[14] or "capture",
                    )
                )
            return interactions
    except (sqlite3.Error, OSError):
        return []


def purge_storage(path: Path | None = None) -> bool:
    """Clear all local SQLite storage (interactions, runs, scenarios)."""
    try:
        with _get_db(path) as db:
            db.execute("DELETE FROM interactions")
            db.execute("DELETE FROM runs")
            db.execute("DELETE FROM scenarios")
            db.commit()
        return True
    except (sqlite3.Error, OSError):
        return False


def count_interactions(path: Path | None = None) -> int:
    """Return the number of captured interactions."""
    try:
        with _get_db(path) as db:
            row = db.execute("SELECT COUNT(*) FROM interactions").fetchone()
            return row[0] if row else 0
    except (sqlite3.Error, OSError):
        return 0


def purge_oldest_interactions(count: int, path: Path | None = None) -> int:
    """Delete the *count* oldest interactions (rolling retention).

    Returns the number of rows actually deleted.
    """
    if count <= 0:
        return 0
    try:
        with _get_db(path) as db:
            db.execute(
                """
                DELETE FROM interactions WHERE id IN (
                    SELECT id FROM interactions ORDER BY timestamp ASC LIMIT ?
                )
                """,
                (count,),
            )
            db.commit()
            return count
    except (sqlite3.Error, OSError):
        return 0


def purge_old_interactions(days: int, path: Path | None = None) -> int:
    """Delete interactions older than *days* days.

    Returns the number of rows deleted.
    """
    if days <= 0:
        return 0
    try:
        cutoff = datetime.now(UTC).isoformat()
        # Compute cutoff by subtracting days
        from datetime import timedelta

        cutoff_dt = datetime.now(UTC) - timedelta(days=days)
        cutoff = cutoff_dt.isoformat()
        with _get_db(path) as db:
            cursor = db.execute(
                "DELETE FROM interactions WHERE timestamp < ?",
                (cutoff,),
            )
            db.commit()
            return cursor.rowcount
    except (sqlite3.Error, OSError):
        return 0
