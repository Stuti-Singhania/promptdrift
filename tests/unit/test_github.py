"""Tests for GitHub markdown report generation."""

from pathlib import Path

from promptdrift.models import RegressionReport, TestRun
from promptdrift.models.result import EvaluationResult
from promptdrift.reports.github import MARKER, github_markdown


class TestGithubMarkdown:
    def test_contains_marker_for_comment_update(self, sample_report):
        report = sample_report()
        assert MARKER in github_markdown(report)

    def test_pass_verdict(self, sample_report):
        md = github_markdown(sample_report())
        assert "✅ All contracts passed" in md

    def test_fail_verdict(self):
        report = RegressionReport(
            provider="mock",
            model="m",
            tests=[
                TestRun(
                    test_id="broken",
                    provider="mock",
                    model="m",
                    input="",
                    output="",
                    latency_ms=0,
                    status="FAIL",
                    evaluations=[
                        EvaluationResult(
                            passed=False,
                            assertion="contains",
                            expected="x",
                            actual="y",
                            reason="Missing text",
                            severity="fail",
                        )
                    ],
                )
            ],
        )
        md = github_markdown(report)
        assert "❌ Regression detected" in md

    def test_warn_verdict(self):
        report = RegressionReport(
            provider="mock",
            model="m",
            tests=[
                TestRun(
                    test_id="soft",
                    provider="mock",
                    model="m",
                    input="",
                    output="",
                    latency_ms=0,
                    status="WARN",
                    evaluations=[
                        EvaluationResult(
                            passed=False,
                            assertion="contains",
                            expected="x",
                            actual="y",
                            reason="Missing text",
                            severity="warn",
                        )
                    ],
                )
            ],
        )
        md = github_markdown(report)
        assert "⚠️ Warnings detected" in md

    def test_multiple_tests(self, multi_test_report):
        md = github_markdown(multi_test_report)
        assert "passing" in md
        assert "warning" in md
        assert "failing" in md

    def test_summary_counts(self, multi_test_report):
        md = github_markdown(multi_test_report)
        assert "1 passed" in md
        assert "1 warnings" in md
        assert "1 failed" in md

    def test_includes_failure_reason(self):
        report = RegressionReport(
            provider="mock",
            model="m",
            tests=[
                TestRun(
                    test_id="a",
                    provider="mock",
                    model="m",
                    input="",
                    output="",
                    latency_ms=0,
                    status="FAIL",
                    evaluations=[
                        EvaluationResult(
                            passed=False,
                            assertion="contains",
                            expected="x",
                            actual="y",
                            reason="Required text missing",
                            severity="fail",
                        )
                    ],
                )
            ],
        )
        md = github_markdown(report)
        assert "Required text missing" in md

    def test_all_pass_shows_all_assertions_passed(self, sample_report):
        md = github_markdown(sample_report())
        assert "All assertions passed" in md


ACTION_PATH = Path(__file__).resolve().parents[2] / "action" / "action.yml"


class TestActionManifest:
    def test_action_defers_failure_until_reports_uploaded(self):
        manifest = ACTION_PATH.read_text(encoding="utf-8")
        assert "always() && inputs.upload-report" in manifest

    def test_action_enforces_result(self):
        manifest = ACTION_PATH.read_text(encoding="utf-8")
        assert "Enforce PromptDrift result" in manifest

    def test_action_blocks_fork_comments(self):
        manifest = ACTION_PATH.read_text(encoding="utf-8")
        assert "head.repo.fork == false" in manifest
