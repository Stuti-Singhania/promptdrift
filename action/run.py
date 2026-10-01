"""Execute the CLI without a shell; publish reports before a separate enforcement step."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DIAGNOSES = {
    "stable",
    "observed_model_drift",
    "prompt_changed",
    "configuration_changed",
    "contract_changed",
    "provider_changed",
    "provider_error",
    "insufficient_evidence",
    "new_test",
    "stochastic_behavior",
    "output_changed",
}
STATUSES = ("PASS", "WARN", "FAIL", "ERROR")
MAX_REPORT_BYTES = 10 * 1024 * 1024


def error_report(kind: str, code: int) -> dict:
    # CLI error text/stderr can contain provider payloads, URLs or credentials.
    return {
        "error": {
            "type": kind,
            "message": "PromptDrift could not complete. Check configuration, baseline and provider access locally.",
        },
        "exit_code": code,
    }


def finite_number(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite JSON number")
    return number


def integer(value: object, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError("invalid count")
    return value


def text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid text")
    return value


def validate_report(data: object, mode: str, code: int, samples: int) -> dict:
    if not isinstance(data, dict):
        raise ValueError("report must be an object")
    if "error" in data:
        if not isinstance(data["error"], dict) or code == 0:
            raise ValueError("invalid error report")
        return error_report("cli_error", code)
    if mode == "check":
        if not isinstance(data.get("report"), dict) or not isinstance(data.get("impact"), dict):
            raise ValueError("invalid check report")
        return data
    if data.get("schema_version") != 1 or type(data.get("schema_version")) is not int:
        raise ValueError("unsupported monitor schema")
    if integer(data.get("samples"), minimum=1) != samples:
        raise ValueError("unexpected sample count")
    counts = {status: integer(data["counts"][status]) for status in STATUSES}
    diagnoses = data["diagnosis_counts"]
    if not isinstance(diagnoses, dict) or set(diagnoses) - DIAGNOSES:
        raise ValueError("invalid diagnoses")
    diagnoses = {label: integer(count) for label, count in diagnoses.items()}
    if not isinstance(data.get("tests"), list):
        raise ValueError("invalid tests")
    tests = []
    observed_counts = dict.fromkeys(STATUSES, 0)
    observed_diagnoses: dict[str, int] = {}
    for case in data["tests"]:
        if case["status"] not in STATUSES or case["diagnosis"] not in DIAGNOSES:
            raise ValueError("unknown status or diagnosis")
        if not isinstance(case["evidence"], list):
            raise ValueError("invalid evidence")
        # Project only the public monitor schema. Never persist extra raw prompt/output fields.
        clean = {key: text(case[key]) for key in ("test_id", "status", "diagnosis", "summary")}
        clean.update(
            {
                key: integer(case[key])
                for key in ("samples", "failures", "provider_errors", "output_changes")
            }
        )
        clean["evidence"] = [text(item) for item in case["evidence"]]
        tests.append(clean)
        observed_counts[case["status"]] += 1
        observed_diagnoses[case["diagnosis"]] = observed_diagnoses.get(case["diagnosis"], 0) + 1
    if counts != observed_counts or {k: v for k, v in diagnoses.items() if v} != observed_diagnoses:
        raise ValueError("inconsistent case counts")
    if code not in (0, 1, 3) or (code == 0 and (counts["FAIL"] or counts["ERROR"])):
        raise ValueError("inconsistent monitor exit status")
    return {
        "schema_version": 1,
        **{
            key: text(data[key])
            for key in ("run_id", "generated_at", "provider", "model", "baseline_path")
        },
        "samples": samples,
        "counts": counts,
        "diagnosis_counts": diagnoses,
        "tests": tests,
    }


def redact(value: object) -> object:
    """Defense in depth for explicitly supplied credentials, including check artifacts."""
    secrets = {
        value
        for key, value in os.environ.items()
        if re.search(r"(?:KEY|TOKEN|SECRET|PASSWORD)$", key, re.IGNORECASE) and len(value) >= 4
    }

    def visit(item: object) -> object:
        if isinstance(item, str):
            for secret in sorted(secrets, key=len, reverse=True):
                item = item.replace(secret, "[REDACTED]")
            return item
        if isinstance(item, dict):
            return {visit(key): visit(val) for key, val in item.items()}
        if isinstance(item, list):
            return [visit(val) for val in item]
        return item

    return visit(value)


def safe_markdown(value: object) -> str:
    value = re.sub(r"[\x00-\x1f\x7f]", " ", str(value))[:180]
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    value = re.sub(r"([\\`*_{}\[\]()#+.!|~-])", r"\\\1", value)
    return value.replace("@", "@\u200b")


def summary(data: dict, mode: str, code: int) -> str:
    lines = [f"## PromptDrift {mode if mode in ('check', 'monitor') else 'run'}", ""]
    if "error" in data:
        lines += [f"Run failed (exit code {code}). No valid evaluation report is available."]
    elif mode == "monitor":
        lines += [
            "Contract/provider failure detected."
            if code
            else "No contract or provider failures detected.",
            "Changed-but-valid behavior is informational, not a contract failure.",
            "",
            "| Case status | Count |",
            "| --- | ---: |",
            *[f"| {status} | {data['counts'][status]} |" for status in STATUSES],
            "",
            f"Samples requested per case: {data['samples']}",
            "",
            "| Diagnosis | Cases |",
            "| --- | ---: |",
            *[
                f"| {label} | {count} |"
                for label, count in sorted(data["diagnosis_counts"].items())
            ],
        ]
        failures = [case for case in data["tests"] if case["status"] in ("FAIL", "ERROR")]
        if failures:
            lines += ["", "### Failing cases (first 50)", ""]
            lines += [
                f"- {safe_markdown(case['test_id'])}: {case['status']} / {case['diagnosis']}"
                for case in failures[:50]
            ]
        lines += ["", "Diagnoses are evidence labels, not proof of a provider-side model change."]
    else:
        impact = data["impact"]
        lines += [
            "Check failed." if code else "No behavioral regressions detected.",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
        ]
        for key in (
            "total_scenarios",
            "regressed",
            "improved",
            "unchanged",
            "changed_but_valid",
            "not_evaluated",
            "impact_radius_percentage",
            "latency_pct_change",
            "cost_pct_change",
        ):
            value = impact.get(key, 0)
            # Never render arbitrary CLI text/provider errors into Markdown.
            if type(value) not in (int, float):
                value = "unavailable"
            lines.append(f"| {key.replace('_', ' ').capitalize()} | {value} |")
        regressions = impact.get("scenarios", [])
        if isinstance(regressions, list):
            for case in regressions[:50]:
                if isinstance(case, dict) and case.get("classification") == "REGRESSED":
                    lines.append(
                        f"- {safe_markdown(case.get('scenario_id', 'unnamed'))}: REGRESSED"
                    )
    return "\n".join(lines) + "\n"


def execute(workdir: Path, mode: str, samples: int) -> tuple[dict, int]:
    if mode not in ("check", "monitor") or not 1 <= samples <= 20 or not workdir.is_dir():
        return error_report("invalid_input", 2), 2
    # Refuse privileged PR workflows, even if the repository happens to be private.
    if os.environ.get("GITHUB_EVENT_NAME") == "pull_request_target":
        return error_report("unsafe_event", 2), 2
    if os.environ.get("PROMPTDRIFT_INSTALL", "true") not in ("true", "false"):
        return error_report("invalid_input", 2), 2
    if os.environ.get("PROMPTDRIFT_INSTALL", "true") == "true":
        package = os.environ.get("PROMPTDRIFT_VERSION", "promptdrift-ci")
        if not package or package.startswith("-"):
            return error_report("invalid_package", 2), 2
        # Arguments are never interpreted as shell code or extra pip options.
        installed = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--", package],
            cwd=workdir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if installed.returncode:
            return error_report("installation_failed", 2), 2
    command = [
        "promptdrift",
        mode,
        "--config",
        os.environ.get("PROMPTDRIFT_CONFIG", "promptdrift.yaml"),
    ]
    if mode == "monitor":
        command += ["--samples", str(samples)]
    elif os.environ.get("PROMPTDRIFT_BASE_REF"):
        command += ["--base", os.environ["PROMPTDRIFT_BASE_REF"]]
    command += ["--json"]
    # Spool stdout privately. Neither raw stdout nor stderr is printed or uploaded on error.
    with tempfile.TemporaryFile() as output:
        completed = subprocess.run(
            command,
            cwd=workdir,
            stdout=output,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        code = completed.returncode
        if code < 0:
            code = 128 - code
        output.seek(0)
        raw = output.read(MAX_REPORT_BYTES + 1)
    try:
        if len(raw) > MAX_REPORT_BYTES:
            raise ValueError("oversized report")
        data = json.loads(raw, parse_float=finite_number, parse_constant=finite_number)
        data = validate_report(data, mode, code, samples)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        # Preserve the CLI's nonzero code; malformed *successful* output is an Action error.
        code = code or 2
        data = error_report("invalid_report", code)
    return data, code


def write_output(name: str, value: object) -> None:
    if os.environ.get("GITHUB_OUTPUT"):
        # Values here are controlled paths, hex digests or integers, not CLI/user strings.
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"{name}={value}\n")


def main() -> int:
    if "--enforce" in sys.argv:
        try:
            code = int(os.environ.get("PROMPTDRIFT_EXIT_CODE", ""))
            return code if 0 <= code <= 255 else 2
        except ValueError:
            return 2
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
    report_dir = Path(
        tempfile.mkdtemp(prefix="promptdrift-", dir=os.environ.get("RUNNER_TEMP"))
    ).resolve()
    mode = os.environ.get("PROMPTDRIFT_MODE", "check")
    config_scope = "invalid-config"
    try:
        workdir = (workspace / os.environ.get("PROMPTDRIFT_WORKING_DIRECTORY", ".")).resolve()
        config_path = (workdir / os.environ.get("PROMPTDRIFT_CONFIG", "promptdrift.yaml")).resolve()
        try:
            config_scope = os.path.relpath(config_path, workspace).replace("\\", "/")
        except ValueError:  # Absolute configuration on another Windows drive.
            config_scope = config_path.as_posix()
        samples = int(os.environ.get("PROMPTDRIFT_SAMPLES", "3")) if mode == "monitor" else 3
        data, code = execute(workdir, mode, samples)
    except (ValueError, OSError):
        code = 2
        data = error_report("action_error", code)
    try:
        data = redact(data)
        serialized = json.dumps(data, indent=2, allow_nan=False) + "\n"
        markdown = summary(data, mode, code)
    except (ValueError, TypeError, RecursionError):
        code = code or 2
        data = error_report("invalid_report", code)
        serialized = json.dumps(data, indent=2) + "\n"
        markdown = summary(data, mode, code)
    report_path = report_dir / "report.json"
    summary_path = report_dir / "summary.md"
    report_path.write_text(serialized, encoding="utf-8")
    summary_path.write_text(markdown, encoding="utf-8")
    scope = hashlib.sha256(
        f"{config_scope}\n{os.environ.get('PROMPTDRIFT_ISSUE_SCOPE', '')}".encode(errors="replace")
    ).hexdigest()
    for key, value in (
        ("result", report_path),
        ("summary", summary_path),
        ("exit_code", code),
        ("scope", scope),
    ):
        write_output(key, value)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(markdown)
    # Failure is intentionally deferred until after artifact/comment/issue publication.
    return 0


if __name__ == "__main__":
    sys.exit(main())
