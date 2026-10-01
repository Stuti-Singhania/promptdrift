"""Read/write deterministic, Git-friendly baselines with v1/v2 schema compatibility."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from promptdrift import __version__
from promptdrift.errors import BaselineError
from promptdrift.models import Baseline, BaselineTest, RegressionReport


def baseline_from_report(
    report: RegressionReport,
    prompt_revision: str | None = None,
    git_sha: str | None = None,
    prompt_hash: str | None = None,
) -> Baseline:
    return Baseline(
        schema_version=3,
        promptdrift_version=__version__,
        generated_at=datetime.now(UTC),
        provider={"type": report.provider, "model": report.model},
        prompt_revision=prompt_revision,
        git_sha=git_sha,
        prompt_hash=prompt_hash,
        tests={
            run.test_id: BaselineTest(
                output_hash=hashlib.sha256(run.output.encode()).hexdigest(),
                provenance=run.provenance,
                status=run.status,
                assertions={
                    evaluation.assertion: evaluation.passed for evaluation in run.evaluations
                },
                metrics={
                    "latency_ms": run.latency_ms,
                    "input_tokens": run.input_tokens,
                    "output_tokens": run.output_tokens,
                    "estimated_cost_usd": run.estimated_cost_usd,
                },
                evaluator_scores={},
                metadata={},
            )
            for run in report.tests
        },
    )


def write_baseline(
    path: Path,
    report: RegressionReport,
    *,
    force: bool = False,
    prompt_revision: str | None = None,
    git_sha: str | None = None,
    prompt_hash: str | None = None,
) -> None:
    if path.exists() and not force:
        raise BaselineError(f"Baseline already exists: {path}. Use --force to replace it.")

    if path.is_file():
        from promptdrift.engine.baseline_history import archive_baseline

        archive_baseline(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    baseline_obj = baseline_from_report(
        report, prompt_revision=prompt_revision, git_sha=git_sha, prompt_hash=prompt_hash
    )
    content = baseline_obj.model_dump_json(indent=2) + "\n"
    atomic_write(path, content)


def load_baseline(path: Path) -> Baseline:
    if not path.is_file():
        raise BaselineError(f"Baseline file not found: {path}. Run 'promptdrift baseline' first.")
    try:
        raw_text = path.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(raw_text)
        # Migrate schema_version 1 to schema_version 2 dynamically
        if data.get("schema_version") == 1:
            data["schema_version"] = 2
            for test_data in data.get("tests", {}).values():
                if "evaluator_scores" not in test_data:
                    test_data["evaluator_scores"] = {}
                if "metadata" not in test_data:
                    test_data["metadata"] = {}
        return Baseline.model_validate(data)
    except (ValidationError, json.JSONDecodeError, AttributeError, TypeError, OSError) as exc:
        raise BaselineError(
            f"Invalid baseline {path.name} or unreadable file ({type(exc).__name__})."
        ) from exc


def atomic_write(path: Path, content: str) -> None:
    """Keep the previous canonical file intact if serialization/writing is interrupted."""
    import os
    import tempfile

    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise BaselineError(
            f"Unable to write baseline {path.name} ({type(exc).__name__})."
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
