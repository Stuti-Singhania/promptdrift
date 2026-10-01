"""File-based scenario store for .promptdrift/scenarios.json.

Production traffic may update candidate statistics (sample_count, last_seen)
but must NEVER modify promoted scenarios, their assertions, or status.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from promptdrift.errors import ConfigError
from promptdrift.models.capture import Scenario, ScenarioLibrary


def load_scenarios(
    path: Path = Path(".promptdrift/scenarios.json"), *, strict: bool = False
) -> ScenarioLibrary:
    if not path.is_file():
        return ScenarioLibrary(version=1, scenarios=[])
    try:
        content = path.read_text(encoding="utf-8")
        return ScenarioLibrary.model_validate_json(content)
    except (OSError, ValueError, ValidationError) as exc:
        if strict:
            raise ConfigError(
                "Scenario library is invalid or unreadable; restore it before evaluating coverage."
            ) from exc
        return ScenarioLibrary(version=1, scenarios=[])


def save_scenarios(
    library: ScenarioLibrary, path: Path = Path(".promptdrift/scenarios.json")
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = library.model_dump_json(indent=2) + "\n"
    path.write_text(content, encoding="utf-8")


def add_or_update_scenarios(
    new_scenarios: list[Scenario], path: Path = Path(".promptdrift/scenarios.json")
) -> ScenarioLibrary:
    """Merge new discovery results into the scenario library.

    Rules:
    - Promoted scenarios are NEVER modified (assertions, input, status are frozen).
    - Candidate scenarios with matching fingerprint get sample_count/last_seen updated.
    - New fingerprints create new candidate entries.
    - Scenarios without fingerprints fall back to ID matching (v0.2 compat).
    """
    lib = load_scenarios(path)
    existing_by_id = {s.id: s for s in lib.scenarios}
    existing_by_fp: dict[str, Scenario] = {}
    for s in lib.scenarios:
        if s.fingerprint:
            existing_by_fp[s.fingerprint] = s

    for new in new_scenarios:
        # Try fingerprint match first
        matched = existing_by_fp.get(new.fingerprint) if new.fingerprint else None

        # Fall back to ID match
        if matched is None:
            matched = existing_by_id.get(new.id)

        if matched is not None:
            if matched.status == "promoted":
                # NEVER modify promoted scenarios from production evidence
                continue
            # Update candidate metadata only
            matched.sample_count = max(matched.sample_count, new.sample_count)
            if new.last_seen:
                if matched.last_seen is None or new.last_seen > matched.last_seen:
                    matched.last_seen = new.last_seen
            if new.first_seen:
                if matched.first_seen is None or new.first_seen < matched.first_seen:
                    matched.first_seen = new.first_seen
            if new.fingerprint and not matched.fingerprint:
                matched.fingerprint = new.fingerprint
        else:
            # New scenario — add as candidate
            existing_by_id[new.id] = new
            if new.fingerprint:
                existing_by_fp[new.fingerprint] = new

    lib.scenarios = list(existing_by_id.values())
    save_scenarios(lib, path)
    return lib
