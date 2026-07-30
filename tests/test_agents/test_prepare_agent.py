from research_agent.inno.agents.inno_agent.prepare_agent import case_resolved, get_prepare_agent
from research_agent.runtime.artifacts import load_stage_payload


def test_case_resolved_persists_prepare_result(tmp_path):
    result = case_resolved(
        reference_codebases=["repo_a", "repo_b", "repo_c", "repo_d", "repo_e"],
        reference_paths=["/workplace/repo_a", "/workplace/repo_b", "/workplace/repo_c", "/workplace/repo_d", "/workplace/repo_e"],
        reference_papers=["p1", "p2", "p3", "p4", "p5"],
        context_variables={"prepare_artifact_dir": str(tmp_path)},
    )

    artifact_path = tmp_path / "prepare_result.json"
    assert artifact_path.exists()
    payload = load_stage_payload(artifact_path, stage="prepare")
    assert payload["reference_codebases"][0] == "repo_a"
    assert result.context_variables["prepare_artifacts"]["prepare_result"] == str(artifact_path)


def test_prepare_agent_has_bounded_turns():
    agent = get_prepare_agent(model="test-model", code_env=None)
    assert agent.max_turns == 14


def test_prepare_agent_forbids_clones_for_frozen_contract():
    agent = get_prepare_agent(model="test-model", code_env=None)

    instructions = agent.instructions(
        {
            "working_dir": "workplace",
            "evaluation_evidence_guidance": (
                "This frozen second-round protocol is mandatory."
            ),
        }
    )

    assert "Do not clone any repository" in instructions
    assert "/workplace/project" in instructions
    assert "/workplace/dataset_candidate" in instructions
