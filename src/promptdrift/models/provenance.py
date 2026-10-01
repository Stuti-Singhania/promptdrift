"""Per-case evidence. Hashes are identifiers, not anonymization guarantees."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_hash: str
    configuration_hash: str
    contract_hash: str
    provider_hash: str
    engine_version: str
    # Optional provider-reported metadata is only a signal, never proof of drift.
    response_model_hash: str | None = None
    system_fingerprint_hash: str | None = None
