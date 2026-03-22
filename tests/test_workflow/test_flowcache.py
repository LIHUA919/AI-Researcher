from dataclasses import dataclass

from research_agent.inno.evals.trace import AgentStepTrace, ToolCallTrace
from research_agent.inno.workflow.flowcache import AgentModule, FlowModule, ToolModule


@dataclass
class FakeResponse:
    messages: list
    context_variables: dict
    agent: object = None


class FakeClient:
    def __init__(self):
        self.last_max_turns = None

    async def run_async(self, agent, messages, context_variables=None, debug=False, max_turns=float("inf")):
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
