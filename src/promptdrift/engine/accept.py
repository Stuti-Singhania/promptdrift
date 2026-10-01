"""Selective baseline acceptance logic."""

from __future__ import annotations

from promptdrift.engine.baseline import baseline_from_report
from promptdrift.errors import BaselineError, PromptDriftError
from promptdrift.impact import ImpactRadiusReport
from promptdrift.models.baseline import Baseline
from promptdrift.models.result import RegressionReport


def selective_accept(
    current_baseline: Baseline,
    report: RegressionReport,
    impact: ImpactRadiusReport,
    scenario_ids: list[str] | None = None,
    accept_changed: bool = False,
    accept_regressions: bool = False,
) -> Baseline:
    """Selectively accept scenarios into a new baseline.

    Rules:
    - If scenario_ids is provided, ONLY those scenarios are accepted.
    - If accept_changed is True, all CHANGED_BUT_VALID scenarios are accepted.
    - REGRESSED scenarios are blocked unless accept_regressions is True.
    - NOT_EVALUATED scenarios are NEVER modified (copied from current_baseline).
    - IMPROVED, UNCHANGED, NEW are accepted by default (unless scenario_ids restricts).

    Returns a new Baseline object merging the accepted changes with the unaccepted
    parts of the current baseline.
    """
    if scenario_ids is not None:
        unknown = set(scenario_ids) - {run.test_id for run in report.tests}
        if unknown:
            raise BaselineError(
                "Requested scenarios were not evaluated: " + ", ".join(sorted(unknown))
            )
    new_baseline_obj = baseline_from_report(report)

    # We will build the new tests dictionary by picking either from current_baseline or new_baseline_obj
    merged_tests = {}

    # First, copy over everything from current baseline
    for test_id, current_test in current_baseline.tests.items():
        merged_tests[test_id] = current_test

    errors = []

    # Build classification lookup
    classifications = {s.scenario_id: s.classification for s in impact.scenarios}

    # We iterate over all tests in the new report
    for test_id, new_test in new_baseline_obj.tests.items():
        classification = classifications.get(test_id, "NOT_EVALUATED")

        if classification == "NOT_EVALUATED":
            # Never modify NOT_EVALUATED
            continue

        if scenario_ids is not None and test_id not in scenario_ids:
            # Skip if specific IDs were requested and this is not one of them
            continue

        if classification == "REGRESSED":
            if not accept_regressions:
                errors.append(test_id)
                continue

        if classification == "CHANGED_BUT_VALID":
            # Only accept if --changed was specified, or if specifically requested by ID
            if not accept_changed and (scenario_ids is None or test_id not in scenario_ids):
                continue

        # If we made it here, we accept the new test
        merged_tests[test_id] = new_test

    if errors:
        raise PromptDriftError(
            f"Cannot accept {len(errors)} REGRESSED scenario(s) without --accept-regressions:\n"
            + "\n".join(f"  - {tid}" for tid in errors)
        )

    # Return a new baseline with the merged tests and updated revision info
    from promptdrift.git import GitContext

    current_git_sha = (
        impact.current_git_sha if impact.current_git_sha else GitContext().get_head_sha()
    )

    return Baseline(
        schema_version=new_baseline_obj.schema_version,
        promptdrift_version=new_baseline_obj.promptdrift_version,
        generated_at=new_baseline_obj.generated_at,
        provider=new_baseline_obj.provider,
        prompt_revision=new_baseline_obj.prompt_revision,
        git_sha=current_git_sha,
        prompt_hash=impact.current_prompt_hash,
        tests=merged_tests,
    )
