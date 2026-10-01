"""Resolve the same complete suite for baseline, monitoring and PR checks."""

from __future__ import annotations

from pathlib import Path

from promptdrift.errors import ConfigError
from promptdrift.models import Config, TestCase
from promptdrift.models.capture import Scenario
from promptdrift.storage.scenarios import load_scenarios


def scenario_to_test_case(
    scenario: Scenario, default_prompt: str = "prompts/example.txt"
) -> TestCase:
    variables = dict(scenario.variables)
    if "input" not in variables and scenario.input:
        variables["input"] = scenario.input
    return TestCase(
        id=scenario.id,
        prompt=scenario.prompt or default_prompt,
        variables=variables,
        assertions=scenario.assertions,
        thresholds=scenario.thresholds,
    )


def resolve_suite(
    config: Config, config_path: Path, scenario_file: Path | None = None
) -> tuple[Config, dict[str, dict]]:
    active = config.model_copy(deep=True)
    metadata: dict[str, dict] = {}
    path = scenario_file or config.resolve_path(
        config_path, config.scenarios.file if config.scenarios else ".promptdrift/scenarios.json"
    )
    if config.scenarios and not path.is_file():
        raise ConfigError("Configured scenario library does not exist.")
    if path.is_file():
        existing = {test.id for test in active.tests}
        for scenario in load_scenarios(path, strict=True).scenarios:
            if scenario.status == "promoted" and scenario.id not in existing:
                active.tests.append(scenario_to_test_case(scenario))
                existing.add(scenario.id)
                metadata[scenario.id] = {
                    "category": scenario.category or "general",
                    "prompt": scenario.prompt,
                }
    if not active.tests:
        raise ConfigError("No active tests. Add YAML tests or promote a scenario before running.")
    return active, metadata
