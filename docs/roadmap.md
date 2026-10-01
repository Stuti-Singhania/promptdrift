# Contribution candidates

These are **not** pre-created GitHub issues or promised features. They are
maintainer-reviewed candidates for real issues when someone brings a use case
or is ready to work on one. Keep the product focused: PromptDrift observes
behavior changes under explicitly monitored inputs; it is not a generic prompt
evaluation platform.

When opening one, copy the problem, scope and acceptance criteria below into
the issue. Add the suggested labels only if they exist in the repository; do
not create activity for its own sake.

| Candidate | Suggested labels / difficulty | Starting points |
| --- | --- | --- |
| Promote a reviewed observation | `enhancement`, `reliability` / advanced | `engine/accept.py`, `engine/monitor.py`, `storage/history.py` |
| Sampled reference distributions | `enhancement`, `statistics` / advanced | `models/baseline.py`, `engine/baseline.py`, `engine/monitor.py` |
| Request-envelope provenance | `enhancement`, `privacy` / advanced | `models/provenance.py`, `engine/provenance.py` |
| Bounded provider resilience | `enhancement`, `providers` / advanced | `providers/`, `models/config.py`, `engine/monitor.py` |
| Provider error taxonomy | `good first issue`, `providers` / intermediate | `providers/openai.py`, `providers/ollama.py`, `errors.py` |
| OpenAI-compatible fixture matrix | `good first issue`, `testing` / intermediate | `tests/unit/test_openai_integration.py`, `providers/openai.py` |
| Ollama provenance fixture coverage | `good first issue`, `testing` / intermediate | `tests/unit/test_providers.py`, `providers/ollama.py` |
| History lifecycle hardening | `good first issue`, `reliability` / intermediate | `storage/history.py`, `tests/unit/test_monitor_safety.py` |
| Action report-contract checks | `good first issue`, `github-actions` / intermediate | `action/run.py`, `tests/unit/test_action_runner.py` |
| Cross-platform CLI smoke coverage | `good first issue`, `cli`, `testing` / beginner | `cli.py`, `tests/integration/test_cli.py`, `.github/workflows/ci.yml` |

## 1. Promote exactly the observation that was reviewed

**Problem:** `baseline` and `accept` make fresh provider calls, so a stochastic
response can differ from the run a reviewer inspected.

**Scope:** Add a versioned, privacy-minimized observation snapshot and an
`accept --run-id` path that promotes compatible reviewed cases without calls.

**Acceptance criteria:** reject stale config/provenance, missing or corrupt
snapshots and partial runs; require an explicit failure override; preserve
atomic archive/update behavior; test no raw prompts/responses are stored.

## 2. Sampled healthy reference distributions

**Problem:** one accepted response and a few current probes are a useful
heuristic, not calibrated evidence of a distribution shift.

**Scope:** make a baseline sample budget explicit and compare comparable
historical/current contract pass rates.

**Acceptance criteria:** deterministic simulations for stationary, noisy and
shifted providers; report uncertainty/minimum samples; do not make unmeasured
accuracy or false-positive claims.

## 3. Request-envelope provenance for real applications

**Problem:** current hashes cover rendered text, but cannot attest to messages,
tools, retrieval state, application code or evaluator dependencies.

**Scope:** define a small, versioned optional request envelope; do not build an
agent framework.

**Acceptance criteria:** deterministic hashes for supplied tool/retrieval
metadata; explicit uncaptured state; credential-safe serialization;
compatibility migration; examples for comparable and confounded runs.

## 4. Bounded provider resilience and request budgets

**Problem:** fixed sequential calls are predictable but limit larger schedules;
rate limits currently share the broad provider-error path.

**Scope:** add bounded configuration for timeout, concurrency, retries and a
maximum request budget.

**Acceptance criteria:** classify auth, rate-limit, transport and malformed
responses without payload leaks; retry only safe transient failures; reject a
run before calls when its request budget is exceeded; use deterministic clocks
and HTTP fixtures. Never estimate unknown cost as zero.

## 5. Provider error taxonomy

**Problem:** users need an actionable infrastructure diagnosis without exposing
provider payloads or credentials.

**Scope:** normalize existing OpenAI/Ollama exceptions into documented,
non-secret categories; this is not a new provider integration.

**Acceptance criteria:** representative HTTP fixtures for auth, rate-limit,
timeout and malformed success payloads; stable CLI/monitor exit behavior; tests
that reports omit response bodies, authorization headers and keys.

## 6. OpenAI-compatible fixture matrix

**Problem:** `base_url` compatibility is deliberately narrow, and regressions
are easy to introduce while supporting standard response variants.

**Scope:** expand only offline fixtures for documented, supported text-response
variants.

**Acceptance criteria:** cover missing optional usage/fingerprint/model fields,
valid content forms and invalid responses; document any intentionally rejected
shape; no live endpoint or paid credential in tests.

## 7. Ollama provenance fixture coverage

**Problem:** model/provenance evidence is only as trustworthy as adapter
normalization, particularly when optional metadata is missing.

**Scope:** add fixture-driven coverage for supported Ollama completion and
metadata shapes.

**Acceptance criteria:** verify stable provenance when metadata is absent,
supporting-signal reporting when it changes, safe rejection of malformed values
and no raw payload in monitor history.

## 8. Monitoring-history lifecycle hardening

**Problem:** local history is bounded, but schema evolution, locked databases
and retention behavior need sharper recovery guidance and test coverage.

**Scope:** improve only the project-local privacy-minimized history store.

**Acceptance criteria:** migration or explicit incompatible-schema error;
deterministic retention tests; clear recovery message for locked/corrupt DBs;
read paths remain read-only and never call providers.

## 9. Action report-contract checks

**Problem:** the Action deliberately projects a small public report schema;
new CLI fields must not accidentally leak raw data or change notification
semantics.

**Scope:** strengthen the offline Action/CLI boundary tests and document schema
compatibility expectations.

**Acceptance criteria:** fixture tests for unknown fields, future schema
versions and nested/raw-looking values; preserve original CLI exit code after
artifact creation; verify issue/comment publication uses sanitized data only.

## 10. Cross-platform CLI smoke coverage

**Problem:** starter workflows can fail on Windows-specific path, temporary
directory or terminal-encoding behavior even when unit tests pass elsewhere.

**Scope:** extend the existing offline CLI smoke tests and CI matrix; do not add
external providers.

**Acceptance criteria:** run `init --directory` for a missing path, baseline,
monitor and history in an isolated home; cover a non-UTF console stream; ensure
temporary files do not reach the real home or checkout; document platform
requirements when a limitation is unavoidable.

## Deliberately not prioritized

A hosted dashboard, arbitrary evaluator marketplace, paid service, broad
provider catalog, invented benchmarks, automatic baseline approval, automatic
rollback and synthetic repository activity. GitHub issues are the only alert
integration currently implemented; Slack, webhooks and email are not.
