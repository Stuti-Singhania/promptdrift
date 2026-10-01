# Contributing to PromptDrift

Thank you for your interest in improving PromptDrift! This guide covers everything you need to get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/tanveer-arch/promptdrift.git
cd promptdrift

# Install with development dependencies
pip install -e ".[dev]"

# Verify the setup (Node 22+ and Git are also needed for Action/Git fixtures)
python -m pytest -q
python -m ruff check src tests action
python -m ruff format --check src tests action
```

## Project Structure

```
src/promptdrift/
├── cli.py              # Typer CLI commands
├── config.py           # YAML config loader
├── templates.py        # Jinja2 prompt renderer
├── errors.py           # Exception hierarchy
├── engine/             # Test runner, baselines, regression
├── evaluators/         # Deterministic assertion evaluators
├── models/             # Pydantic data models
├── providers/          # LLM adapters (OpenAI, Ollama, Mock)
├── reports/            # Terminal, HTML, GitHub formatters
└── storage/            # SQLite local history

tests/
├── unit/               # Fast, isolated tests
├── integration/        # CLI end-to-end tests
├── fixtures/           # Shared test data
└── snapshots/          # Output snapshot tests
```

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/unit/test_evaluators.py

# Run tests matching a pattern
pytest -k "test_contains"

# Run with coverage
pytest --cov=promptdrift --cov-report=term-missing
```

## Code Style

PromptDrift uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Check lint and format
ruff check src tests action
ruff format --check src tests action

# Format only files you change
ruff format path/to/changed_file.py
```

**Style guidelines:**
- Line length: 100 characters
- Target Python: 3.11+
- Lint rules: `E`, `F`, `I` (imports), `UP` (pyupgrade)
- All models use `ConfigDict(extra="forbid")` — no silent field drops
- Provider errors never expose request bodies or credentials

## Making Changes

### 1. Pick an Issue or Feature

Check [open issues](https://github.com/tanveer-arch/promptdrift/issues) or create a new one describing what you want to work on.

### 2. Create a Branch

```bash
git checkout -b feat/your-feature-name
```

Use prefixes: `feat/`, `fix/`, `docs/`, `test/`, `refactor/`.

### 3. Write Tests First

PromptDrift is a testing tool — tests are not optional. For any behavioral change:
- Add unit tests in `tests/unit/`
- Add integration tests in `tests/integration/` for CLI changes
- Ensure edge cases are covered

### 4. Make Your Changes

Follow the existing patterns:
- Providers implement the `Provider` ABC
- All data flows through Pydantic models
- Errors use the `PromptDriftError` hierarchy
- Keep providers isolated from the engine

### 5. Verify

```bash
python -m pytest -q
python -m ruff check src tests action
python -m ruff format --check src tests action
python -m build
python -m twine check dist/*
```

Tests use a temporary working directory and home. Do not remove that isolation to make a test pass; use `Path(__file__)` for source fixtures and `tmp_path` for generated projects. Offline tests need no paid API credentials. Node publication tests skip locally if Node is missing, but CI requires it. No repository-wide type checker is currently configured; do not report a typecheck as passed.

Try `promptdrift demo` and an installed-wheel starter → baseline → monitor → history flow outside the checkout. A synthetic failure is evidence that the fixture works, not a real model benchmark. Changes to diagnosis must test confounding inputs, missing evidence and provider failure, not only the positive drift case.

### Release preparation

The package version is defined once in `src/promptdrift/__init__.py` and read by Hatch. Current 0.4.0 changes are unreleased. Build both wheel and sdist, inspect their contents, install the wheel in a clean environment, and verify `promptdrift version` and `demo`. A tag must match the package version. The release workflow verifies tests/static checks/build metadata before using the configured PyPI trusted publisher for **promptdrift-ci**; publisher/environment settings must be configured by a maintainer.

Do not tag/publish or enable paid schedules as a side effect of a contribution.

### 6. Submit a Pull Request

- Write a clear description of what changed and why
- Link related issues
- Ensure CI passes

## Architecture Guidelines

- **Providers are isolated.** A new provider is one file + a type registration. It should never import engine internals.
- **Assertions are pure functions.** Each evaluator takes an assertion and a response, returns a result. No side effects.
- **Compatibility must be explicit.** New fields should have defaults. Document/test migrations, and reject unsupported behavior rather than silently accepting misleading configuration.
- **Privacy boundaries are explicit.** Provider calls necessarily transmit rendered prompts. Monitor artifacts must exclude raw content; legacy JSON/HTML exports have different privacy boundaries. Test those boundaries rather than promising blanket anonymity.

## Reporting Bugs

Use the [bug report template](https://github.com/tanveer-arch/promptdrift/issues/new?template=bug_report.yml) and include:
- PromptDrift version (`promptdrift version`)
- Python version (`python --version`)
- OS and provider
- Steps to reproduce
- Expected vs actual behavior

## Focused contribution opportunities

See the [contribution candidates](docs/roadmap.md) for ten scoped, testable
starting points. Each gives a problem, scope, acceptance criteria, suggested
labels/difficulty and relevant files. They are proposals, not fabricated GitHub
issues or promised deliveries.

## Questions?

Open a [discussion](https://github.com/tanveer-arch/promptdrift/discussions) or reach out on the issue tracker.
