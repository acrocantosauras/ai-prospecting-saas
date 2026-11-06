"""OpenAI-backed AI analysis provider.

This is an optional production provider. It is only active when
AI_PROVIDER=openai and a valid OpenAI API key is configured.

All provider outputs are validated against Pydantic schemas before use.
"""

from typing import Any

from pydantic import BaseModel

from app.config import settings as app_settings
from app.providers.base import AIAnalysisProvider


class OpenAIProvider(AIAnalysisProvider):
    """Uses OpenAI chat completions with structured output when available."""

    def __init__(self) -> None:
        self.api_key = app_settings.openai_api_key
        self.model = app_settings.openai_model
        self.base_url = app_settings.openai_base_url

    def analyze(self, prompt: str, schema: type, system: str | None = None) -> Any:
        """Run an AI analysis task and return validated schema output.

        Falls back to a synthetic response if the API key is missing.
        """
        if not self.api_key:
            from app.providers.demo import DemoProvider
            return DemoProvider().analyze(prompt, schema, system)

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        extra: dict[str, Any] = {}
        if issubclass(schema, BaseModel):
            extra["response_format"] = {"type": "json_object"}

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url=self.base_url or None)
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                **extra,
            )
            content = response.choices[0].message.content or "{}"
        except Exception as exc:
            return self._synthetic_fallback(schema, prompt, exc)

        try:
            import json
            data = json.loads(content)
        except Exception:
            return self._synthetic_fallback(schema, prompt, "Invalid JSON from model")

        if issubclass(schema, BaseModel):
            try:
                return schema.model_validate(data)
            except Exception:
                return self._synthetic_fallback(schema, prompt, "Schema validation failed")

        return data

    def _synthetic_fallback(self, schema: type, prompt: str, reason: Exception | str) -> Any:
        from app.providers.demo import DemoProvider
        from pydantic import BaseModel
        if issubclass(schema, BaseModel):
            return DemoProvider()._synthetic_ai_fill(schema)
        return {"synthetic": True, "note": f"Fallback: {reason}"}
