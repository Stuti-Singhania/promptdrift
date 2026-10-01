"""Integration tests for the PromptDrift CLI including capture, learn, check, promote."""

import io
import json

from rich.console import Console
from typer.testing import CliRunner

import promptdrift.cli as cli
from promptdrift.cli import app

runner = CliRunner()


class TestInitCommand:
    def test_creates_starter_files(self, tmp_path):
        result = runner.invoke(app, ["init", "--directory", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "promptdrift.yaml").is_file()
        assert (tmp_path / "prompts" / "example.txt").is_file()

    def test_creates_missing_target_directory(self, tmp_path):
        target = tmp_path / "new-project"
        result = runner.invoke(app, ["init", "--directory", str(target)])
        assert result.exit_code == 0, result.output
        assert (target / "promptdrift.yaml").is_file()
        assert (target / "prompts" / "example.txt").is_file()

    def test_missing_target_is_initialized_on_a_non_utf_console(self, tmp_path, monkeypatch):
        stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        monkeypatch.setattr(cli, "console", Console(file=stream, color_system=None))
        result = runner.invoke(app, ["init", "--directory", str(tmp_path / "new-project")])
        assert result.exit_code == 0, result.output

    def test_refuses_overwrite_without_force(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["init", "--directory", str(tmp_path)])
        assert result.exit_code == 2

    def test_force_replaces_files(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["init", "--directory", str(tmp_path), "--force"])
        assert result.exit_code == 0


class TestTestCommand:
    def test_runs_and_passes(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["test", "--config", str(tmp_path / "promptdrift.yaml")])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(
            app, ["test", "--config", str(tmp_path / "promptdrift.yaml"), "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["tests"][0]["status"] == "PASS"

    def test_missing_config_fails(self, tmp_path):
        result = runner.invoke(app, ["test", "--config", str(tmp_path / "missing.yaml")])
        assert result.exit_code != 0


class TestBaselineCommand:
    def test_creates_baseline(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml")])
        assert result.exit_code == 0
        assert (tmp_path / "promptdrift.baseline.json").is_file()

    def test_refuses_overwrite_without_force(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        runner.invoke(app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml")])
        result = runner.invoke(app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml")])
        assert result.exit_code != 0

    def test_force_replaces_baseline(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        runner.invoke(app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml")])
        result = runner.invoke(
            app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml"), "--force"]
        )
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(
            app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml"), "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "baseline" in data


class TestDiffCommand:
    def test_diff_with_baseline(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        runner.invoke(app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml")])
        result = runner.invoke(app, ["diff", "--config", str(tmp_path / "promptdrift.yaml")])
        assert result.exit_code == 0

    def test_diff_without_baseline(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["diff", "--config", str(tmp_path / "promptdrift.yaml")])
        assert result.exit_code == 0


class TestReportCommand:
    def test_creates_html_report(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        output_path = tmp_path / "report.html"
        result = runner.invoke(
            app,
            [
                "report",
                "--config",
                str(tmp_path / "promptdrift.yaml"),
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0
        assert output_path.is_file()


class TestDoctorCommand:
    def test_doctor_passes(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["doctor", "--config", str(tmp_path / "promptdrift.yaml")])
        assert result.exit_code == 0

    def test_doctor_privacy(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(
            app, ["doctor", "--config", str(tmp_path / "promptdrift.yaml"), "--privacy"]
        )
        assert result.exit_code == 0

    def test_doctor_json(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(
            app, ["doctor", "--config", str(tmp_path / "promptdrift.yaml"), "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "checks" in data
        assert all(c["passed"] for c in data["checks"])

    def test_doctor_missing_config(self, tmp_path):
        result = runner.invoke(app, ["doctor", "--config", str(tmp_path / "missing.yaml")])
        assert result.exit_code != 0


class TestVersionCommand:
    def test_prints_version(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        from promptdrift import __version__

        assert __version__ in result.output


class TestNewLifecycleCommands:
    def test_capture_learn_promote_check(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])

        # 1. Capture interaction
        res_cap = runner.invoke(
            app,
            [
                "capture",
                "--input",
                "How do I cancel my order?",
                "--output",
                "You can cancel your order within 24 hours.",
                "--json",
            ],
        )
        assert res_cap.exit_code == 0

        # 2. Learn candidate scenarios
        res_learn = runner.invoke(app, ["learn", "--json"])
        assert res_learn.exit_code == 0
        scenarios = json.loads(res_learn.output)
        assert len(scenarios) > 0
        first_id = scenarios[0]["id"]

        # 3. Suggest contracts
        res_sug = runner.invoke(app, ["suggest", first_id, "--json"])
        assert res_sug.exit_code == 0
        suggestions = json.loads(res_sug.output)
        assert len(suggestions) > 0

        # 4. Promote
        res_prom = runner.invoke(app, ["promote", first_id])
        assert res_prom.exit_code == 0

        # 5. Check
        res_check = runner.invoke(
            app, ["check", "--config", str(tmp_path / "promptdrift.yaml"), "--json"]
        )
        assert res_check.exit_code == 0
        check_data = json.loads(res_check.output)
        assert "impact" in check_data
        assert "report" in check_data

        # 6. Accept
        res_accept = runner.invoke(app, ["accept", "--config", str(tmp_path / "promptdrift.yaml")])
        assert res_accept.exit_code == 0

        # 7. Purge
        res_purge = runner.invoke(app, ["purge", "--yes"])
        assert res_purge.exit_code == 0
