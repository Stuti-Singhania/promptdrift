"""Ollama generation adapter."""

from __future__ import annotations

import time

import httpx

from promptdrift.errors import ProviderError
from promptdrift.models.result import ModelResponse

from .base import Provider


class OllamaProvider(Provider):
    def __init__(self, config):
        self.config = config

    def complete(self, prompt: str, *, temperature: float, max_output_tokens: int) -> ModelResponse:
        start = time.perf_counter()
        try:
            response = httpx.post(
                (self.config.base_url or "http://localhost:11434").rstrip("/") + "/api/generate",
                json={
                    "model": self.config.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_output_tokens},
                },
                timeout=90,
            )
            response.raise_for_status()
            payload = response.json()
            output = payload["response"]
            if not isinstance(output, str):
                raise ValueError("Expected a text completion")
            return ModelResponse(
                output=output,
                input_tokens=payload.get("prompt_eval_count"),
                output_tokens=payload.get("eval_count"),
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                model=self.config.model,
                provider="ollama",
                resolved_model=payload.get("model"),
                estimated_cost_usd=0.0,
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ProviderError(
                f"Ollama request failed: {type(exc).__name__}. Is Ollama running?"
            ) from exc
