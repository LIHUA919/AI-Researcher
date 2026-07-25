from dataclasses import dataclass

from research_agent.inno.evals.trace import AgentStepTrace, ToolCallTrace
from research_agent.inno.workflow.flowcache import AgentModule, ToolModule
from research_agent.inno.workflow.cache_identity import behavioral_cache_key


@dataclass
class FakeResponse:
    messages: list
    context_variables: dict
    agent: object = None


class FakeClient:
    def __init__(self):
        self.last_max_turns = None
        self.call_count = 0

    async def run_async(self, agent, messages, context_variables=None, debug=False, max_turns=float("inf")):
        self.call_count += 1
        self.last_max_turns = max_turns
        return FakeResponse(
            messages=[{"role": "assistant", "content": f"done by {agent.name}"}],
            context_variables={"status": "ok"},
            agent=agent,
        )


class FakeClientWithTurns:
    def __init__(self):
        self.last_max_turns = None

    async def run_async(self, agent, messages, context_variables=None, debug=False, max_turns=float("inf")):
        self.last_max_turns = max_turns
        return FakeResponse(
            messages=[{"role": "assistant", "content": f"done by {agent.name}"}],
            context_variables={"status": "ok"},
            agent=agent,
        )


class FakeAgent:
    def __init__(self, name: str):
        self.name = name


def test_tool_module_records_trace(tmp_dir):
    traces = []

    def sample_tool(query: str):
        return {"result": f"found {query}"}

    module = ToolModule(
        sample_tool,
        tmp_dir,
        trace_recorder=traces.append,
        trace_owner="Flow",
    )

    result = module({"query": "papers"})

    assert result["result"] == "found papers"
    assert len(traces) == 1
    assert isinstance(traces[0], ToolCallTrace)
    assert traces[0].tool_name == "sample_tool"


def test_agent_module_records_trace(tmp_dir):
    traces = []
    client = FakeClient()
    module = AgentModule(
        FakeAgent("Survey Agent"),
        client,
        tmp_dir,
        trace_recorder=traces.append,
    )

    import asyncio

    messages, context = asyncio.run(
        module([{"role": "user", "content": "summarize this"}], {})
    )

    assert context["status"] == "ok"
    assert len(messages) >= 1
    assert len(traces) == 1
    assert isinstance(traces[0], AgentStepTrace)
    assert traces[0].agent_name == "Survey Agent"
    assert traces[0].input_summary == "summarize this"


def test_agent_module_passes_agent_max_turns(tmp_dir):
    client = FakeClientWithTurns()
    agent = FakeAgent("Prepare Agent")
    agent.max_turns = 7
    module = AgentModule(agent, client, tmp_dir)

    import asyncio

    asyncio.run(module([{"role": "user", "content": "pick repos"}], {}))

    assert client.last_max_turns == 7


def test_tool_cache_key_includes_arguments_and_reuses_without_prompt(tmp_dir):
    calls = []

    def sample_tool(query: str):
        calls.append(query)
        return {"query": query}

    module = ToolModule(sample_tool, tmp_dir, cache_policy="reuse")

    assert module({"query": "alpha"}) == {"query": "alpha"}
    assert module({"query": "alpha"}) == {"query": "alpha"}
    assert module({"query": "beta"}) == {"query": "beta"}
    assert calls == ["alpha", "beta"]


def test_agent_cache_isolates_memory_off_and_memory_on(tmp_dir):
    import asyncio

    client = FakeClient()
    module = AgentModule(
        FakeAgent("Plan Agent"),
        client,
        tmp_dir,
        cache_policy="reuse",
    )
    messages = [{"role": "user", "content": "make a plan"}]

    asyncio.run(module(list(messages), {"recall_snapshot_id": "off"}))
    asyncio.run(module(list(messages), {"recall_snapshot_id": "off"}))
    asyncio.run(module(list(messages), {"recall_snapshot_id": "snapshot-1"}))

    assert client.call_count == 2


def test_disabled_cache_does_not_write_files(tmp_dir):
    def sample_tool(query: str):
        return query

    module = ToolModule(sample_tool, tmp_dir, cache_policy="disabled")
    module({"query": "alpha"})

    from pathlib import Path

    assert not (Path(tmp_dir) / "tools").exists()


def test_behavioral_cache_identity_covers_recall_code_data_and_evaluator():
    base = {
        "task_id": "task-1",
        "stage": "plan",
        "normalized_input": {"query": "q"},
        "model_configuration": {"model": "m"},
        "tool_configuration": {"tools": ["search"]},
        "recall_snapshot_id": "off",
        "code_revision": "abc",
        "dataset_digest": "data-1",
        "evaluation_contract_version": "1",
    }
    original = behavioral_cache_key(**base)

    for field, value in (
        ("recall_snapshot_id", "snapshot-1"),
        ("code_revision", "def"),
        ("dataset_digest", "data-2"),
        ("evaluation_contract_version", "2"),
    ):
        changed = dict(base)
        changed[field] = value
        assert behavioral_cache_key(**changed) != original
