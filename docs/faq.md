# FAQ

## General

### What is PromptDrift?

PromptDrift is a Python CLI and GitHub Action for behavioral drift checks, including fresh probes when your prompts have not changed. Define contracts, review a baseline and monitor it over time. It also supports PR prompt-regression checks. Diagnosis labels are evidence, not proof of a vendor update.

### How is PromptDrift different from a regular diff?

A `git diff` shows you what changed in the prompt **text**. PromptDrift tells you whether the AI **behavior** changed in a way that matters. Rewording a prompt is fine — silently dropping a required field from the response is not.

### Does PromptDrift send telemetry?

No. PromptDrift has no analytics, tracking, hosted service, or phone-home behavior. Your prompt content goes only to the LLM provider you configure.

### Is PromptDrift a hosted service?

No. PromptDrift runs entirely locally or in your own CI pipeline. There are no accounts, dashboards, or remote databases.

## Behavior

### Does an output change fail my build?

No. A failure requires a **violated assertion** (e.g., required text missing, invalid JSON, schema mismatch). If the output changed but all assertions still pass, PromptDrift adds a diagnostic note but keeps the status as PASS.

### Can I get warnings without blocking CI?

Yes. Set `severity: warn` on any assertion:

```yaml
- type: not_contains
  value: "guaranteed"
  severity: warn
```

Warnings appear in reports but don't set a non-zero exit code.

### What happens when I add a new test that has no baseline?

The test runs normally against assertions. If it passes, the status is set to WARN with a note saying "Test has no baseline." Run `promptdrift baseline --force` to update the baseline.

### Can I use PromptDrift without a baseline?

For `test` and `check`, yes: contracts can run without a baseline. **`monitor` requires a valid accepted baseline**, because its purpose is historical comparison. Empty suites are errors, not passing runs.

## Privacy and Security

### Where does prompt data go?

Only to the LLM provider you configure. The `mock` provider is entirely local — no network calls at all.

### Are API keys stored in config?

No. API keys are read exclusively from environment variables. The config file only stores the **name** of the variable (e.g., `api_key_env: OPENAI_API_KEY`), never the value.

### What's in the baseline file?

Output hashes, contract results, metrics and per-case provenance hashes. Raw outputs/prompts are not stored. Hashes are not encryption; review IDs, model names and other metadata before committing publicly.

### Is local history safe?

Legacy history at `~/.promptdrift/promptdrift.db` suppresses prompts, outputs and evaluation payloads by default; `baseline.store_raw_output: true` opts into retaining them. Monitoring history is separate, project-local and always privacy-minimized. Neither database is encrypted. See [monitoring](monitoring.md).

## CI and GitHub

### Can I use PromptDrift with fork PRs?

Yes, but with care. Use the `pull_request` event (not `pull_request_target`) and either:
- Use the `mock` provider (no API key needed)
- Skip tests that require a real provider

Never expose API secrets to code from a fork. See [GitHub Action docs](github-action.md) for details.

### How do I pin the PromptDrift version in CI?

Pin an existing reviewed Action commit/tag and a matching published **`promptdrift-ci`** version. Do not use an invented `@v1` release or install a different package named `promptdrift`. New monitoring is currently unreleased: use the source-install workflow in [the Action guide](github-action.md).

### Can I run multiple config files?

Not in a single invocation. Run `promptdrift test -c config1.yaml` and `promptdrift test -c config2.yaml` separately, or use multiple workflow jobs.

### Does monitoring prove the model changed?

No. At least two repeated behavioral failures under matching recorded inputs can yield `observed_model_drift`. A single accepted baseline, randomness, routing, hidden system state, unobserved application context and dependency changes all limit attribution. There is no confidence percentage or statistical-significance claim. See [the rules](monitoring.md).

### Does PromptDrift support semantic judges?

No usable semantic or LLM-judge suite evaluator is implemented. Nonempty `evaluators` and `evaluation.semantic.enabled: true` are rejected. Do not infer support from legacy scaffolding or old changelog wording.

## Troubleshooting

### `promptdrift doctor` shows a failing check

Run `promptdrift doctor --verbose` for a detailed traceback. Common causes:
- Missing prompt file referenced in config
- API key env var not set
- Corrupted baseline JSON

### Tests pass locally but fail in CI

Run `promptdrift doctor` in CI as a diagnostic step. Check:
- Is the API key secret set correctly?
- Are prompt files checked into the repository?
- Is the Python version compatible (3.11+)?
