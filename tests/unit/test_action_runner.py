"""Behavioral tests of the composite Action's real Python/CLI boundary."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("action_runner", ROOT / "action" / "run.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def monitor_report(status="PASS", diagnosis="stable"):
    return {
        "schema_version": 1,
        "run_id": "offline-run",
        "generated_at": "2026-01-01T00:00:00Z",
        "provider": "mock",
        "model": "local-echo",
        "samples": 3,
        "baseline_path": "baseline.json",
        "counts": {key: int(key == status) for key in runner.STATUSES},
        "diagnosis_counts": {diagnosis: 1},
        "tests": [
            {
                "test_id": "example",
                "status": status,
                "diagnosis": diagnosis,
                "summary": "Aggregate evidence only",
                "samples": 3,
                "failures": 3 if status == "FAIL" else 0,
                "provider_errors": 3 if status == "ERROR" else 0,
                "output_changes": 0,
                "evidence": ["Three samples evaluated"],
            }
        ],
    }


@pytest.fixture
def action_environment(tmp_path, monkeypatch):
    workspace = tmp_path / "checkout with spaces"
    workdir = workspace / "nested app"
    workdir.mkdir(parents=True)
    temp = tmp_path / "runner temp"
    temp.mkdir()
    output = tmp_path / "output.txt"
    step_summary = tmp_path / "summary.md"
    received = tmp_path / "received.json"
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("RUNNER_TEMP", str(temp))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("PROMPTDRIFT_WORKING_DIRECTORY", "nested app")
    monkeypatch.setenv("PROMPTDRIFT_INSTALL", "false")
    monkeypatch.setenv("PROMPTDRIFT_MODE", "monitor")
    monkeypatch.setenv("PROMPTDRIFT_SAMPLES", "3")
    monkeypatch.setenv("FAKE_CLI_RECEIVED", str(received))
    real_run = subprocess.run

    def local_cli(command, **kwargs):
        assert command[0] == "promptdrift"
        assert not kwargs.get("shell")
        return real_run(
            [sys.executable, str(ROOT / "tests/action/fake_cli.py"), *command[1:]], **kwargs
        )

    monkeypatch.setattr(runner.subprocess, "run", local_cli)

    def run(data=None, code=0, raw=None):
        monkeypatch.setenv("FAKE_CLI_STDOUT", json.dumps(data) if raw is None else raw)
        monkeypatch.setenv("FAKE_CLI_STATUS", str(code))
        assert runner.main() == 0, "execution defers failure until reports are published"
        outputs = dict(
            line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines()
        )
        report = json.loads(Path(outputs["result"]).read_text(encoding="utf-8"))
        markdown = Path(outputs["summary"]).read_text(encoding="utf-8")
        return outputs, report, markdown

    return run, workdir, received


@pytest.mark.parametrize(
    ("code", "status", "diagnosis"),
    [
        (0, "PASS", "stable"),
        (0, "WARN", "output_changed"),
        (1, "FAIL", "observed_model_drift"),
        (3, "ERROR", "provider_error"),
    ],
)
def test_monitor_preserves_codes_and_publishes_before_enforcement(
    action_environment, code, status, diagnosis
):
    run, workdir, received = action_environment
    outputs, data, markdown = run(monitor_report(status, diagnosis), code)
    assert outputs["exit_code"] == str(code)
    assert Path(outputs["result"]).is_absolute()
    assert not Path(outputs["result"]).is_relative_to(workdir)
    invocation = json.loads(received.read_text(encoding="utf-8"))
    assert Path(invocation["cwd"]) == workdir
    assert invocation["arguments"] == [
        "monitor",
        "--config",
        "promptdrift.yaml",
        "--samples",
        "3",
        "--json",
    ]
    assert data["counts"][status] == 1  # Cases, not samples.
    assert f"| {status} | 1 |" in markdown
    assert diagnosis in markdown
    assert len(outputs["scope"]) == 64


@pytest.mark.parametrize("code", [1, 2, 3, 17])
@pytest.mark.parametrize(
    "raw", ["", "provider failure: sk-sensitive", "[]", "{", '{"counts": null}']
)
def test_malformed_cli_output_does_not_mask_failure(action_environment, code, raw, capsys):
    run, _, _ = action_environment
    outputs, data, markdown = run(code=code, raw=raw)
    assert outputs["exit_code"] == str(code)
    assert data["exit_code"] == code
    assert data["error"]["type"] == "invalid_report"
    assert "sk-sensitive" not in json.dumps(data) + markdown + capsys.readouterr().out
    assert "No valid evaluation report" in markdown


@pytest.mark.parametrize(
    "raw", ["not-json", "null", '{"schema_version": 2}', '{"report": {}, "impact": NaN}']
)
def test_invalid_success_is_not_green(action_environment, raw):
    outputs, data, _ = action_environment[0](raw=raw)
    assert outputs["exit_code"] == "2"
    assert data["error"]


@pytest.mark.parametrize("code", [2, 3])
def test_error_envelopes_keep_codes_but_never_publish_provider_messages(action_environment, code):
    outputs, data, markdown = action_environment[0](
        {
            "error": {"type": "<script>@everyone", "message": "secret raw prompt provider payload"},
            "exit_code": code,
        },
        code,
    )
    assert outputs["exit_code"] == str(code)
    assert data["error"]["type"] == "cli_error"
    assert "secret raw prompt" not in json.dumps(data) + markdown
    assert "@everyone" not in markdown


@pytest.mark.parametrize("samples", ["0", "21", "abc", "3; touch owned", "2.5"])
def test_rejects_invalid_sample_input_before_cli(action_environment, monkeypatch, samples):
    monkeypatch.setenv("PROMPTDRIFT_SAMPLES", samples)
    outputs, _, _ = action_environment[0](monitor_report())
    assert outputs["exit_code"] == "2"
    assert not action_environment[2].exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("PROMPTDRIFT_MODE", "bogus"),
        ("PROMPTDRIFT_INSTALL", "yes"),
        ("GITHUB_EVENT_NAME", "pull_request_target"),
        ("PROMPTDRIFT_WORKING_DIRECTORY", "missing"),
    ],
)
def test_invalid_inputs_and_privileged_prs_do_not_execute(
    action_environment, monkeypatch, field, value
):
    monkeypatch.setenv(field, value)
    outputs, _, _ = action_environment[0](monitor_report())
    assert outputs["exit_code"] == "2"
    assert not action_environment[2].exists()


def test_check_mode_keeps_base_ref_as_one_literal_argument(action_environment, monkeypatch):
    monkeypatch.setenv("PROMPTDRIFT_MODE", "check")
    monkeypatch.setenv("PROMPTDRIFT_SAMPLES", "ignored in check mode")
    monkeypatch.setenv("PROMPTDRIFT_CONFIG", 'config space; $(touch OWNED) "quoted".yaml')
    monkeypatch.setenv("PROMPTDRIFT_BASE_REF", "ref with spaces; $(touch OWNED)")
    data = {
        "report": {},
        "impact": {
            "regressed": 1,
            "scenarios": [{"scenario_id": "case", "classification": "REGRESSED"}],
        },
    }
    outputs, report, markdown = action_environment[0](data, 1)
    args = json.loads(action_environment[2].read_text(encoding="utf-8"))["arguments"]
    assert args == [
        "check",
        "--config",
        os.environ["PROMPTDRIFT_CONFIG"],
        "--base",
        os.environ["PROMPTDRIFT_BASE_REF"],
        "--json",
    ]
    assert report == data
    assert outputs["exit_code"] == "1"
    assert "Regressed | 1" in markdown
    assert not (action_environment[1] / "OWNED").exists()


def test_monitor_ignores_base_and_drops_raw_fields(action_environment, monkeypatch):
    monkeypatch.setenv("PROMPTDRIFT_BASE_REF", "malicious base")
    data = monitor_report()
    data["raw_output"] = "sensitive payload"
    data["tests"][0].update(prompt="sensitive prompt", output="sensitive output")
    _, report, _ = action_environment[0](data)
    assert "--base" not in action_environment[2].read_text(encoding="utf-8")
    assert "sensitive" not in json.dumps(report)


def test_summary_escapes_markdown_mentions_and_redacts_keys(action_environment, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-private-example")
    monkeypatch.setenv("FAKE_CLI_STDERR", "sk-private-example provider response")
    data = monitor_report("FAIL", "observed_model_drift")
    data["tests"][0]["test_id"] = (
        "@everyone `x`\n![click](https://evil.test) <script> sk-private-example"
    )
    data["tests"][0]["summary"] = "Provider said secret words"
    data["tests"][0]["evidence"] = ["Not for GitHub comments"]
    _, report, markdown = action_environment[0](data, 1)
    assert "sk-private-example" not in json.dumps(report) + markdown
    assert "@everyone" not in markdown
    assert "@\u200beveryone" in markdown
    assert "![click]" not in markdown
    assert "<script>" not in markdown
    assert "Provider said" not in markdown
    assert "Not for GitHub comments" not in markdown


@pytest.mark.parametrize("depth", [600, 2000])
def test_deep_json_does_not_bypass_safe_error_reporting(action_environment, monkeypatch, depth):
    monkeypatch.setenv("PROMPTDRIFT_MODE", "check")
    raw = '{"report": {"nested": ' + "[" * depth + "0" + "]" * depth + '}, "impact": {}}'
    outputs, data, _ = action_environment[0](code=3, raw=raw)
    assert outputs["exit_code"] == "3"
    if "error" in data:
        assert data["error"]["type"] == "invalid_report"
    else:
        # Recursion limits differ across Python versions; safely handled nesting is valid.
        assert data["impact"] == {}


def test_oversized_report_keeps_cli_failure(action_environment, monkeypatch):
    monkeypatch.setattr(runner, "MAX_REPORT_BYTES", 20)
    outputs, data, _ = action_environment[0](monitor_report("FAIL"), 1)
    assert outputs["exit_code"] == "1"
    assert data["error"]["type"] == "invalid_report"


def test_missing_cli_still_publishes_action_error(action_environment, monkeypatch):
    def missing_cli(*args, **kwargs):
        raise FileNotFoundError("sensitive path not for publication")

    monkeypatch.setattr(runner.subprocess, "run", missing_cli)
    outputs, data, markdown = action_environment[0](monitor_report())
    assert outputs["exit_code"] == "2"
    assert data["error"]["type"] == "action_error"
    assert "sensitive path" not in markdown


def test_scope_stays_stable_and_can_be_namespaced(action_environment, monkeypatch):
    run = action_environment[0]
    first = run(monitor_report())[0]
    again = run(monitor_report())[0]
    assert first["result"] != again["result"]
    assert first["scope"] == again["scope"]
    monkeypatch.setenv("PROMPTDRIFT_ISSUE_SCOPE", "other-job")
    assert run(monitor_report())[0]["scope"] != first["scope"]


def test_pip_argument_is_not_shell_code_or_options(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setenv("PROMPTDRIFT_INSTALL", "true")
    monkeypatch.setenv("PROMPTDRIFT_VERSION", "package; $(touch OWNED)")

    def install(command, **kwargs):
        commands.append(command)
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert not kwargs.get("shell")
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(runner.subprocess, "run", install)
    data, code = runner.execute(tmp_path, "check", 3)
    assert code == 2 and data["error"]["type"] == "installation_failed"
    assert commands[0][-2:] == ["--", "package; $(touch OWNED)"]
    monkeypatch.setenv("PROMPTDRIFT_VERSION", "--index-url=https://evil.test")
    assert runner.execute(tmp_path, "check", 3)[0]["error"]["type"] == "invalid_package"
    assert len(commands) == 1


@pytest.mark.parametrize("code", ["0", "1", "2", "3", "17", "", "$(touch OWNED)"])
def test_enforce_exits_with_original_status(code):
    result = subprocess.run(
        [sys.executable, str(ROOT / "action/run.py"), "--enforce"],
        env={**os.environ, "PROMPTDRIFT_EXIT_CODE": code},
        capture_output=True,
        check=False,
    )
    assert result.returncode == (int(code) if code.isdecimal() else 2)
    assert not result.stdout and not result.stderr


def test_manifest_passes_inputs_only_through_environment_and_enforces_last():
    manifest = yaml.safe_load((ROOT / "action/action.yml").read_text(encoding="utf-8"))
    steps = manifest["runs"]["steps"]
    assert manifest["inputs"]["mode"]["default"] == "check"
    assert manifest["inputs"]["create-issue"]["default"] == "false"
    assert steps[-1]["name"] == "Enforce PromptDrift result"
    for step in steps:
        if "run" in step:
            assert "${{" not in step["run"]
        if "script" in step.get("with", {}):
            assert "${{" not in step["with"]["script"]
    upload = next(
        step for step in steps if step.get("uses", "").startswith("actions/upload-artifact")
    )
    assert upload["with"]["path"] == "${{ steps.run.outputs.result }}"


@pytest.mark.parametrize("code", [0, 1, 3])
@pytest.mark.parametrize("number", ["NaN", "Infinity", "1e999"])
def test_nonfinite_json_never_masks_result(action_environment, monkeypatch, code, number):
    monkeypatch.setenv("PROMPTDRIFT_MODE", "check")
    outputs, data, _ = action_environment[0](
        code=code, raw='{"report": {}, "impact": {"regressed": ' + number + "}}"
    )
    assert outputs["exit_code"] == str(code or 2)
    assert data["error"]["type"] == "invalid_report"


def test_real_mock_cli_monitor_and_baseline_are_compatible(tmp_path, monkeypatch):
    # Exercise this Action against the real package, not just a synthetic JSON producer.
    workdir = tmp_path / "real app"
    workdir.mkdir()
    (workdir / "prompt.txt").write_text("Refunds within 30 days.", encoding="utf-8")
    (workdir / "config.yml").write_text(
        "version: 1\nprovider: {type: mock, model: local-echo}\n"
        "baseline: {path: baseline.json}\ntests:\n"
        "  - id: refund\n    prompt: prompt.txt\n"
        "    assertions: [{type: contains, value: '30 days'}]\n",
        encoding="utf-8",
    )
    cli = [sys.executable, "-c", "from promptdrift.cli import main; main()"]
    baseline = subprocess.run(
        [*cli, "baseline", "--config", "config.yml"],
        cwd=workdir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    accepted = (workdir / "baseline.json").read_bytes()
    real_run = subprocess.run

    def local_cli(command, **kwargs):
        assert command[0] == "promptdrift"
        return real_run([*cli, *command[1:]], **kwargs)

    monkeypatch.setattr(runner.subprocess, "run", local_cli)
    monkeypatch.setenv("PROMPTDRIFT_INSTALL", "false")
    monkeypatch.setenv("PROMPTDRIFT_CONFIG", "config.yml")
    data, code = runner.execute(workdir, "monitor", 3)
    assert code == 0 and data["counts"]["PASS"] == 1, data
    assert data["tests"][0]["diagnosis"] == "stable"
    (workdir / "prompt.txt").write_text("No refunds available.", encoding="utf-8")
    data, code = runner.execute(workdir, "monitor", 3)
    assert code == 1 and data["counts"]["FAIL"] == 1, data
    assert data["tests"][0]["diagnosis"] == "prompt_changed"
    assert (workdir / "baseline.json").read_bytes() == accepted
    (workdir / "baseline.json").unlink()
    data, code = runner.execute(workdir, "monitor", 3)
    assert code == 2 and data["error"], data
    assert not (workdir / "baseline.json").exists()


def test_example_is_manual_gated_offline_and_has_minimal_permissions():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/monitor-example.yml").read_text(encoding="utf-8")
    )
    # PyYAML uses YAML 1.1, where the GitHub Actions key `on` is parsed as True.
    events = workflow.get("on", workflow.get(True))
    assert set(events) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is False
    job = workflow["jobs"]["monitor"]
    assert "PROMPTDRIFT_MONITOR_ENABLED" in job["if"]
    assert job["permissions"] == {"contents": "read", "issues": "write"}
    action = next(step for step in job["steps"] if step.get("uses") == "./action")
    assert action["with"]["version"] == "."
    assert action["with"]["config"] == "examples/monitoring/mock.yml"
    assert "env" not in action
    from promptdrift.config import load_config

    for name in ("mock", "openai"):
        config, config_path = load_config(str(ROOT / f"examples/monitoring/{name}.yml"))
        assert config.resolve_path(config_path, config.tests[0].prompt).is_file()
        assert config.baseline.store_raw_output is False


def test_github_publication_node_behaviors():
    node = shutil.which("node")
    if not node:
        if os.environ.get("CI"):
            pytest.fail("Node is required in CI for Action behavior tests")
        pytest.skip("Node is not installed")
    result = subprocess.run(
        [node, "--test", str(ROOT / "tests/action/publish.test.cjs")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
