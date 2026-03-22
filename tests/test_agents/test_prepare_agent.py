import json

from research_agent.inno.agents.inno_agent.prepare_agent import case_resolved, get_prepare_agent


def test_case_resolved_persists_prepare_result(tmp_path):
    result = case_resolved(
        reference_codebases=["repo_a", "repo_b", "repo_c", "repo_d", "repo_e"],
        reference_paths=["/workplace/repo_a", "/workplace/repo_b", "/workplace/repo_c", "/workplace/repo_d", "/workplace/repo_e"],
        reference_papers=["p1", "p2", "p3", "p4", "p5"],
        context_variables={"prepare_artifact_dir": str(tmp_path)},
    )

    artifact_path = tmp_path / "prepare_result.json"
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["reference_codebases"][0] == "repo_a"
    assert result.context_variables["prepare_artifacts"]["prepare_result"] == str(artifact_path)


def test_prepare_agent_has_bounded_turns():
    agent = get_prepare_agent(model="test-model", code_env=None)
    assert agent.max_turns == 14
