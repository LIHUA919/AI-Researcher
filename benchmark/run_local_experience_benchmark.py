from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import time
from typing import Callable

from research_agent.inno.evals.experience_benchmark import (
    ExperienceBenchmarkRunner,
    ExperienceBenchmarkTask,
    TrialConfiguration,
    TrialResult,
    save_experience_gain_report,
)
from research_agent.inno.experience import (
    ArtifactRef,
    CommandVerifier,
    ExperienceLoop,
    ExperimentAttempt,
    Hypothesis,
    KeywordExperienceRetriever,
    KnowledgeGate,
    Observation,
    RecallContext,
    RecallRequest,
    RunCompletion,
    SQLiteExperimentLedger,
    load_evaluation_contract,
)


EVALUATOR_DIR = Path(__file__).parent / "evaluators" / "operator_selection"
OPERATORS = ("identity", "square")
OPERATOR_PATTERN = re.compile(r"operator `([^`]+)`")


@dataclass(frozen=True)
class OperatorSelection:
    operator: str
    tokens: int = 0


OperatorSelector = Callable[
    [TrialConfiguration, RecallContext],
    OperatorSelection,
]


def _digest(payload) -> str:
    if not isinstance(payload, str):
        payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _artifact(path: Path, *, media_type: str) -> ArtifactRef:
    content = path.read_bytes()
    return ArtifactRef(
        path=str(path.resolve()),
        sha256=hashlib.sha256(content).hexdigest(),
        media_type=media_type,
        size_bytes=len(content),
    )


def _solution(operator: str) -> str:
    implementations = {
        "identity": "def transform(value):\n    return value\n",
        "square": "def transform(value):\n    return value * value\n",
    }
    return implementations[operator]


