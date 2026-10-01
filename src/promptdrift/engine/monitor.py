"""Repeated full-suite probes and conservative, evidence-based drift triage.

This observes behavior under fingerprinted inputs. It cannot prove a vendor
changed model weights, distinguish every source of randomness, or attest that
an application's code/retrieval/environment remained unchanged.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from promptdrift.engine.baseline import load_baseline
from promptdrift.engine.provenance import fingerprint, with_response
from promptdrift.engine.runner import evaluate_response, evaluation_status
from promptdrift.engine.suite import resolve_suite
from promptdrift.errors import ConfigError, ProviderError
from promptdrift.models import BaselineTest, Config, TestCase
from promptdrift.models.monitor import Diagnosis, MonitorCase, MonitorReport
from promptdrift.models.provenance import Provenance
from promptdrift.providers import create_provider
from promptdrift.templates import render_prompt

OPERATIONAL_ASSERTIONS = {"latency_ms", "cost_usd", "max_tokens"}


def _diagnose(
    old: BaselineTest | None,
    current: Provenance,
    *,
    samples: int,
    failures: int,
    behavioral_failures: int,
    errors: int,
    changes: int,
    warnings: int,
    response_signals: set[str],
) -> tuple[Diagnosis, str, list[str]]:
    evidence = [
        f"{samples - errors}/{samples} probes completed; {failures} failed contracts; {changes} changed outputs."
    ]
    evidence.extend(sorted(response_signals))
    changed_fields = []
    if old and old.provenance:
        for field, label in (
            ("input_hash", "prompt_changed"),
            ("configuration_hash", "configuration_changed"),
            ("provider_hash", "provider_changed"),
            ("contract_hash", "contract_changed"),
        ):
            if getattr(old.provenance, field) != getattr(current, field):
                changed_fields.append(label)
                evidence.append(f"{field} differs from the accepted baseline.")
    if errors:
        return (
            "provider_error",
            "Provider probes failed; do not interpret availability or malformed responses as model drift.",
            evidence,
        )
    if old is None:
        return "new_test", "No accepted baseline exists for this case.", evidence
    if changed_fields:
        return (
            changed_fields[0],
            "Monitored inputs/settings changed; model-only attribution is not justified. Review all evidence.",
            evidence,
        )
    if old.provenance is None:
        return (
            "insufficient_evidence",
            "Legacy baseline has no per-case provenance. Review and recreate it before attributing drift.",
            evidence,
        )
    if old.provenance.engine_version != current.engine_version:
        return (
            "insufficient_evidence",
            "PromptDrift version changed; review evaluator compatibility before attributing drift.",
            evidence,
        )
    if old.status != "PASS" or not all(old.assertions.values()):
        return (
            "insufficient_evidence",
            "The accepted case was not healthy; a new regression cannot be established.",
            evidence,
        )
    evidence.append(
        "Rendered input, generation settings, configured provider, contracts and PromptDrift version match the baseline."
    )
    if 0 < behavioral_failures < samples:
        return (
            "stochastic_behavior",
            "Repeated probes disagree on behavioral contracts; investigate variability, not a confirmed model update.",
            evidence,
        )
    if behavioral_failures == samples and samples >= 2:
        return (
            "observed_model_drift",
            "Repeated behavioral failures under unchanged monitored inputs. This is evidence of drift, not proof of a vendor model update.",
            evidence,
        )
    if failures or warnings:
        return (
            "insufficient_evidence",
            "Contract or operational limits failed; evidence does not establish repeated behavioral drift.",
            evidence,
        )
    if changes:
        return (
            "output_changed",
            "Output changed while contracts still pass; text differences alone are not regressions.",
            evidence,
        )
    return "stable", "All probes passed and output hashes match the baseline.", evidence


def monitor_suite(config: Config, config_path: Path, *, samples: int = 3) -> MonitorReport:
    if not 1 <= samples <= 20:
        raise ConfigError("samples must be between 1 and 20")
    # Preflight the entire suite before spending any provider calls.
    baseline_path = config.resolve_path(config_path, config.baseline.path)
    baseline = load_baseline(baseline_path)
    active, _ = resolve_suite(config, config_path)
    prepared: list[tuple[TestCase, str, Provenance]] = []
    for test in active.tests:
        prompt = render_prompt(active.resolve_path(config_path, test.prompt), test.variables)
        prepared.append((test, prompt, fingerprint(active, test, prompt)))
    provider = create_provider(active.provider)
    results = []
    for test, prompt, provenance in prepared:
        old = baseline.tests.get(test.id)
        failures = behavioral_failures = errors = changes = warnings = 0
        signals: set[str] = set()
        for _ in range(samples):
            try:
                response = provider.complete(
                    prompt,
                    temperature=active.defaults.temperature,
                    max_output_tokens=active.defaults.max_output_tokens,
                )
            except ProviderError:
                errors += 1
                continue
            evaluations = evaluate_response(test, response)
            status = evaluation_status(evaluations)
            failures += status == "FAIL"
            warnings += status == "WARN"
            behavioral_failures += any(
                not result.passed
                and result.severity == "fail"
                and assertion.type not in OPERATIONAL_ASSERTIONS
                for assertion, result in zip(test.assertions, evaluations, strict=False)
            ) or (test.output.format == "json" and not evaluations[len(test.assertions)].passed)
            if old:
                changes += hashlib.sha256(response.output.encode()).hexdigest() != old.output_hash
                observed = with_response(provenance, response)
                if old.provenance:
                    for field in ("response_model_hash", "system_fingerprint_hash"):
                        before, after = getattr(old.provenance, field), getattr(observed, field)
                        if before and after and before != after:
                            signals.add(
                                f"Provider-reported {field} changed (supporting signal only)."
                            )
                        elif bool(before) != bool(after):
                            signals.add(
                                f"Provider-reported {field} is unavailable on one side; no equality claim is possible."
                            )
        diagnosis, summary, evidence = _diagnose(
            old,
            provenance,
            samples=samples,
            failures=failures,
            behavioral_failures=behavioral_failures,
            errors=errors,
            changes=changes,
            warnings=warnings,
            response_signals=signals,
        )
        status = (
            "ERROR"
            if errors
            else "FAIL"
            if failures
            else "WARN"
            if warnings
            or diagnosis
            in {
                "new_test",
                "insufficient_evidence",
                "prompt_changed",
                "configuration_changed",
                "contract_changed",
                "provider_changed",
            }
            else "PASS"
        )
        results.append(
            MonitorCase(
                test_id=test.id,
                status=status,
                diagnosis=diagnosis,
                summary=summary,
                samples=samples,
                failures=failures,
                provider_errors=errors,
                output_changes=changes,
                evidence=evidence,
            )
        )
    for missing in sorted(set(baseline.tests) - {test.id for test in active.tests}):
        results.append(
            MonitorCase(
                test_id=missing,
                status="WARN",
                diagnosis="insufficient_evidence",
                samples=0,
                summary="Accepted case is absent from the active suite; monitoring coverage was removed.",
            )
        )
    return MonitorReport(
        provider=active.provider.type,
        model=active.provider.model,
        samples=samples,
        baseline_path=str(baseline_path),
        tests=results,
    )
