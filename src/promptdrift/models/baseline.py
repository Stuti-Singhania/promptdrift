"""Git-friendly canonical baseline models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .provenance import Provenance


class BaselineTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_hash: str
    provenance: Provenance | None = None
    status: str
    assertions: dict[str, bool]
    metrics: dict[str, float | int | None]
    evaluator_scores: dict[str, float | None] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Baseline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1, 2, 3] = 3
    promptdrift_version: str
    generated_at: datetime
    provider: dict[str, str]
    prompt_revision: str | None = None
    git_sha: str | None = None
    prompt_hash: str | None = None
    tests: dict[str, BaselineTest]
