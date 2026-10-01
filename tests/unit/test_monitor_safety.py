"""Preflight, storage and provider safety regression tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from promptdrift.cli import app
from promptdrift.engine.baseline import atomic_write, load_baseline, write_baseline
from promptdrift.engine.check import orchestrate_check
from promptdrift.engine.runner import evaluate_response
from promptdrift.errors import BaselineError, ConfigError, ProviderError
from promptdrift.models import Config
from promptdrift.models.config import ProviderConfig
from promptdrift.models.result import ModelResponse
from promptdrift.models.test import Assertion
from promptdrift.models.test import TestCase as Case
from promptdrift.providers.ollama import OllamaProvider
from promptdrift.providers.openai import OpenAIProvider
from promptdrift.storage.sqlite import record_report


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"choices": []},
        {"choices": None},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": 123}}]},
        {"choices": [{"message": {"content": "PRIVATE"}}], "usage": []},
    ],
)
def test_malformed_openai_response_is_safe_provider_error(monkeypatch, payload):
    monkeypatch.setenv("TEST_FIXTURE_KEY", "fixture-only")
    monkeypatch.setattr(
        "httpx.post",
        lambda *args, **kwargs: httpx.Response(
            200, json=payload, request=httpx.Request("POST", "https://example.invalid")
        ),
    )
    with pytest.raises(ProviderError) as error:
        OpenAIProvider(ProviderConfig(type="openai", api_key_env="TEST_FIXTURE_KEY")).complete(
            "PRIVATE", temperature=0, max_output_tokens=10
        )
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize(
    "payload", [[], {}, {"response": None}, {"response": ["PRIVATE"]}, {"error": "PRIVATE"}]
)
def test_malformed_ollama_response_is_safe_provider_error(monkeypatch, payload):
    monkeypatch.setattr(
        "httpx.post",
        lambda *args, **kwargs: httpx.Response(
            200, json=payload, request=httpx.Request("POST", "http://localhost")
        ),
    )
    with pytest.raises(ProviderError) as error:
        OllamaProvider(ProviderConfig(type="ollama")).complete(
            "PRIVATE", temperature=0, max_output_tokens=10
        )
    assert "PRIVATE" not in str(error.value)


def test_response_provenance_is_normalized(monkeypatch):
    monkeypatch.setenv("TEST_FIXTURE_KEY", "fixture-only")
    payload = {
        "choices": [{"message": {"content": "ok"}}],
        "model": "resolved-v2",
        "system_fingerprint": "fp-test",
    }
    monkeypatch.setattr(
        "httpx.post",
        lambda *args, **kwargs: httpx.Response(
            200, json=payload, request=httpx.Request("POST", "https://example.invalid")
        ),
    )
    response = OpenAIProvider(
        ProviderConfig(type="openai", model="alias", api_key_env="TEST_FIXTURE_KEY")
    ).complete("x", temperature=0, max_output_tokens=10)
    assert response.model == "alias"
    assert response.resolved_model == "resolved-v2"
    assert response.system_fingerprint == "fp-test"


@pytest.mark.parametrize("value", ["many", -1, float("nan"), float("inf"), True, 1.5])
def test_invalid_numeric_contracts_rejected_before_calls(value):
    with pytest.raises(ValidationError):
        Assertion(type="max_tokens", value=value)


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "nonsense"},
        {"$ref": "https://example.invalid/private"},
        {"properties": {"x": {"$dynamicRef": "file:///secret"}}},
    ],
)
def test_invalid_or_remote_schemas_rejected(schema):
    with pytest.raises(ValidationError):
        Assertion(type="json_schema", schema=schema)


def test_unknown_cost_and_tokens_cannot_satisfy_limits():
    response = ModelResponse(output="text", latency_ms=1, provider="mock", model="m")
    case = Case(
        id="x",
        prompt="x.txt",
        assertions=[Assertion(type="max_tokens", value=10), Assertion(type="cost_usd", value=1)],
        thresholds={"cost_usd": 1},
    )
    results = evaluate_response(case, response)
    assert len(results) == 3
    assert all(not result.passed and result.actual is None for result in results)


def test_suppressed_history_contains_no_evaluation_payload(sample_report, tmp_path):
    from promptdrift.models.result import EvaluationResult

    report = sample_report(
        output="PRIVATE_OUTPUT",
        evaluations=[
            EvaluationResult(
                passed=False,
                assertion="schema",
                actual="PRIVATE_OUTPUT",
                expected="PRIVATE_EXPECTED",
                reason="PRIVATE_OUTPUT did not match",
            )
        ],
    )
    path = tmp_path / "runs.db"
    record_report(report, path=path)
    with sqlite3.connect(path) as db:
        content = db.execute("SELECT report_json FROM runs").fetchone()[0]
    assert "PRIVATE" not in content
    assert report.tests[0].output == "PRIVATE_OUTPUT"  # Do not mutate the live report.


def test_atomic_write_failure_preserves_old_baseline(tmp_path, monkeypatch):
    path = tmp_path / "baseline.json"
    path.write_text("old", encoding="utf-8")

    def interrupted(*args):
        raise OSError("disk failure")

    monkeypatch.setattr("os.replace", interrupted)
    with pytest.raises(BaselineError):
        atomic_write(path, "new")
    assert path.read_text(encoding="utf-8") == "old"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["baseline.json", "home", "workspace"]


@pytest.mark.parametrize("data", [[], None, 123, {"schema_version": 999}])
def test_invalid_baseline_shapes_are_domain_errors(tmp_path, data):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BaselineError):
        load_baseline(path)


def test_baseline_archive_is_project_relative(sample_report, tmp_path):
    path = tmp_path / "project" / "baseline.json"
    write_baseline(path, sample_report())
    write_baseline(path, sample_report(output="next"), force=True)
    assert len(list((path.parent / ".promptdrift" / "baseline_history").glob("*.json"))) == 1
    assert not (Path.cwd() / ".promptdrift" / "baseline_history").exists()


def test_check_cannot_swallow_corrupt_baseline(config_dir, monkeypatch):
    from promptdrift.config import load_config

    config, path = load_config(config_dir / "promptdrift.yaml")
    (config_dir / config.baseline.path).write_text("broken", encoding="utf-8")
    calls = []
    monkeypatch.setattr("promptdrift.engine.check.run_suite", lambda *args: calls.append(True))
    with pytest.raises(BaselineError):
        orchestrate_check(config, path)
    assert not calls


def test_empty_resolved_suite_is_not_green(tmp_path):
    config = Config.model_validate(
        {"version": 2, "provider": {"type": "mock"}, "sources": {"prompts": ["prompts/**"]}}
    )
    with pytest.raises(ConfigError, match="No active tests"):
        orchestrate_check(config, tmp_path / "config.yaml")


def test_baseline_refuses_failing_contract_unless_explicit(config_dir):
    path = config_dir / "promptdrift.yaml"
    path.write_text(
        "provider: {type: mock}\ntests:\n- id: hello\n  prompt: hello.txt\n  variables: {input: hello}\n  assertions: [{type: contains, value: absent}]\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(app, ["baseline", "-c", str(path)])
    assert result.exit_code == 2
    assert not (config_dir / "promptdrift.baseline.json").exists()
    result = runner.invoke(app, ["baseline", "-c", str(path), "--accept-regressions"])
    assert result.exit_code == 0, result.output
    assert load_baseline(config_dir / "promptdrift.baseline.json").tests["hello"].status == "FAIL"


def test_existing_baseline_rejected_before_provider_calls(config_dir, monkeypatch):
    path = config_dir / "promptdrift.yaml"
    (config_dir / "promptdrift.baseline.json").write_text("placeholder", encoding="utf-8")
    calls = []
    monkeypatch.setattr("promptdrift.cli.run_suite", lambda *args: calls.append(True))
    assert CliRunner().invoke(app, ["baseline", "-c", str(path)]).exit_code == 2
    assert not calls


def test_semantic_enabled_is_not_silently_ignored():
    with pytest.raises(ValidationError):
        Config.model_validate(
            {
                "provider": {"type": "mock"},
                "tests": [{"id": "x", "prompt": "x.txt"}],
                "evaluation": {"semantic": {"enabled": True}},
            }
        )


def test_corrupt_scenario_library_is_not_silently_skipped(config_dir):
    from promptdrift.config import load_config

    config, path = load_config(config_dir / "promptdrift.yaml")
    scenario_path = config_dir / ".promptdrift" / "scenarios.json"
    scenario_path.parent.mkdir()
    scenario_path.write_text("broken", encoding="utf-8")
    with pytest.raises(ConfigError, match="Scenario library"):
        orchestrate_check(config, path)


def test_json_output_format_is_an_enforced_contract():
    case = Case(id="json", prompt="x.txt", output={"format": "json"})
    response = ModelResponse(output="not json", latency_ms=1, provider="mock", model="m")
    results = evaluate_response(case, response)
    assert len(results) == 1
    assert not results[0].passed
    assert results[0].assertion == "output.format"


@pytest.mark.parametrize("policy", [{"ci": {"fail_on": []}}, {"policy": {"warn_on": ["anything"]}}])
def test_unsupported_policy_is_not_silently_ignored(policy):
    with pytest.raises(ValidationError):
        Config.model_validate(
            {"provider": {"type": "mock"}, "tests": [{"id": "x", "prompt": "x.txt"}], **policy}
        )


@pytest.mark.parametrize(
    "metrics",
    [
        {"latency_ms": -1},
        {"latency_ms": float("nan")},
        {"output_tokens": -1},
        {"estimated_cost_usd": float("inf")},
    ],
)
def test_provider_metric_validation(metrics):
    values = {"output": "x", "latency_ms": 1, "provider": "mock", "model": "m", **metrics}
    with pytest.raises(ValidationError):
        ModelResponse(**values)


def test_demo_is_synthetic_network_local_and_has_no_persistent_files():
    before = set(Path.cwd().iterdir())
    result = CliRunner().invoke(app, ["demo", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["diagnosis_counts"] == {"observed_model_drift": 1}
    assert "Synthetic local fixture" in data["warnings"][0]
    assert set(Path.cwd().iterdir()) == before
