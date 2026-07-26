import json
from pathlib import Path

import pytest

from research_agent.inno.evals import (
    BenchmarkConfigurationError,
    ExperienceBenchmarkRunner,
    ExperienceBenchmarkTask,
    TrialResult,
    load_scientist_bench_task,
    save_experience_gain_report,
)


def task(direction="maximize"):
    return ExperienceBenchmarkTask(
        task_id="task-1",
        query="q",
        goal="g",
        primary_metric="score",
        direction=direction,
    )


def run_report(trial_fn, *, direction="maximize"):
    return ExperienceBenchmarkRunner(trial_fn).run(
        task(direction),
        seeds=[1, 2, 3],
        model="same-model",
        budget={"tokens": 100},
        evaluator_version="eval@1",
        dataset_digest="data@1",
        code_revision="abc",
    )


def test_experience_gain_uses_paired_equal_configuration():
    configurations = []

    def trial(config):
        configurations.append(config)
        return TrialResult(
            score=float(config.seed) + (0.5 if config.mode == "closed-loop" else 0),
            tokens=100,
            wall_seconds=2,
            artifact_refs=[f"artifact://{config.mode}/{config.seed}"],
        )

    report = run_report(trial)

    assert report.experience_gain == pytest.approx(0.5)
    assert report.paired_deltas == pytest.approx([0.5, 0.5, 0.5])
    assert [pair.seed for pair in report.trial_pairs] == [1, 2, 3]
    assert report.trial_pairs[0].baseline.artifact_refs == ["artifact://off/1"]
    assert report.trial_pairs[0].closed_loop.artifact_refs == [
        "artifact://closed-loop/1"
    ]
    assert [pair.execution_order for pair in report.trial_pairs] == [
        ["off", "closed-loop"],
        ["closed-loop", "off"],
        ["off", "closed-loop"],
    ]
    assert report.baseline.total_tokens == report.closed_loop.total_tokens == 300
    by_seed = {
        seed: {
            config.mode: config
            for config in configurations
            if config.seed == seed
        }
        for seed in (1, 2, 3)
    }
    for pair in by_seed.values():
        baseline = pair["off"]
        closed = pair["closed-loop"]
        assert baseline.mode == "off"
        assert closed.mode == "closed-loop"
        assert baseline.model_copy(update={"mode": "closed-loop"}) == closed


def test_experience_gain_respects_minimize_direction():
    report = run_report(
        lambda config: TrialResult(
            score=0.8 if config.mode == "off" else 0.6
        ),
        direction="minimize",
    )

    assert report.experience_gain == pytest.approx(0.2)


def test_repeated_failure_rate_and_valid_rate_are_reported():
    report = run_report(
        lambda config: TrialResult(
            score=0.0,
            valid=config.seed != 3,
            failure_signature="same-failure" if config.mode == "off" else None,
        )
    )

    assert report.baseline.repeated_failure_rate == pytest.approx(2 / 3)
    assert report.baseline.valid_rate == pytest.approx(2 / 3)
    assert report.closed_loop.repeated_failure_rate == 0


def test_runner_rejects_empty_or_duplicate_seed_pairs():
    runner = ExperienceBenchmarkRunner(lambda _: TrialResult(score=0))
    common = {
        "model": "m",
        "budget": {},
        "evaluator_version": "1",
        "dataset_digest": "d",
        "code_revision": "c",
    }

    with pytest.raises(BenchmarkConfigurationError):
        runner.run(task(), seeds=[], **common)
    with pytest.raises(BenchmarkConfigurationError):
        runner.run(task(), seeds=[1, 1], **common)


def test_verified_runner_requires_provenance_and_comparable_manifests():
    common = {
        "seeds": [1],
        "model": "m",
        "budget": {},
        "evaluator_version": "1",
        "dataset_digest": "d",
        "code_revision": "c",
    }
    runner = ExperienceBenchmarkRunner(
        lambda _: TrialResult(score=1),
        require_verified_trials=True,
    )
    with pytest.raises(BenchmarkConfigurationError, match="missing provenance"):
        runner.run(task(), **common)

    def mismatched(config):
        return TrialResult(
            score=1,
            artifact_refs=["artifact.json"],
            artifact_digests={"artifact.json": "a" * 64},
            score_source="verification_record",
            verification_id=f"verification-{config.mode}",
            verification_ids=[f"verification-{config.mode}"],
            attempt_id=f"attempt-{config.mode}",
            attempt_ids=[f"attempt-{config.mode}"],
            selected_iteration=1,
            recall_snapshot_id=f"recall-{config.mode}",
            manifest_digest=f"manifest-{config.mode}",
            comparison_digest=f"comparison-{config.mode}",
            evaluator_digest="evaluator",
        )

    with pytest.raises(BenchmarkConfigurationError, match="comparison manifests"):
        ExperienceBenchmarkRunner(
            mismatched,
            require_verified_trials=True,
        ).run(task(), **common)


def test_report_round_trip_and_scientist_bench_adapter(tmp_path):
    report = run_report(lambda config: TrialResult(score=float(config.seed)))
    report_path = tmp_path / "report.json"
    save_experience_gain_report(report, report_path)

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["experience_gain"] == 0

    repository_root = Path(__file__).resolve().parents[2]
    scientist_task = load_scientist_bench_task(
        repository_root / "benchmark" / "final" / "vq" / "one_layer_vq.json",
        task_level="task1",
        primary_metric="codebook_utilization",
    )
    assert scientist_task.task_id == "one_layer_vq:task1"
    assert "linear transformation" in scientist_task.query.lower()
