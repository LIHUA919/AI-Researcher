import os
from pathlib import Path
import sys

import benchmark.run_one_layer_vq_closed_loop_v2 as runner
from benchmark.run_one_layer_vq_closed_loop_v2 import (
    arm_order,
    build_trial_command,
    resolved_cache_path,
    summarize_trials,
    trial_environment,
)


def test_arm_order_alternates_across_seeds():
    assert arm_order(0) == ("control", "treatment")
    assert arm_order(1) == ("treatment", "control")


def test_trial_command_holds_everything_but_recall_budget_constant(tmp_path):
    common = {
        "python": Path("/venv/python"),
        "model": "openai/test",
        "output_root": tmp_path,
        "seed": 401,
        "port": 13000,
    }
    control, control_cache, _ = build_trial_command(arm="control", **common)
    treatment, treatment_cache, _ = build_trial_command(arm="treatment", **common)

    def option(command, name):
        return command[command.index(name) + 1]

    assert option(control, "--experience-mode") == "closed-loop"
    assert option(treatment, "--experience-mode") == "closed-loop"
    assert option(control, "--max-loop-iterations") == "3"
    assert option(treatment, "--max-loop-iterations") == "3"
    assert option(control, "--recall-item-budget") == "0"
    assert option(control, "--recall-token-budget") == "0"
    assert option(treatment, "--recall-item-budget") == "8"
    assert option(treatment, "--recall-token-budget") == "3000"
    assert control_cache == resolved_cache_path(
        tmp_path / "seed-401/control/cache",
        "openai/test",
    )
    assert treatment_cache == resolved_cache_path(
        tmp_path / "seed-401/treatment/cache",
        "openai/test",
    )


def test_trial_environment_imports_package_from_repository_root(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/existing/path")

    environment = trial_environment()

    entries = environment["PYTHONPATH"].split(os.pathsep)
    assert entries[0].endswith("/AI-Researcher")
    assert entries[1] == "/existing/path"
    if sys.platform == "darwin":
        assert environment["PLAYWRIGHT_BROWSER_CHANNEL"] == "chrome"
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["TRANSFORMERS_OFFLINE"] == "1"


def test_source_revision_includes_frozen_training_templates(
    monkeypatch,
    tmp_path,
):
    (tmp_path / "research_agent").mkdir()
    (tmp_path / "research_agent/runtime.py").write_text(
        "runtime = 1\n",
        encoding="utf-8",
    )
    evaluator = tmp_path / "benchmark/evaluators/one_layer_vq_smoke"
    evaluator.mkdir(parents=True)
    (evaluator / "contract.yaml").write_text("version: 1\n", encoding="utf-8")
    launcher = tmp_path / "benchmark/run_one_layer_vq_closed_loop_v2.py"
    launcher.write_text("launcher = 1\n", encoding="utf-8")
    protocol = tmp_path / "benchmark/real_smoke/one_layer_vq/train.py"
    protocol.parent.mkdir(parents=True)
    protocol.write_text("protocol = 1\n", encoding="utf-8")
    entrypoint = (
        tmp_path
        / "benchmark/process/dataset_candidate/vq/run_training_testing.py"
    )
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text("entrypoint = 1\n", encoding="utf-8")
    instance = tmp_path / "benchmark/final/vq/one_layer_vq.json"
    instance.parent.mkdir(parents=True)
    instance.write_text('{"id": "one_layer_vq"}\n', encoding="utf-8")
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner, "INSTANCE_PATH", instance)

    before = runner.source_revision()
    protocol.write_text("protocol = 2\n", encoding="utf-8")
    after_protocol_change = runner.source_revision()
    entrypoint.write_text("entrypoint = 2\n", encoding="utf-8")
    after_entrypoint_change = runner.source_revision()

    assert after_protocol_change != before
    assert after_entrypoint_change != after_protocol_change


def test_source_revision_excludes_generated_agent_artifacts(
    monkeypatch,
    tmp_path,
):
    agent_root = tmp_path / "research_agent"
    agent_root.mkdir()
    source = agent_root / "runtime.py"
    source.write_text("runtime = 1\n", encoding="utf-8")
    generated_files = (
        agent_root / "workplace_paper/run/project/protocol.py",
        agent_root / "cache_trial/agents/state.json",
        agent_root / "logs/run/result.json",
        agent_root / "paper_db/index.json",
        agent_root / "terminal_tmp/command.py",
    )
    for generated in generated_files:
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text("generated = 1\n", encoding="utf-8")
    evaluator = tmp_path / "benchmark/evaluators/one_layer_vq_smoke"
    evaluator.mkdir(parents=True)
    (evaluator / "contract.yaml").write_text("version: 1\n", encoding="utf-8")
    launcher = tmp_path / "benchmark/run_one_layer_vq_closed_loop_v2.py"
    launcher.write_text("launcher = 1\n", encoding="utf-8")
    protocol = tmp_path / "benchmark/real_smoke/one_layer_vq/train.py"
    protocol.parent.mkdir(parents=True)
    protocol.write_text("protocol = 1\n", encoding="utf-8")
    entrypoint = (
        tmp_path
        / "benchmark/process/dataset_candidate/vq/run_training_testing.py"
    )
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text("entrypoint = 1\n", encoding="utf-8")
    instance = tmp_path / "benchmark/final/vq/one_layer_vq.json"
    instance.parent.mkdir(parents=True)
    instance.write_text('{"id": "one_layer_vq"}\n', encoding="utf-8")
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner, "AGENT_ROOT", agent_root)
    monkeypatch.setattr(runner, "INSTANCE_PATH", instance)

    before = runner.source_revision()
    for generated in generated_files:
        generated.write_text("generated = 2\n", encoding="utf-8")
    after_generated_changes = runner.source_revision()
    source.write_text("runtime = 2\n", encoding="utf-8")
    after_source_change = runner.source_revision()

    assert after_generated_changes == before
    assert after_source_change != after_generated_changes


def test_summary_withholds_claim_when_any_pair_is_invalid():
    trials = [
        {
            "seed": 1,
            "arm": "control",
            "score": 0.2,
            "valid": True,
            "attempts_used": 3,
            "tokens": 100,
            "wall_seconds": 10,
            "gpu_hours": 0,
            "failure_signature": None,
        },
        {
            "seed": 1,
            "arm": "treatment",
            "score": 0.3,
            "valid": False,
            "attempts_used": 3,
            "tokens": 120,
            "wall_seconds": 11,
            "gpu_hours": 0,
            "failure_signature": "bad_evidence",
        },
    ]

    report = summarize_trials(
        trials,
        seeds=[1],
        model="openai/test",
        revision="revision",
    )

    assert report["paired_deltas"] == [None]
    assert report["experience_gain"] is None
    assert report["claim_valid"] is False
