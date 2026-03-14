"""Tests for core type definitions (Agent, Response, Result)."""

from research_agent.inno.types import Agent, Response, Result


class TestAgent:
    def test_default_agent(self):
        agent = Agent()
        assert agent.name == "Agent"
        assert agent.model == "gpt-4o"
        assert agent.instructions == "You are a helpful agent."
        assert agent.functions == []
        assert agent.parallel_tool_calls is False

    def test_agent_custom(self):
        agent = Agent(name="TestAgent", model="gpt-3.5-turbo", instructions="Do X")
        assert agent.name == "TestAgent"
        assert agent.model == "gpt-3.5-turbo"
        assert agent.instructions == "Do X"

    def test_agent_callable_instructions(self):
        agent = Agent(instructions=lambda cv: f"Hello {cv.get('name', 'world')}")
        assert callable(agent.instructions)
        assert agent.instructions({"name": "test"}) == "Hello test"


class TestResponse:
    def test_default_response(self):
        resp = Response()
        assert resp.messages == []
        assert resp.agent is None
        assert resp.context_variables == {}

    def test_response_with_agent(self):
        agent = Agent(name="A")
        resp = Response(agent=agent, messages=[{"role": "user", "content": "hi"}])
        assert resp.agent.name == "A"
        assert len(resp.messages) == 1


class TestResult:
    def test_default_result(self):
        r = Result()
        assert r.value == ""
        assert r.agent is None
        assert r.context_variables == {}
        assert r.image is None

    def test_result_with_value(self):
        r = Result(value="done", context_variables={"k": "v"})
        assert r.value == "done"
        assert r.context_variables["k"] == "v"

    def test_result_with_agent(self):
        agent = Agent(name="Sub")
        r = Result(value="ok", agent=agent)
        assert r.agent.name == "Sub"
