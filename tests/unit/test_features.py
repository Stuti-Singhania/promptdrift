"""Unit tests for Git-native features, capture, learning, suggestions, and impact radius."""

import subprocess

from promptdrift.engine.discovery import discover_scenarios
from promptdrift.engine.suggest import suggest_assertions_for_scenario
from promptdrift.git import GitContext
from promptdrift.impact import calculate_impact_radius, classify_scenario_change
from promptdrift.models import Baseline, BaselineTest, RegressionReport, TestRun
from promptdrift.models.capture import Interaction, Scenario
from promptdrift.models.result import EvaluationResult
from promptdrift.storage.sqlite import get_interactions, purge_storage, record_interaction


class TestGitContext:
    def test_git_repo_detection(self, tmp_path):
        subprocess.run(
            ["git", "init", "-b", "main", str(tmp_path)], check=True, capture_output=True
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(tmp_path),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "--allow-empty",
                "-m",
                "test",
            ],
            check=True,
            capture_output=True,
        )
        ctx = GitContext(root=tmp_path)
        assert ctx.is_git_repo() is True
        assert ctx.get_current_branch() is not None

    def test_changed_files_empty_or_list(self):
        ctx = GitContext()
        files = ctx.get_changed_files()
        assert isinstance(files, list)


class TestCaptureAndStorage:
    def test_capture_and_retrieve(self, tmp_path):
        db_path = tmp_path / "test_capture.db"
        interaction = Interaction(
            id="int_123",
            provider="mock",
            model="local-echo",
            prompt="prompts/test.txt",
            input="Hello world",
            output="Hello world back",
            tags=["test"],
        )
        record_interaction(interaction, path=db_path)
        items = get_interactions(path=db_path)
        assert len(items) == 1
        assert items[0].id == "int_123"
        assert items[0].input == "Hello world"

    def test_purge_storage(self, tmp_path):
        db_path = tmp_path / "test_purge.db"
        interaction = Interaction(
            id="int_456",
            provider="mock",
            model="local-echo",
            prompt="prompts/test.txt",
            input="To be purged",
            output="Purged",
        )
        record_interaction(interaction, path=db_path)
        assert len(get_interactions(path=db_path)) == 1
        assert purge_storage(path=db_path) is True
        assert len(get_interactions(path=db_path)) == 0


class TestDiscoveryAndLearning:
    def test_discover_scenarios_grouping(self):
        interactions = [
            Interaction(
                id="1",
                provider="mock",
                model="m",
                prompt="p.txt",
                input="I want a refund for my item",
                output="Refund policy: 30 days",
                tags=["refund"],
            ),
            Interaction(
                id="2",
                provider="mock",
                model="m",
                prompt="p.txt",
                input="Where is my refund?",
                output="Refunds take 5-7 business days",
                tags=["refund"],
            ),
            Interaction(
                id="3",
                provider="mock",
                model="m",
                prompt="p.txt",
                input="Speak to human representative",
                output="Connecting to agent",
                tags=["escalation"],
            ),
        ]
        scenarios = discover_scenarios(interactions)
        # v0.3: full-input fingerprinting → different inputs are separate scenarios
        assert len(scenarios) == 3
        categories = {s.category for s in scenarios}
        assert "refund" in categories
        assert "escalation" in categories


class TestContractSuggestions:
    def test_suggests_json_assertions_when_output_is_json(self):
        scenario = Scenario(id="json_case", input="get json", category="billing")
        interactions = [
            Interaction(
                id="1",
                provider="mock",
                model="m",
                prompt="p.txt",
                input="get json",
                output='{"status": "ok", "code": 200}',
            ),
            Interaction(
                id="2",
                provider="mock",
                model="m",
                prompt="p.txt",
                input="get json",
                output='{"status": "error", "code": 400}',
            ),
        ]
        assertions = suggest_assertions_for_scenario(scenario, interactions)
        types = [a.type for a in assertions]
        assert "json_valid" in types
        assert "json_schema" in types

    def test_suggests_length_bounds(self):
        scenario = Scenario(id="text_case", input="say hello", category="general")
        interactions = [
            Interaction(
                id="1",
                provider="mock",
                model="m",
                prompt="p.txt",
                input="say hello",
                output="Hello there! Nice to meet you today.",
            )
        ]
        assertions = suggest_assertions_for_scenario(scenario, interactions)
        types = [a.type for a in assertions]
        assert "min_length" in types
        assert "max_length" in types


