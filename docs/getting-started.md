# Getting started

Use Python 3.11+ and preferably a virtual environment. The published package is named **`promptdrift-ci`**, while the CLI/import is `promptdrift`.

```bash
python -m pip install promptdrift-ci
```

The monitoring features documented here are **unreleased 0.4 development features**. Install the checkout to try them:

```bash
git clone https://github.com/tanveer-arch/promptdrift.git
cd promptdrift
python -m pip install .
promptdrift demo
```

The demo uses a temporary loopback HTTP fixture: accepted response first, deliberately broken response next, same request/configuration. It demonstrates the actual adapter/diagnosis flow without external services or API keys, not a real model incident.

## A working project in minutes

```bash
promptdrift init --directory my-prompts
cd my-prompts
promptdrift doctor
promptdrift test
promptdrift baseline
promptdrift monitor --samples 3
promptdrift history --json
```

`init` creates `promptdrift.yaml` and `prompts/example.txt`; it reports existing prompt files but does not automatically author coverage for them. Its mock provider echoes the rendered prompt, so this sequence should pass without an API key.

Baseline paths and prompt paths are relative to the config. The monitoring database stays beside that config under `.promptdrift/`, even when commands run from another directory.

## Real monitoring

1. Choose a few stable, representative cases, excluding private production data.
2. Edit the provider and contracts; see [providers](providers.md) and the [README support example](../README.md).
3. Set the provider API key through your environment/secret manager, never in YAML.
4. Run `promptdrift test` and review the behavior locally.
5. Run `promptdrift baseline --force` deliberately, then inspect and commit the new reference. The command makes fresh calls; it does not accept the exact prior test run.
6. Schedule `promptdrift monitor --samples 3`, budgeting three calls per case per run.

Switching from mock to a real model changes the provider fingerprint. Do not interpret that as a silent upstream drift incident; establish a new reviewed baseline.

## Reading a failure

`observed_model_drift` means repeated behavioral contract failures under matching **recorded inputs**. It does not prove changed weights or unchanged application code. Mixed successes/failures are `stochastic_behavior`; provider errors have a separate infrastructure exit code. A valid wording change alone does not fail CI.

Keep the old baseline during investigation. Use `history`, provider status information, and repeated manual checks before deciding to accept new behavior. See [monitoring rules](monitoring.md).

## CI and further reading

- [GitHub Action](github-action.md): PR checks, scheduled monitoring and optional deduplicated issues.
- [Configuration](configuration.md): supported options and deliberately rejected features.
- [Baselines](baselines.md): acceptance, migration and archives.
- [Contributing](../CONTRIBUTING.md): offline tests, development setup and release checks.
