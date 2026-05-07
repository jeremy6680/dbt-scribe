from __future__ import annotations

from types import SimpleNamespace

from dbt_scribe.generators.base_generator import LLMResponse
from dbt_scribe.generators.providers.anthropic_provider import AnthropicProvider
from dbt_scribe.generators.providers.google_provider import GoogleProvider
from dbt_scribe.generators.providers.openai_provider import OpenAIProvider


def test_anthropic_provider_normalizes_response(monkeypatch):
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(text='{"ok": true}')],
                usage=SimpleNamespace(input_tokens=12, output_tokens=7),
            )

    class FakeAnthropic:
        def __init__(self, *, api_key):
            self.api_key = api_key
            self.messages = FakeMessages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setattr("anthropic.Anthropic", FakeAnthropic)

    provider = AnthropicProvider(model="claude-test", temperature=0.2)
    response = provider.complete("system prompt", "user prompt")

    assert response == LLMResponse(
        content='{"ok": true}',
        input_tokens=12,
        output_tokens=7,
        provider="anthropic",
        model="claude-test",
    )
    assert calls == [
        {
            "model": "claude-test",
            "max_tokens": 4096,
            "temperature": 0.2,
            "system": "system prompt",
            "messages": [{"role": "user", "content": "user prompt"}],
        }
    ]


def test_openai_provider_normalizes_response(monkeypatch):
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
                usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7),
            )

    class FakeOpenAI:
        def __init__(self, *, api_key):
            self.api_key = api_key
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    provider = OpenAIProvider(model="gpt-test", temperature=0.2)
    response = provider.complete("system prompt", "user prompt")

    assert response == LLMResponse(
        content='{"ok": true}',
        input_tokens=12,
        output_tokens=7,
        provider="openai",
        model="gpt-test",
    )
    assert calls == [
        {
            "model": "gpt-test",
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "user prompt"},
            ],
        }
    ]


def test_google_provider_normalizes_response(monkeypatch):
    calls = []

    class FakeModels:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                text='{"ok": true}',
                usage_metadata=SimpleNamespace(
                    prompt_token_count=12,
                    candidates_token_count=7,
                ),
            )

    class FakeClient:
        def __init__(self, *, api_key):
            self.api_key = api_key
            self.models = FakeModels()

    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setattr("google.genai.Client", FakeClient)

    provider = GoogleProvider(model="gemini-test", temperature=0.2)
    response = provider.complete("system prompt", "user prompt")

    assert response == LLMResponse(
        content='{"ok": true}',
        input_tokens=12,
        output_tokens=7,
        provider="google",
        model="gemini-test",
    )
    assert calls[0]["model"] == "gemini-test"
    assert calls[0]["contents"] == "user prompt"
    assert calls[0]["config"].system_instruction == "system prompt"
    assert calls[0]["config"].temperature == 0.2
