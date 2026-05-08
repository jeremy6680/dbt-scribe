from __future__ import annotations

import abc
import time
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    provider: str
    model: str


class LLMProvider(abc.ABC):
    def __init__(self, *, model: str, temperature: float = 0.2) -> None:
        self.model = model
        self.temperature = temperature

    _NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404}

    def complete(self, system: str, user: str) -> LLMResponse:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                return self._complete(system, user)
            except Exception as exc:
                if getattr(exc, "status_code", None) in self._NON_RETRYABLE_STATUS_CODES:
                    raise
                last_exc = exc
                if attempt < 2:
                    time.sleep(2**attempt)
        raise RuntimeError(
            f"LLM call failed after 3 attempts: {last_exc}"
        ) from last_exc

    @abc.abstractmethod
    def _complete(self, system: str, user: str) -> LLMResponse:
        """Send a completion request and return a normalised LLMResponse."""
