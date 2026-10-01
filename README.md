# PromptDrift

[![CI](https://github.com/tanveer-arch/promptdrift/actions/workflows/ci.yml/badge.svg)](https://github.com/tanveer-arch/promptdrift/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/promptdrift-ci?color=blue)](https://pypi.org/project/promptdrift-ci/)
[![Python](https://img.shields.io/pypi/pyversions/promptdrift-ci)](https://pypi.org/project/promptdrift-ci/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Your prompts stayed the same. Did your model's behavior?**

PromptDrift is a Python CLI and GitHub Action for fresh behavioral checks against a reviewed, Git-tracked baseline. Monitor an unchanged prompt suite on a schedule, distinguish contract regressions from harmless wording changes, and inspect evidence before blaming a model update.

It also checks intentional prompt changes in pull requests and can turn captured interactions into candidate tests. It is **not** a general-purpose evaluation platform, hosted observability service, or proof that a provider changed its model weights.

> **Development status:** monitoring, history and the synthetic demo below are part of **0.4.0 (unreleased)**. Install this checkout to try them. `pip install promptdrift-ci` installs the published release, which may not contain these commands. The project remains pre-1.0.

## Try an incident without an API key

Python 3.11+ required. Prefer a virtual environment.

```bash
git clone https://github.com/tanveer-arch/promptdrift.git
cd promptdrift
python -m pip install .
promptdrift demo
```

The demo starts a temporary **loopback HTTP fixture**, saves a passing baseline, then changes only the fixture's response. The real OpenAI-compatible adapter and monitoring engine report `observed_model_drift` after three contract failures. **This is a synthetic demonstration, not a real model incident or benchmark.** No external API, paid key, or persistent project files are needed.

## Monitor your own application contract

Start in a separate project directory:

```bash
promptdrift init --directory my-monitor
cd my-monitor
promptdrift test
promptdrift baseline
promptdrift monitor --samples 3
promptdrift history
```

The starter uses a deterministic mock. To monitor a real endpoint, change the provider, author a few representative cases, and create a **new reviewed baseline** for that provider:

```yaml
version: 2
provider:
  type: openai
  model: gpt-4.1-mini
  api_key_env: OPENAI_API_KEY
  # base_url: https://your-openai-compatible-endpoint.example/v1

defaults:
  temperature: 0
  max_output_tokens: 300

tests:
  - id: refund-policy
    prompt: prompts/support.txt
    variables:
      question: Can I return my order after ten days?
    assertions:
      - type: contains
        value: 30 days
      - type: not_contains
        value: guaranteed
```

`prompts/support.txt`:

```text
You are a support assistant. Refunds are available within 30 days.
Answer concisely using that policy. Question: {{ question }}
```

Set `OPENAI_API_KEY` using your environment or CI secret store, then run:

```bash
promptdrift doctor
promptdrift baseline --force  # Review behavior; deliberately replaces a previous baseline.
promptdrift monitor --samples 3 --json
```

Commit the reviewed baseline with your contracts. Schedule **monitor**, not a changed-files-only PR job, to detect changes when your repository is idle. Each run makes **samples × active cases** fresh provider calls; no output cache or automatic retries. Provider charges still apply.

## What the diagnosis means

| Observation | Diagnosis | CI result |
| --- | --- | --- |
| Same monitored inputs, all repeated probes now fail behavioral contracts | `observed_model_drift` | Fail |
| Some repeated probes pass and others fail behavioral contracts | `stochastic_behavior` | Fail if any failure |
| Rendered prompt, generation settings, provider or contracts changed | Explicit `*_changed` diagnosis with all changed fingerprints listed | Determined by contract results |
| Output wording changed, contracts still pass | `output_changed` | Pass |
| Timeout, HTTP error, malformed completion | `provider_error` | Infrastructure failure |
| Old baseline lacks provenance, previous baseline was unhealthy, or evidence is insufficient | `insufficient_evidence` | Warning unless contracts fail |

Fingerprints are **per case**, so selective acceptance retains the evidence belonging to each accepted case. Provider-reported model IDs/fingerprints are supporting signals only. One accepted sample and a handful of probes are not a statistically calibrated detector. Read the [diagnosis rules and limits](docs/monitoring.md) before using alerts operationally.

## CI and alerts

The [composite GitHub Action](action/action.yml) supports:

- existing Git-aware `check` mode and full-suite `monitor` mode;
- machine-readable artifacts and step summaries retained before enforcing the CLI result;
- opt-in same-repository PR comments;
- opt-in deduplicated monitoring issues for scheduled/manual jobs;
- explicit working-directory, package version and sampling settings.

See the [Action guide](docs/github-action.md) and [scheduled workflow example](.github/workflows/monitor-example.yml). No paid scheduled job is enabled in this repository. Pin a reviewed Action revision and matching package version when deploying. Never expose provider keys to untrusted PR code.

## Commands

| Workflow | Commands |
| --- | --- |
| First use | `init`, `doctor`, `demo` |
| Unchanged-input monitoring | **`monitor`**, **`history`** |
| PR regression checks | `check --base origin/main`, `test`, `diff` |
| Reviewed references | `baseline`, `accept --scenario ID`, `accept --changed`, `baselines` |
| Local evidence | `report` (HTML; contains raw results) |
| Capture to coverage | `capture`, `learn`, `scenarios`, `suggest`, `promote` |
| Maintenance | `purge` (legacy capture/run store), `version` |

`baseline`/initial `accept` refuse failed contracts without `--accept-regressions`. `--force` only authorizes overwriting, not silently accepting failures. Monitoring never updates your baseline.

## Providers and evaluators

**Providers:** OpenAI Chat Completions (including compatible `base_url` endpoints), Ollama, and deterministic mock. Compatible servers must implement the supported text-response API; not every model accepts `temperature`/`max_tokens`.

**Contracts:** `exact_match`, `contains`, `not_contains`, `regex`, `not_regex`, `json_valid`, `json_schema`, `min_length`, `max_length`, `max_tokens`, `latency_ms`, `cost_usd`. JSON schemas resolve local references only. Unknown token/cost usage cannot satisfy a configured limit. `output.format: json` enforces JSON validity.

Semantic embeddings and LLM judges are **not implemented as usable suite evaluators**. Unsupported settings are rejected, not presented as working capabilities.

## Privacy boundaries

- No telemetry or hosted account. Fresh probes go to your configured provider.
- Monitoring JSON/history omit raw prompts, responses, contract values, and provider exception bodies.
- Baselines store hashes, metrics, IDs and provenance, **not encryption**. Low-entropy content can be guessed; review IDs and metadata before publishing.
- Legacy `test/check/diff --json` and HTML reports can contain raw data. Their local SQLite history suppresses prompts, outputs and evaluation payloads by default.
- Capture is separate and requires deliberate privacy configuration. Read [SECURITY.md](SECURITY.md).

## Documentation and contributing

[Getting started](docs/getting-started.md) · [Monitoring](docs/monitoring.md) · [Configuration](docs/configuration.md) · [Baselines](docs/baselines.md) · [Providers](docs/providers.md) · [Assertions](docs/assertions.md) · [Architecture](docs/architecture.md)

[Contributing](CONTRIBUTING.md) explains offline tests and module boundaries. The [source-linked ecosystem comparison](docs/competitive-landscape.md) documents overlap rather than claiming invented uniqueness. [Next engineering priorities](docs/roadmap.md) describe concrete, testable work—not promised features.

Licensed under [MIT](LICENSE).
