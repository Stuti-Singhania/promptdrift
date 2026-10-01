"""Baseline history archiving and retrieval.

Archives old baselines as timestamped JSON snapshots to .promptdrift/baseline_history/.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path


def archive_baseline(baseline_path: Path, history_dir: Path | None = None) -> Path | None:
    """Archive the current baseline to history directory if it exists.

    Returns the path to the newly created archive file, or None if no baseline existed.
    """
    if not baseline_path.is_file():
        return None

    history_dir = history_dir or baseline_path.parent / ".promptdrift" / "baseline_history"
    history_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamp for filename: YYYYMMDD_HHMMSS
    timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    archive_path = history_dir / f"baseline_{timestamp_str}.json"

    # In case of exact same second, append suffix
    counter = 1
    while archive_path.exists():
        archive_path = history_dir / f"baseline_{timestamp_str}_{counter}.json"
        counter += 1

    shutil.copy2(baseline_path, archive_path)
    return archive_path


def list_baseline_history(history_dir: Path = Path(".promptdrift/baseline_history")) -> list[Path]:
    """Return a list of archived baseline paths, sorted from newest to oldest."""
    if not history_dir.is_dir():
        return []

    paths = list(history_dir.glob("baseline_*.json"))
    # Sort descending (newest first) based on filename timestamp
    paths.sort(reverse=True)
    return paths
