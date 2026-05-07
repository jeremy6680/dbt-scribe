from __future__ import annotations

import os

from dbt_scribe.generators.base_generator import LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    def __init__(self, *, model: str, temperature: float = 0.2) -> None:
        super().__init__(model=model, temperature=temperature)
        import anthropic
        self._client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    def _complete(self, system: str, user: str) -> LLMResponse:
        import anthropic
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return LLMResponse(
            content=msg.content[0].text,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            provider="anthropic",
            model=self.model,
        )
