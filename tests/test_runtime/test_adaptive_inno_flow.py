from types import SimpleNamespace

import research_agent.run_infer_plan as run_infer_plan


def test_inno_flow_builds_intervention_planner_on_its_traced_client(
    monkeypatch,
    tmp_path,
):
    captured = {}
    facade = SimpleNamespace()

    def fake_build(config, *, planner):
        captured["config"] = config
        captured["planner"] = planner
        return facade

    monkeypatch.setattr(
        run_infer_plan,
        "build_adaptive_experiment_runner",
        fake_build,
    )
    config = SimpleNamespace(
        project_dir=tmp_path / "project",
        contract_path=tmp_path / "contract.yaml",
        ledger=SimpleNamespace(),
    )

    flow = run_infer_plan.InnoFlow(
        cache_path=str(tmp_path / "cache"),
        model="test-model",
        code_env=SimpleNamespace(),
        web_env=SimpleNamespace(),
        file_env=SimpleNamespace(),
        adaptive_experiment_config=config,
    )

    assert captured["config"] is config
    assert flow.adaptive_experiment is facade
    assert captured["planner"] is flow.intervention_planner
    assert flow.intervention_planner.agent_module.client is flow.client
    assert flow.intervention_planner.agent_module.cache_policy == "disabled"
    assert flow.intervention_planner.agent_module.agent.model == "test-model"
