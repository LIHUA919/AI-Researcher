from types import SimpleNamespace

from research_agent.inno.agents.inno_agent.ml_agent import get_ml_agent


def test_ml_agent_has_bounded_turns():
    agent = get_ml_agent(model="test-model", code_env=None)

    assert agent.max_turns == 24


def test_ml_agent_instructions_prioritize_reference_paths_and_plan_artifacts():
    code_env = SimpleNamespace(workplace_name="workplace")
    agent = get_ml_agent(model="test-model", code_env=code_env)

    instructions = agent.instructions(
        {
            "working_dir": "workplace",
            "prepare_result": {
                "reference_paths": ["/workplace/VQGAN-pytorch", "/workplace/vqvae-pytorch"],
            },
            "plan_artifacts": {
                "dataset_plan": "cache/plan_stages/dataset_plan.json",
                "training_plan": "cache/plan_stages/training_plan.json",
            },
        }
    )

    assert "Do NOT run `gen_code_tree_structure` on the entire `/workplace` root" in instructions
    assert "/workplace/VQGAN-pytorch" in instructions
    assert "cache/plan_stages/dataset_plan.json" in instructions
