"""Local LLM analysis provider (Ollama / vLLM / OpenAI-compatible).

This provider talks to a model runtime that the operator runs locally. It never
downloads a model, never requires a coding-agent subscription, and never falls
back to fabricating analysis without marking it as synthetic.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from app.config.settings import get_settings


class LocalLLMProvider:
    """OpenAI-compatible client for a locally hosted model runtime."""

    name = "local_llm"

    def __init__(self) -> None:
        """Load local runtime settings."""
        settings = get_settings()
        self.base_url = settings.local_llm_base_url
        self.model = settings.local_llm_model
        self.runtime = settings.local_llm_provider

    def analyze(self, prompt: str, schema: type, system: str | None = None) -> Any:
        """Run analysis against the local runtime."""
        if not (self.base_url and self.model):
            from app.providers.demo import DemoProvider

            return DemoProvider().analyze(prompt, schema, system)

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        extra: dict[str, Any] = {}
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            extra["response_format"] = {"type": "json_object"}

        try:
            from openai import OpenAI

            client = OpenAI(api_key="local", base_url=self.base_url)
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                **extra,
            )
            content = response.choices[0].message.content or "{}"
        except Exception as exc:  # noqa: BLE001
            from app.providers.demo import DemoProvider

            return DemoProvider()._synthetic_ai_fill(schema) if (
                isinstance(schema, type) and issubclass(schema, BaseModel)
            ) else {"synthetic": True, "note": f"local llm unavailable: {exc}"}

        try:
            data = json.loads(content)
        except Exception:
            from app.providers.demo import DemoProvider

            return DemoProvider()._synthetic_ai_fill(schema) if (
                isinstance(schema, type) and issubclass(schema, BaseModel)
            ) else {"synthetic": True, "note": "invalid json from local model"}

        if isinstance(schema, type) and issubclass(schema, BaseModel):
            try:
                return schema.model_validate(data)
            except Exception:
                from app.providers.demo import DemoProvider

                return DemoProvider()._synthetic_ai_fill(schema)
        return data
