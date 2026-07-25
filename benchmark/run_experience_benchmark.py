from __future__ import annotations

import argparse
from pathlib import Path

from research_agent.inno.evals.experience_benchmark import (
    ExperienceBenchmarkRunner,
    ExperienceBenchmarkTask,
    TrialConfiguration,
    TrialResult,
    save_experience_gain_report,
)


def deterministic_trial(config: TrialConfiguration) -> TrialResult:
    seed_noise = (config.seed % 5) * 0.005
    baseline_score = 0.5 + seed_noise
    score = baseline_score + (0.15 if config.mode == "closed-loop" else 0.0)
    return TrialResult(
        score=score,
        valid=True,
        tokens=1000,
        wall_seconds=1.0,
        failure_signature="repeated-baseline-error" if config.mode == "off" else None,
        artifact_refs=[f"deterministic://{config.task_id}/{config.mode}/{config.seed}"],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="benchmark/results/deterministic_experience_gain.json",
    )
    args = parser.parse_args()
    task = ExperienceBenchmarkTask(
        task_id="deterministic-score",
        query="Improve a deterministic score using verified prior experience.",
        goal="Demonstrate the paired Experience Gain reporting path.",
        primary_metric="score",
        direction="maximize",
        metadata={"synthetic": True},
    )
    report = ExperienceBenchmarkRunner(deterministic_trial).run(
        task,
        seeds=[1, 2, 3, 4, 5],
        model="deterministic-fixture",
        budget={"iterations": 2, "tokens": 1000},
        evaluator_version="deterministic-score@1",
        dataset_digest="deterministic-dataset@1",
        code_revision="fixture",
        metadata={
            "synthetic": True,
            "disclaimer": "Infrastructure fixture; not evidence of Scientist-Bench improvement.",
        },
    )
    output = save_experience_gain_report(report, Path(args.output))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
