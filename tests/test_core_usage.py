import asyncio
from types import SimpleNamespace

from litellm.types.utils import Message

from research_agent.inno import Agent
from research_agent.inno.core import MetaChain, accumulate_llm_usage


def _completion(*, prompt_tokens=11, completion_tokens=7, total_tokens=18):
    message = Message(role="assistant", content="done")
    return SimpleNamespace(
        model="openai/test-model",
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
        choices=[SimpleNamespace(message=message)],
    )


def test_accumulate_llm_usage_groups_calls_by_model():
    context = {}

    accumulate_llm_usage(context, _completion(), requested_model="openai/requested")
    accumulate_llm_usage(
        context,
        _completion(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        requested_model="openai/requested",
    )

    assert context["llm_usage"] == {
        "calls": 2,
        "prompt_tokens": 14,
        "completion_tokens": 9,
        "total_tokens": 23,
        "by_model": {
            "openai/test-model": {
                "calls": 2,
                "prompt_tokens": 14,
                "completion_tokens": 9,
                "total_tokens": 23,
            }
        },
    }


def test_accumulate_llm_usage_tolerates_missing_provider_usage():
    context = {}
    response = SimpleNamespace(model=None, usage=None)

    accumulate_llm_usage(context, response, requested_model="openai/requested")

    assert context["llm_usage"]["calls"] == 1
    assert context["llm_usage"]["total_tokens"] == 0
    assert context["llm_usage"]["by_model"]["openai/requested"]["calls"] == 1


def test_run_async_returns_aggregated_usage(monkeypatch):
    chain = MetaChain()

    async def fake_completion(**_kwargs):
        return _completion()

    monkeypatch.setattr(chain, "try_completion_with_truncation", fake_completion)
    response = asyncio.run(
        chain.run_async(
            Agent(name="Test Agent", model="openai/requested"),
            [{"role": "user", "content": "hello"}],
            debug=False,
        )
    )

    assert response.context_variables["llm_usage"]["calls"] == 1
    assert response.context_variables["llm_usage"]["total_tokens"] == 18
    assert response.context_variables["llm_usage"]["by_model"]["openai/test-model"][
        "total_tokens"
    ] == 18
