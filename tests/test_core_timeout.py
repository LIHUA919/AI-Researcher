import asyncio
from types import SimpleNamespace

from research_agent.inno.core import MetaChain


def test_acompletion_falls_back_after_timeout(monkeypatch):
    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == "primary-model":
            raise TimeoutError("request timed out")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    monkeypatch.setattr("research_agent.inno.core.acompletion", fake_acompletion)
    monkeypatch.setenv("MODEL_FALLBACKS", "fallback-model")

    chain = MetaChain()
    response = asyncio.run(
        chain._acompletion_with_retry_and_fallback(
            {
                "model": "primary-model",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
                "base_url": "https://example.com/v1",
            }
        )
    )

    assert response.choices[0].message.content == "ok"
    assert calls[0] == "primary-model"
    assert "openai/fallback-model" in calls


def test_acompletion_normalizes_bare_fallback_model_names(monkeypatch):
    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == "openai/deepseek-ai/DeepSeek-V3.2":
            raise TimeoutError("request timed out")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    monkeypatch.setattr("research_agent.inno.core.acompletion", fake_acompletion)
    monkeypatch.setenv("MODEL_FALLBACKS", "deepseek-chat")

    chain = MetaChain()
    response = asyncio.run(
        chain._acompletion_with_retry_and_fallback(
            {
                "model": "openai/deepseek-ai/DeepSeek-V3.2",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
                "base_url": "https://example.com/v1",
            }
        )
    )

    assert response.choices[0].message.content == "ok"
    assert calls[0] == "openai/deepseek-ai/DeepSeek-V3.2"
    assert "openai/deepseek-chat" in calls