class LocalVerifiedExperienceTrial:
    """Exercise a real evaluator while varying only Recall availability."""

    def __init__(
        self,
        output_root: Path,
        *,
        evaluator_dir: Path = EVALUATOR_DIR,
        selector: OperatorSelector | None = None,
        domain: str = "behavioral-microbenchmark",
    ) -> None:
        self.output_root = output_root
        self.evaluator_dir = evaluator_dir
        self.selector = selector or self._select_first_untried
        self.domain = domain

    @staticmethod
    def _select_first_untried(
        config: TrialConfiguration,
        recall: RecallContext,
    ) -> OperatorSelection:
        del config
        tried = {
            match.group(1)
            for item in recall.items
            if (match := OPERATOR_PATTERN.search(item.lesson)) is not None
        }
        return OperatorSelection(
            operator=next(
                (candidate for candidate in OPERATORS if candidate not in tried),
                OPERATORS[0],
            )
        )

    def __call__(self, config: TrialConfiguration) -> TrialResult:
        started = time.monotonic()
        trial_root = (
            self.output_root
            / config.task_id
            / config.mode
            / f"seed-{config.seed}"
        )
        trial_root.mkdir(parents=True, exist_ok=True)
        store_path = trial_root / "experience.sqlite3"
        contract = load_evaluation_contract(self.evaluator_dir / "contract.yaml")
        final_score = 0.0
        selected: list[str] = []
        final_refs: list[str] = []
        total_tokens = 0

        for iteration in range(1, int(config.budget["iterations"]) + 1):
            ledger = SQLiteExperimentLedger(store_path)
            loop = ExperienceLoop(
                ledger=ledger,
                retriever=KeywordExperienceRetriever(ledger),
                verifier=CommandVerifier(contract_dir=self.evaluator_dir),
                knowledge_gate=KnowledgeGate(
                    domain=self.domain,
                    model_family=config.model,
                ),
                evaluation_contract=contract,
                mode="closed-loop" if config.mode == "closed-loop" else "record",
            )
            recall = loop.before_run(
                RecallRequest(
                    query="Select a transformation operator without repeating failures.",
                    task_id=config.task_id,
                    domain=self.domain,
                    dataset_id=config.dataset_digest,
                    model_family=config.model,
                    max_items=4,
                    token_budget=512,
                )
            )
            decision = self.selector(config, recall)
            operator = decision.operator
            if operator not in OPERATORS:
                raise ValueError(f"unsupported operator selection: {operator}")
            total_tokens += decision.tokens
            selected.append(operator)
            attempt_dir = trial_root / f"attempt-{iteration}"
            attempt_dir.mkdir(exist_ok=True)
            solution_path = attempt_dir / "solution.py"
            solution_path.write_text(_solution(operator), encoding="utf-8")
            log_path = attempt_dir / "run.log"
            log_path.write_text(
                f"selected operator={operator} seed={config.seed}\n",
                encoding="utf-8",
            )
            now = datetime.now(timezone.utc)
            parent_ids = sorted(
                {
                    source_id
                    for item in recall.items
                    for source_id in item.source_experience_ids
                }
            )
            hypothesis_payload = {
                "task_id": config.task_id,
                "statement": f"Try operator `{operator}` for the hidden transformation.",
                "mechanism": "A verified negative result should prevent repeating the same operator.",
                "expected_metric": "score",
                "metric_direction": "maximize",
                "conditions": ["fixed hidden transformation dataset"],
                "parent_experience_ids": parent_ids,
                "citations": [item.citation_id for item in recall.items],
            }
            hypothesis = Hypothesis(
                hypothesis_id=_digest(
                    {
                        **hypothesis_payload,
                        "seed": config.seed,
                        "iteration": iteration,
                    }
                ),
                created_at=now,
                **hypothesis_payload,
            )
            attempt = ExperimentAttempt(
                attempt_id=_digest(
                    {
                        "mode": config.mode,
                        "seed": config.seed,
                        "iteration": iteration,
                        "operator": operator,
                        "recall": recall.snapshot_id,
                    }
                ),
                run_id=f"{config.task_id}:{config.mode}:{config.seed}",
                iteration_id=f"{config.mode}:{config.seed}:{iteration}",
                task_id=config.task_id,
                hypothesis_id=hypothesis.hypothesis_id,
                code_revision=_digest(solution_path.read_text(encoding="utf-8")),
                dataset_id=config.dataset_digest,
                dataset_digest=config.dataset_digest,
                model_config_digest=_digest(config.model),
                seed=config.seed,
                budget=config.budget,
                evaluation_contract_id=(
                    f"{contract.contract_id}@{contract.version}"
                ),
                recall_snapshot_id=recall.snapshot_id,
                status="completed",
                created_at=now,
            )
            refs = [
                _artifact(solution_path, media_type="text/x-python"),
                _artifact(log_path, media_type="text/plain"),
            ]
            observation = Observation(
                observation_id=_digest(
                    {
                        "attempt": attempt.attempt_id,
                        "artifacts": [ref.sha256 for ref in refs],
                    }
                ),
                attempt_id=attempt.attempt_id,
                exit_code=0,
                metrics={},
                artifact_refs=refs,
                started_at=now,
                completed_at=now,
                environment_fingerprint=(
                    f"python={platform.python_version()};"
                    f"platform={platform.system()}-{platform.machine()}"
                ),
            )
            outcome = loop.after_run(
                RunCompletion(
                    hypothesis=hypothesis,
                    attempt=attempt,
                    observation=observation,
                    analysis=(
                        f"Do not repeat operator `{operator}` if its independently "
                        "verified outcome is negative."
                    ),
                    iteration_number=iteration,
                    max_iterations=int(config.budget["iterations"]),
                )
            )
            assert outcome.verification is not None
            final_score = outcome.verification.verified_metrics["score"]
            final_refs = [ref.path for ref in outcome.verification.evidence_refs]
            if outcome.action == "completed":
                break

        repeated_failure = (
            f"repeated-operator:{selected[-1]}"
            if len(selected) > 1 and len(set(selected)) == 1 and final_score <= 0.95
            else None
        )
        return TrialResult(
            score=final_score,
            valid=True,
            tokens=total_tokens,
            wall_seconds=time.monotonic() - started,
            failure_signature=repeated_failure,
            artifact_refs=final_refs,
        )


def run(output_root: Path, *, seeds: list[int]):
    task = ExperienceBenchmarkTask(
        task_id="operator-selection",
        query="Select a transformation operator without repeating verified failures.",
        goal="Measure whether cited negative experience changes the next attempt.",
        primary_metric="score",
        direction="maximize",
        metadata={
            "synthetic": False,
            "scope": "deterministic local behavioral microbenchmark",
        },
    )
    runner = ExperienceBenchmarkRunner(
        LocalVerifiedExperienceTrial(output_root)
    )
    return runner.run(
        task,
        seeds=seeds,
        model="deterministic-policy-v1",
        budget={"iterations": 2},
        evaluator_version="operator-selection@1",
        dataset_digest="hidden-square-transform@1",
        code_revision="local-behavioral-benchmark@1",
        metadata={
            "synthetic": False,
            "claim_scope": (
                "Validates verified recall behavior; not evidence of external "
                "scientific benchmark improvement."
            ),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        default=".ai_researcher/benchmarks/local-experience-gain",
    )
    parser.add_argument("--seeds", default="1,2,3,4,5")
    args = parser.parse_args()
    output_root = Path(args.output_root)
    report_path = output_root / "experience_gain.json"
    if report_path.exists():
        parser.error(
            f"report already exists at {report_path}; use a fresh --output-root"
        )
    seeds = [int(value) for value in args.seeds.split(",") if value]
    report = run(output_root, seeds=seeds)
    print(save_experience_gain_report(report, report_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
