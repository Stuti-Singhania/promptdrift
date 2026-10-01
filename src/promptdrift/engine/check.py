"""Orchestration for git-aware selective scenario check and impact analysis."""

from __future__ import annotations

from pathlib import Path

from promptdrift.engine.baseline import load_baseline
from promptdrift.engine.runner import run_suite
from promptdrift.engine.suite import (  # noqa: F401 (public compatibility)
    resolve_suite,
    scenario_to_test_case,
)
from promptdrift.errors import ConfigError
from promptdrift.git import GitContext
from promptdrift.impact import ImpactRadiusReport, calculate_impact_radius
from promptdrift.models import Config, RegressionReport, TestCase


def orchestrate_check(
    config: Config,
    config_path: Path,
    *,
    base_ref: str | None = None,
    scenario_file: Path | None = None,
    selective: bool = True,
) -> tuple[RegressionReport, ImpactRadiusReport]:
    if base_ref and base_ref.startswith("-"):
        raise ConfigError("Git base refs must not start with '-'.")
    git = GitContext(root=config_path.parent)
    changed_files = git.get_changed_files(base_ref=base_ref)

    active_config, scenario_metadata = resolve_suite(config, config_path, scenario_file)
    tests = active_config.tests

    # Validate the baseline before making potentially billable provider calls.
    baseline_path = config.resolve_path(config_path, config.baseline.path)
    baseline = load_baseline(baseline_path) if baseline_path.exists() else None

    # Selective scenario execution if git changed files are available
    selected_tests = tests
    skipped_ids: set[str] = set()
    normalized_changes = {str(Path(item)).replace("\\", "/") for item in changed_files}
    prompt_names = {str(Path(test.prompt)).replace("\\", "/") for test in tests}
    # Unknown paths (code, config, scenario definitions or nested Git paths) may affect
    # every case. Only use the optimization when all changes map exactly to prompts.
    if selective and normalized_changes and normalized_changes <= prompt_names:
        affected: list[TestCase] = [
            test
            for test in tests
            if str(Path(test.prompt)).replace("\\", "/") in normalized_changes
        ]
        skipped_ids = {t.id for t in tests} - {t.id for t in affected}
        selected_tests = affected

    active_config.tests = selected_tests

    # If no tests exist to run, raise or return empty
    report = run_suite(active_config, config_path)

    if baseline is not None:
        report.baseline_path = str(baseline_path)

    current_git_sha = git.get_head_sha()
    prompt_paths = [config.resolve_path(config_path, t.prompt) for t in tests]
    current_prompt_hash = git.compute_prompt_hash(prompt_paths)

    impact = calculate_impact_radius(
        report,
        baseline,
        scenario_metadata=scenario_metadata,
        skipped_ids=skipped_ids,
        current_git_sha=current_git_sha,
        current_prompt_hash=current_prompt_hash,
    )
    return report, impact
