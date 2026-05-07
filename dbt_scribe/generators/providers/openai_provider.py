from __future__ import annotations

import os

from dbt_scribe.generators.base_generator import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    def __init__(self, *, model: str, temperature: float = 0.2) -> None:
        super().__init__(model=model, temperature=temperature)
        import openai
        self._client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def _complete(self, system: str, user: str) -> LLMResponse:
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        choice = resp.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
            provider="openai",
            model=self.model,
        )
