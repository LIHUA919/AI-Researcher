from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import mimetypes
from pathlib import Path
import platform
from typing import Any, Literal

from research_agent.inno.experience import (
    ArtifactRef,
    CommandVerifier,
    EvaluationContract,
    ExperienceLoop,
    ExperienceMode,
    ExperimentAttempt,
    Hypothesis,
    KeywordExperienceRetriever,
    KnowledgeGate,
    LoopOutcome,
    Observation,
    RecallContext,
    RecallRequest,
    RunCompletion,
    SQLiteExperimentLedger,
    load_evaluation_contract,
)
from research_agent.runtime.master import MasterRuntime


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_ref(path: Path) -> ArtifactRef:
    content = path.read_bytes()
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return ArtifactRef(
        path=str(path.resolve()),
        sha256=hashlib.sha256(content).hexdigest(),
        media_type=media_type,
        size_bytes=len(content),
    )


def _tree_digest(root: Path, *, ignored_names: set[str]) -> str:
    entries: list[tuple[str, str]] = []
    if root.is_dir():
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            if path.name in ignored_names or ".git" in path.parts:
                continue
            entries.append((str(path.relative_to(root)), _file_ref(path).sha256))
    return _digest(entries)


class ExperienceConfigurationError(ValueError):
    """Raised when an enabled experience mode lacks a required contract."""


