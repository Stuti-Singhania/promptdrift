"""Shared fixtures for PromptDrift tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from promptdrift.models.result import EvaluationResult, ModelResponse, RegressionReport, TestRun


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    """Never let offline tests mutate a checkout, real home, or captured traffic."""
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    workspace.mkdir()
    home.mkdir()
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))


@pytest.fixture
def mock_response():
    """Create a ModelResponse with default values."""

    def _make(output="hello world", latency_ms=12.0, input_tokens=5, output_tokens=2, cost=0.001):
        return ModelResponse(
            output=output,
            latency_ms=latency_ms,
            model="test-model",
            provider="mock",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
        )

    return _make


@pytest.fixture
def sample_report():
    """Create a RegressionReport with one passing test."""

    def _make(test_id="hello", status="PASS", output="hello world", evaluations=None):
        return RegressionReport(
            provider="mock",
            model="test-model",
            tests=[
                TestRun(
                    test_id=test_id,
                    provider="mock",
                    model="test-model",
                    input="test prompt",
                    output=output,
                    latency_ms=10.0,
                    input_tokens=3,
                    output_tokens=2,
                    estimated_cost_usd=0.0,
                    evaluations=evaluations or [],
                    status=status,
                )
            ],
        )

    return _make


@pytest.fixture
def multi_test_report():
    """Create a report with PASS, WARN, and FAIL tests."""
    return RegressionReport(
        provider="mock",
        model="test-model",
        tests=[
            TestRun(
                test_id="passing",
                provider="mock",
                model="test-model",
                input="p1",
                output="ok",
                latency_ms=5.0,
                status="PASS",
            ),
            TestRun(
                test_id="warning",
                provider="mock",
                model="test-model",
                input="p2",
                output="warn",
                latency_ms=5.0,
                evaluations=[
                    EvaluationResult(
                        passed=False,
                        assertion="contains",
                        expected="expected",
                        actual="warn",
                        reason="Required text missing",
                        severity="warn",
                    )
                ],
                status="WARN",
            ),
            TestRun(
                test_id="failing",
                provider="mock",
                model="test-model",
                input="p3",
                output="bad",
                latency_ms=5.0,
                evaluations=[
                    EvaluationResult(
                        passed=False,
                        assertion="contains",
                        expected="good",
                        actual="bad",
                        reason="Required text missing",
                        severity="fail",
                    )
                ],
                status="FAIL",
            ),
        ],
    )


@pytest.fixture
def minimal_config_yaml():
    """Return valid minimal YAML config string."""
    return "version: 1\nprovider: {type: mock}\ntests:\n  - id: hello\n    prompt: hello.txt\n"


@pytest.fixture
def config_dir(tmp_path, minimal_config_yaml):
    """Create a temp directory with a valid config and prompt file."""
    config_path = tmp_path / "promptdrift.yaml"
    config_path.write_text(minimal_config_yaml, encoding="utf-8")
    prompt_path = tmp_path / "hello.txt"
    prompt_path.write_text("Say hello: {{ input }}", encoding="utf-8")
    return tmp_path
