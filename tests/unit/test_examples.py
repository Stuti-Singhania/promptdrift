"""Keep shipped examples executable without keys or checkout side effects."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from promptdrift.config import load_config
from promptdrift.engine.baseline import write_baseline
from promptdrift.engine.monitor import monitor_suite
from promptdrift.engine.runner import run_suite
from promptdrift.templates import render_prompt

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = sorted(
    [*ROOT.glob("examples/**/promptdrift.yaml"), *ROOT.glob("examples/monitoring/*.yml")]
)


@pytest.mark.parametrize("source", EXAMPLES, ids=lambda path: str(path.relative_to(ROOT)))
def test_example_configs_and_offline_workflow(source, tmp_path):
    copied = tmp_path / "examples"
    shutil.copytree(ROOT / "examples", copied)
    config, path = load_config(copied / source.relative_to(ROOT / "examples"))
    for case in config.tests:
        assert render_prompt(config.resolve_path(path, case.prompt), case.variables)
    if config.provider.type != "mock":
        # Paid-provider example is validated/rendered only, never silently charged.
        return
    report = run_suite(config, path)
    assert report.counts["FAIL"] == 0
    write_baseline(config.resolve_path(path, config.baseline.path), report)
    monitoring = monitor_suite(config, path, samples=2)
    assert monitoring.exit_code == 0
    assert monitoring.diagnosis_counts == {"stable": len(config.tests)}


def test_documentation_relative_links_exist():
    paths = [
        ROOT / "README.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "SECURITY.md",
        *ROOT.glob("docs/*.md"),
    ]
    missing = []
    for document in paths:
        for link in re.findall(r"\]\(([^\s)]+)\)", document.read_text(encoding="utf-8")):
            if "://" in link or link.startswith(("#", "mailto:")):
                continue
            target = link.split("#", 1)[0]
            if target and not (document.parent / target).exists():
                missing.append(f"{document.relative_to(ROOT)} -> {link}")
    assert not missing, "\n".join(missing)