class ExperienceRunAdapter:
    """Connect durable experience services to the two research entrypoints."""

    def __init__(
        self,
        *,
        mode: ExperienceMode,
        store_path: str | Path,
        cache_path: str | Path,
        evaluation_contract_path: str | Path | None = None,
        max_iterations: int = 3,
        recall_item_budget: int = 8,
        recall_token_budget: int = 3000,
    ) -> None:
        self.mode = mode
        self.cache_path = Path(cache_path)
        self.max_iterations = max(1, max_iterations)
        self.recall_item_budget = max(0, recall_item_budget)
        self.recall_token_budget = max(0, recall_token_budget)
        self.ledger = (
            SQLiteExperimentLedger(store_path) if self.mode != "off" else None
        )
        self.contract_path = (
            Path(evaluation_contract_path).resolve()
            if evaluation_contract_path is not None
            else None
        )
        self.contract: EvaluationContract | None = None
        self.loop: ExperienceLoop | None = None

        if self.mode in {"record", "closed-loop"}:
            if self.contract_path is None:
                raise ExperienceConfigurationError(
                    "--evaluation-contract is required when experience recording is enabled"
                )
            self.contract = load_evaluation_contract(self.contract_path)
            assert self.ledger is not None
            self.loop = ExperienceLoop(
                ledger=self.ledger,
                retriever=KeywordExperienceRetriever(self.ledger),
                verifier=CommandVerifier(contract_dir=self.contract_path.parent),
                knowledge_gate=KnowledgeGate(
                    domain="runtime",
                    model_family="runtime",
                ),
                evaluation_contract=self.contract,
                mode=self.mode,
                event_sink=self._emit,
            )

    @classmethod
    def from_args(
        cls,
        args: Any,
        *,
        cache_path: str | Path,
    ) -> "ExperienceRunAdapter":
        return cls(
            mode=getattr(args, "experience_mode", "off"),
            store_path=getattr(
                args,
                "experience_store",
                ".ai_researcher/experience.sqlite3",
            ),
            cache_path=cache_path,
            evaluation_contract_path=getattr(args, "evaluation_contract", None),
            max_iterations=getattr(args, "max_loop_iterations", 3),
            recall_item_budget=getattr(args, "recall_item_budget", 8),
            recall_token_budget=getattr(args, "recall_token_budget", 3000),
        )

    @property
    def records_experience(self) -> bool:
        return self.mode in {"record", "closed-loop"}

    @property
    def runs_closed_loop(self) -> bool:
        return self.mode == "closed-loop"

    def before_run(
        self,
        *,
        task_id: str,
        query: str,
        domain: str,
        dataset_id: str,
        model_family: str,
    ) -> RecallContext | None:
        if self.mode == "off":
            return None
        assert self.ledger is not None
        request = RecallRequest(
            query=query,
            task_id=task_id,
            domain=domain,
            dataset_id=dataset_id,
            model_family=model_family,
            max_items=self.recall_item_budget,
            token_budget=self.recall_token_budget,
        )
        if self.loop is not None:
            return self.loop.before_run(request)
        return KeywordExperienceRetriever(self.ledger).recall(request)

    def verification_check(self, run_id: str):
        if not self.records_experience:
            return None
        assert self.ledger is not None
        return lambda: self.ledger.has_valid_verification(run_id)

    def pending_verification_check(self):
        """Keep a running attempt non-terminal until its evaluator has executed."""

        if not self.records_experience:
            return None
        return lambda: False

    def after_flow(
        self,
        flow_result: dict[str, Any],
        *,
        project_dir: str | Path,
        run_id: str,
        model: str,
        domain: str,
        dataset_id: str,
        model_family: str,
        recall_context: RecallContext | None,
        iteration_number: int,
    ) -> LoopOutcome | None:
        return self._record_result(
            flow_result,
            project_dir=project_dir,
            run_id=run_id,
            model=model,
            domain=domain,
            dataset_id=dataset_id,
            model_family=model_family,
            recall_context=recall_context,
            iteration_number=iteration_number,
            attempt_status="completed",
            exit_code=0,
            error=None,
        )

    def after_failure(
        self,
        *,
        project_dir: str | Path,
        run_id: str,
        task_id: str,
        query: str,
        model: str,
        domain: str,
        dataset_id: str,
        model_family: str,
        recall_context: RecallContext | None,
        iteration_number: int,
        error: Exception,
    ) -> LoopOutcome | None:
        failure = {
            "type": type(error).__name__,
            "message": str(error),
        }
        return self._record_result(
            {
                "task_id": task_id,
                "query": query,
                "analysis": f"The research attempt failed: {failure['type']}.",
                "metadata": {
                    "failure_hypothesis": {
                        "task_id": task_id,
                        "statement": query,
                        "conditions": [domain],
                    }
                },
            },
            project_dir=project_dir,
            run_id=run_id,
            model=model,
            domain=domain,
            dataset_id=dataset_id,
            model_family=model_family,
            recall_context=recall_context,
            iteration_number=iteration_number,
            attempt_status="failed",
            exit_code=1,
            error=failure,
        )

    def _record_result(
        self,
        flow_result: dict[str, Any],
        *,
        project_dir: str | Path,
        run_id: str,
        model: str,
        domain: str,
        dataset_id: str,
        model_family: str,
        recall_context: RecallContext | None,
        iteration_number: int,
        attempt_status: Literal["completed", "failed"],
        exit_code: int,
        error: dict[str, Any] | None,
    ) -> LoopOutcome | None:
        if not self.records_experience:
            return None
        assert self.loop is not None
        assert self.contract is not None

        project = Path(project_dir).resolve()
        project.mkdir(parents=True, exist_ok=True)
        refs = self._artifact_refs(project)
        artifact_time = self._artifact_time(refs)
        metadata = flow_result.get("metadata") or {}
        if "hypothesis" in metadata:
            hypothesis = Hypothesis.model_validate(metadata["hypothesis"])
        else:
            failure_hypothesis = metadata["failure_hypothesis"]
            hypothesis_payload = {
                "task_id": failure_hypothesis["task_id"],
                "statement": failure_hypothesis["statement"],
                "mechanism": "The attempted research execution did not complete.",
                "expected_metric": self.contract.primary_metric.name,
                "metric_direction": self.contract.primary_metric.direction,
                "conditions": failure_hypothesis["conditions"],
                "parent_experience_ids": sorted(
                    {
                        source_id
                        for item in (
                            recall_context.items if recall_context is not None else []
                        )
                        for source_id in item.source_experience_ids
                    }
                ),
                "citations": [
                    item.citation_id
                    for item in (
                        recall_context.items if recall_context is not None else []
                    )
                ],
            }
            hypothesis = Hypothesis(
                hypothesis_id=_digest(hypothesis_payload),
                created_at=artifact_time,
                **hypothesis_payload,
            )
        code_revision = _tree_digest(
            project,
            ignored_names={self.contract.result_file, "experience_observation.json"},
        )
        attempt_id = _digest(
            {
                "run_id": run_id,
                "iteration_number": iteration_number,
                "hypothesis_id": hypothesis.hypothesis_id,
                "code_revision": code_revision,
                "contract": f"{self.contract.contract_id}@{self.contract.version}",
                "recall": recall_context.snapshot_id if recall_context else "off",
                "status": attempt_status,
            }
        )
        attempt = ExperimentAttempt(
            attempt_id=attempt_id,
            run_id=run_id,
            iteration_id=f"{run_id}:{iteration_number}",
            task_id=hypothesis.task_id,
            hypothesis_id=hypothesis.hypothesis_id,
            code_revision=code_revision,
            dataset_id=dataset_id,
            dataset_digest=_digest(dataset_id),
            model_config_digest=_digest(model),
            seed=0,
            budget={"iterations": self.max_iterations},
            evaluation_contract_id=(
                f"{self.contract.contract_id}@{self.contract.version}"
            ),
            recall_snapshot_id=(
                recall_context.snapshot_id if recall_context is not None else "off"
            ),
            status=attempt_status,
            created_at=artifact_time,
        )
        observation_id = _digest(
            {
                "attempt_id": attempt_id,
                "artifacts": [
                    {"path": Path(ref.path).name, "sha256": ref.sha256}
                    for ref in refs
                ],
                "exit_code": exit_code,
                "error": error,
            }
        )
        observation = Observation(
            observation_id=observation_id,
            attempt_id=attempt_id,
            exit_code=exit_code,
            metrics=self._reported_metrics(project),
            artifact_refs=refs,
            started_at=artifact_time,
            completed_at=artifact_time,
            environment_fingerprint=(
                f"python={platform.python_version()};"
                f"platform={platform.system()}-{platform.machine()}"
            ),
            error=error,
        )
        analysis = self._analysis(flow_result)
        self.loop.knowledge_gate = KnowledgeGate(
            domain=domain,
            model_family=model_family,
        )
        outcome = self.loop.after_run(
            RunCompletion(
                hypothesis=hypothesis,
                attempt=attempt,
                observation=observation,
                analysis=analysis,
                iteration_number=iteration_number,
                max_iterations=self.max_iterations,
            )
        )
        self._write_json(
            self.cache_path / "experience_outcome.json",
            outcome.model_dump(mode="json"),
        )
        return outcome

    def finalize_runtime(
        self,
        *,
        run_id: str,
        outcome: LoopOutcome | None,
    ) -> None:
        if not self.records_experience:
            return
        check = self.verification_check(run_id)
        runtime = MasterRuntime(
            str(self.cache_path),
            require_verification_for_completion=True,
            verification_check=check,
        )
        verified = bool(check and check())
        if self.runs_closed_loop and outcome is not None:
            status = {
                "completed": "completed",
                "continue": "running",
                "failed_budget": "failed",
                "invalid": "failed",
                "unverified": "failed",
            }[outcome.action]
        else:
            status = "completed" if verified else "running"
        runtime.write_runtime_status(
            run_id=run_id,
            status=status,
            metadata={
                "experience_mode": self.mode,
                "verification_valid": verified,
                "loop_action": outcome.action if outcome is not None else None,
            },
        )

    def _artifact_refs(self, project: Path) -> list[ArtifactRef]:
        assert self.contract is not None
        refs = [
            _file_ref(project / relative)
            for relative in self.contract.required_artifacts
            if (project / relative).is_file()
        ]
        if refs:
            return refs
        fallback = project / "experience_observation.json"
        self._write_json(
            fallback,
            {"reason": "no required evaluator artifacts were produced"},
        )
        return [_file_ref(fallback)]

    @staticmethod
    def _artifact_time(refs: list[ArtifactRef]) -> datetime:
        timestamp = max(Path(ref.path).stat().st_mtime for ref in refs)
        return datetime.fromtimestamp(timestamp, timezone.utc)

    @staticmethod
    def _reported_metrics(project: Path) -> dict[str, float]:
        metrics_path = project / "metrics.json"
        if not metrics_path.is_file():
            return {}
        try:
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {
            str(name): float(value)
            for name, value in payload.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }

    @staticmethod
    def _analysis(flow_result: dict[str, Any]) -> str:
        analysis = flow_result.get("analysis")
        if isinstance(analysis, str) and analysis.strip():
            return analysis.strip()
        final_output = flow_result.get("final_output") or {}
        for key in ("submission_report", "judge_report", "plan_report"):
            value = final_output.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "The run produced evaluator artifacts without a narrative analysis."

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "payload": payload,
        }
        path = self.cache_path / "experience_events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if path.is_file() and path.read_text(encoding="utf-8") == content:
            return
        path.write_text(content, encoding="utf-8")
