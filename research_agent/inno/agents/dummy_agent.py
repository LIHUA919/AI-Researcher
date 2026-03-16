from research_agent.inno.registry import register_agent
from research_agent.inno.types import Agent


@register_agent("get_dummy_agent")
def get_dummy_agent(model: str, **kwargs):
    """Return a minimal agent for smoke tests and CLI sanity checks."""
    return Agent(
        name="Dummy Agent",
        model=model,
        instructions="You are a minimal test agent. Reply briefly to the user.",
        functions=[],
        tool_choice=None,
        parallel_tool_calls=False,
    )
