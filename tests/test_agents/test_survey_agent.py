from types import SimpleNamespace

import pytest

from research_agent.inno.agents.inno_agent.idea_agent import (
    case_resolved as idea_case_resolved,
    get_survey_agent as get_idea_survey_agent,
)
from research_agent.inno.agents.inno_agent.survey_agent import (
    case_resolved as survey_case_resolved,
    get_survey_agent,
)


def test_survey_case_resolved_preserves_incomplete_note_without_crashing():
    context = {
        "notes": [
            {"definition": "Incomplete concept 1"},
            {"definition": "Incomplete concept 2"},
            {"definition": "Incomplete concept 3"},
        ]
    }

    result = survey_case_resolved(context)

    assert "## Incomplete concept 1" in result.value
    assert "Not provided by the survey sub-agent." in result.value
    assert result.context_variables == context


def test_idea_case_resolved_preserves_incomplete_note_without_crashing():
    context = {
        "notes": [
            {"definition": "Incomplete idea 1"},
            {"definition": "Incomplete idea 2"},
            {"definition": "Incomplete idea 3"},
        ]
    }

    result = idea_case_resolved(context)

    assert "## Incomplete idea 1" in result.value
    assert "Not provided by the survey sub-agent." in result.value
    assert result.context_variables == context


def test_survey_agents_have_bounded_definition_budget():
    file_env = SimpleNamespace(docker_workplace="/workplace")
    code_env = SimpleNamespace(workplace_name="workplace")

    agents = (
        get_survey_agent("test-model", file_env=file_env, code_env=code_env),
        get_idea_survey_agent(
            "test-model",
            file_env=file_env,
            code_env=code_env,
        ),
    )

    for agent in agents:
        assert agent.max_turns == 50
        assert "at most 6" in agent.instructions({})


@pytest.mark.parametrize(
    "resolver",
    [survey_case_resolved, idea_case_resolved],
)
def test_survey_case_resolved_rejects_empty_notes(resolver):
    with pytest.raises(ValueError, match="At least 3"):
        resolver({"notes": []})
