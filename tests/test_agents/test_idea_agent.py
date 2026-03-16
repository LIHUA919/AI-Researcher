from types import SimpleNamespace


def test_get_survey_agent_constructs_without_name_error():
    from research_agent.inno.agents.inno_agent.idea_agent import get_survey_agent

    file_env = SimpleNamespace(docker_workplace="/tmp/papers")
    code_env = SimpleNamespace(workplace_name="workspace")

    agent = get_survey_agent("gpt-4o", file_env=file_env, code_env=code_env)

    assert agent.name == "Survey Agent"
    assert len(agent.functions) == 2