class TestImpactRadiusAndClassification:
    def test_classification_unchanged(self):
        import hashlib

        output = "Valid unchanged output"
        out_hash = hashlib.sha256(output.encode()).hexdigest()
        baseline = Baseline(
            schema_version=2,
            promptdrift_version="0.1.0",
            generated_at="2026-09-19T00:00:00Z",
            provider={"type": "mock", "model": "m"},
            tests={
                "sc_1": BaselineTest(
                    output_hash=out_hash,
                    status="PASS",
                    assertions={"contains": True},
                    metrics={"latency_ms": 10.0, "estimated_cost_usd": 0.001},
                )
            },
        )
        current = TestRun(
            test_id="sc_1",
            provider="mock",
            model="m",
            input="test",
            output=output,
            latency_ms=12.0,
            status="PASS",
        )
        impact = classify_scenario_change(current, baseline)
        assert impact.classification == "UNCHANGED"

    def test_classification_changed_but_valid(self):
        import hashlib

        out_hash = hashlib.sha256(b"Old output").hexdigest()
        baseline = Baseline(
            schema_version=2,
            promptdrift_version="0.1.0",
            generated_at="2026-09-19T00:00:00Z",
            provider={"type": "mock", "model": "m"},
            tests={
                "sc_1": BaselineTest(
                    output_hash=out_hash,
                    status="PASS",
                    assertions={"contains": True},
                    metrics={"latency_ms": 10.0, "estimated_cost_usd": 0.001},
                )
            },
        )
        current = TestRun(
            test_id="sc_1",
            provider="mock",
            model="m",
            input="test",
            output="New worded output that satisfies all contracts",
            latency_ms=12.0,
            status="PASS",
        )
        impact = classify_scenario_change(current, baseline)
        assert impact.classification == "CHANGED_BUT_VALID"

    def test_classification_regressed(self):
        import hashlib

        out_hash = hashlib.sha256(b"Old output").hexdigest()
        baseline = Baseline(
            schema_version=2,
            promptdrift_version="0.1.0",
            generated_at="2026-09-19T00:00:00Z",
            provider={"type": "mock", "model": "m"},
            tests={
                "sc_1": BaselineTest(
                    output_hash=out_hash,
                    status="PASS",
                    assertions={"contains": True},
                    metrics={"latency_ms": 10.0, "estimated_cost_usd": 0.001},
                )
            },
        )
        current = TestRun(
            test_id="sc_1",
            provider="mock",
            model="m",
            input="test",
            output="Broken output",
            latency_ms=12.0,
            status="FAIL",
            evaluations=[
                EvaluationResult(
                    passed=False,
                    assertion="contains",
                    expected="key",
                    actual="Broken",
                    reason="Missing key",
                    severity="fail",
                )
            ],
        )
        impact = classify_scenario_change(current, baseline)
        assert impact.classification == "REGRESSED"

    def test_impact_radius_aggregation(self):
        import hashlib

        out_hash = hashlib.sha256(b"same").hexdigest()
        baseline = Baseline(
            schema_version=2,
            promptdrift_version="0.1.0",
            generated_at="2026-09-19T00:00:00Z",
            provider={"type": "mock", "model": "m"},
            tests={
                "s1": BaselineTest(
                    output_hash=out_hash, status="PASS", assertions={}, metrics={"latency_ms": 10}
                ),
                "s2": BaselineTest(
                    output_hash=out_hash, status="PASS", assertions={}, metrics={"latency_ms": 10}
                ),
            },
        )
        report = RegressionReport(
            provider="mock",
            model="m",
            tests=[
                TestRun(
                    test_id="s1",
                    provider="mock",
                    model="m",
                    input="a",
                    output="same",
                    latency_ms=10,
                    status="PASS",
                ),
                TestRun(
                    test_id="s2",
                    provider="mock",
                    model="m",
                    input="b",
                    output="different",
                    latency_ms=15,
                    status="PASS",
                ),
            ],
        )
        res = calculate_impact_radius(report, baseline)
        assert res.total_scenarios == 2
        assert res.unchanged == 1
        assert res.changed_but_valid == 1
        assert res.regressed == 0
        assert res.impact_radius_percentage == 50.0
