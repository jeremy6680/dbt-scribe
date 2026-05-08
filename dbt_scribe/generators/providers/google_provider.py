from __future__ import annotations

import os

from dbt_scribe.generators.base_generator import LLMProvider, LLMResponse


class GoogleProvider(LLMProvider):
    def __init__(self, *, model: str, temperature: float = 0.2) -> None:
        super().__init__(model=model, temperature=temperature)
        from google import genai
        self._client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

    def _complete(self, system: str, user: str) -> LLMResponse:
        from google.genai import types
        resp = self._client.models.generate_content(
            model=self.model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=self.temperature,
            ),
        )
        usage = resp.usage_metadata
        return LLMResponse(
            content=resp.text or "",
            input_tokens=usage.prompt_token_count or 0 if usage else 0,
            output_tokens=usage.candidates_token_count or 0 if usage else 0,
            provider="google",
            model=self.model,
        )
