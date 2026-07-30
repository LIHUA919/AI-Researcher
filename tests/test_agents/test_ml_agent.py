from types import SimpleNamespace

from research_agent.inno.agents.inno_agent.ml_agent import get_ml_agent


def test_ml_agent_keeps_host_plan_paths_out_of_container_instructions():
    agent = get_ml_agent(
        "test-model",
        code_env=SimpleNamespace(workplace_name="workplace"),
    )

    instructions = agent.instructions(
        {
            "working_dir": "workplace",
            "plan_artifacts": {
                "dataset_plan": "/Users/example/private/dataset_plan.json",
            },
        }
    )

    assert "/Users/example" not in instructions
    assert "dataset_plan: content is included in the task prompt" in instructions
    assert "/workplace/project/run_training_testing.py" in instructions
    assert agent.max_turns == 24


def test_ml_agent_protects_frozen_protocol_and_forbids_container_installs():
    agent = get_ml_agent(
        "test-model",
        code_env=SimpleNamespace(workplace_name="workplace"),
        frozen_protocol=True,
    )

    instructions = agent.instructions(
        {
            "working_dir": "workplace",
            "evaluation_evidence_guidance": (
                "This frozen second-round protocol is mandatory."
            ),
        }
    )

    assert "Do not execute either frozen file inside the container" in instructions
    assert "Do not install packages" in instructions
    assert "Do not create, modify, replace, or delete them" in instructions
    tool_names = {tool.__name__ for tool in agent.functions}
    assert "read_file" in tool_names
    assert "case_resolved" in tool_names
    assert "create_file" not in tool_names
    assert "write_file" not in tool_names
    assert "execute_command" not in tool_names
    assert "run_python" not in tool_names
