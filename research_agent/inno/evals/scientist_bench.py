from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import time
from typing import Any, Literal, Protocol

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from research_agent.inno.evals.experience_benchmark import (
    ExperienceBenchmarkTask,
    TrialConfiguration,
    TrialResult,
)
from research_agent.inno.experience import (
    ArtifactRef,
    CommandVerifier,
    ContainerVerifier,
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
    VerificationRecord,
    load_evaluation_contract,
)


def _digest(value: Any) -> str:
    if not isinstance(value, str):
        value = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(path: Path, *, media_type: str) -> ArtifactRef:
    content = path.read_bytes()
    return ArtifactRef(
        path=str(path.resolve()),
        sha256=hashlib.sha256(content).hexdigest(),
        media_type=media_type,
        size_bytes=len(content),
    )


class CandidateGeneration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    solution_code: str
    analysis: str
    tokens: int = Field(default=0, ge=0)
    failure_kind: str | None = None
    cache_hit: bool = False


class CandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task: ExperienceBenchmarkTask
    configuration: TrialConfiguration
    interface_text: str
    recall: RecallContext
    iteration: int = Field(ge=1)


class SolutionGenerator(Protocol):
    @property
    def configuration_digest(self) -> str: ...

    def generate(self, request: CandidateRequest) -> CandidateGeneration: ...


class OpenAICompatibleSolutionGenerator:
    """Generate candidate code without participating in evaluation."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=180,
            max_retries=1,
        )
        self._cache: dict[str, CandidateGeneration] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    @property
    def configuration_digest(self) -> str:
        return _digest(
            {
                "adapter": type(self).__name__,
                "model": self.model,
                "base_url": self.base_url,
                "temperature": 0,
                "response_protocol": "tagged-or-fenced-candidate@2",
                "cache_policy": "identical-model-request@1",
            }
        )

    def generate(self, request: CandidateRequest) -> CandidateGeneration:
        if request.configuration.model != self.model:
            raise ValueError(
                "trial model does not match solution generator configuration"
            )
        evidence = "\n".join(
            (
                f"- [{item.citation_id}] outcome={item.outcome}; "
                f"lesson={item.lesson}"
            )
            for item in request.recall.items
        )
        if not evidence:
            evidence = "- No verified experience is available."
        messages = [
            {
                "role": "system",
                "content": (
                    "Implement the requested scientific method as one "
                    "standard-library-only Python file. Follow the candidate "
                    "interface exactly. Do not import third-party packages such "
                    "as NumPy or SciPy. Prefer a concise implementation under "
                    "200 lines. Verified feedback may identify behavior "
                    "categories but never reveals hidden cases. Return code "
                    "only in the tagged format below; do not claim your own "
                    "score. The candidate Interface overrides third-party "
                    "examples in the task description. When negative verified "
                    "experience is supplied, correct every listed failure and "
                    "do not repeat its failed rationale.\n"
                    "<analysis>brief rationale</analysis>\n"
                    "<solution>complete solution.py code</solution>"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Task:\n{request.task.query}\n\n"
                    f"Candidate interface:\n{request.interface_text}\n\n"
                    f"Verified experience:\n{evidence}\n\n"
                    f"Paired seed: {request.configuration.seed}\n"
                    f"Iteration: {request.iteration}\n"
                    "Produce a complete solution.py implementation."
                ),
            },
        ]
        max_tokens = int(request.configuration.budget.get("generation_tokens", 4000))
        cache_key = _digest(
            {
                "model": self.model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": max_tokens,
                "protocol": "tagged-or-fenced-candidate@2",
            }
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            self.cache_hits += 1
            return cached.model_copy(update={"cache_hit": True})
        self.cache_misses += 1
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
            max_tokens=max_tokens,
        )
        message = response.choices[0].message
        content = message.content or ""
        analysis_match = re.search(
            r"<analysis>(?P<value>.*?)</analysis>",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        solution_match = re.search(
            r"<solution>(?P<value>.*?)</solution>",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        fenced_match = re.search(
            r"```(?:python)?\s*\n(?P<value>.*?)\n```",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if solution_match is not None:
            solution_code = solution_match.group("value").strip()
        elif fenced_match is not None:
            solution_code = fenced_match.group("value").strip()
        elif "def " in content:
            solution_code = content.strip()
        else:
            raise ValueError("model response contains no candidate Python code")
        usage = response.usage
        tokens = (
            (usage.prompt_tokens or 0) + (usage.completion_tokens or 0)
            if usage is not None
            else 0
        )
        generation = CandidateGeneration(
            solution_code=solution_code,
            analysis=(
                analysis_match.group("value").strip()
                if analysis_match is not None
                else "No rationale supplied."
            ),
            tokens=tokens,
        )
        self._cache[cache_key] = generation
        return generation


class VerifiedTrialManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = "1"
    task_id: str
    mode: Literal["off", "closed-loop"]
    seed: int
    model: str
    budget: dict[str, float | int]
    evaluator_contract_id: str
    evaluator_contract_version: str
    evaluator_contract_digest: str
    evaluator_digest: str
    evaluator_container_image: str
    task_source_digest: str
    interface_digest: str
    dataset_digest: str
    code_revision: str
    generator_configuration_digest: str
    cache_policy: Literal[
        "fresh-ledger-per-trial;identical-model-request-cache"
    ] = "fresh-ledger-per-trial;identical-model-request-cache"
    score_selection_policy: Literal["best-valid-primary-metric"] = (
        "best-valid-primary-metric"
    )

    @property
    def manifest_digest(self) -> str:
        return _digest(self.model_dump(mode="json"))

    @property
    def comparison_digest(self) -> str:
        payload = self.model_dump(mode="json")
        payload.pop("mode")
        return _digest(payload)


class ScientistBenchTrialAdapter:
    """Own one verified scientific trial behind the generic TrialFn Interface."""

    def __init__(
        self,
        output_root: str | Path,
        *,
        task: ExperienceBenchmarkTask,
        evaluator_root: str | Path,
        contract_path: str | Path,
        interface_path: str | Path,
        generator: SolutionGenerator,
        domain: str,
        verifier: CommandVerifier | None = None,
    ) -> None:
        self.output_root = Path(output_root)
        self.task = task
        self.evaluator_root = Path(evaluator_root).resolve()
        self.contract_path = Path(contract_path).resolve()
        self.interface_path = Path(interface_path).resolve()
        self.generator = generator
        self.domain = domain
        self.contract = load_evaluation_contract(self.contract_path)
        self.interface_text = self.interface_path.read_text(encoding="utf-8")
        self.verifier = verifier or ContainerVerifier(
            contract_dir=self.evaluator_root
        )
        if self.contract.task_id != self.task.task_id:
            raise ValueError("task and evaluation contract IDs do not match")

    def __call__(self, config: TrialConfiguration) -> TrialResult:
        started = time.monotonic()
        self._validate_configuration(config)
        manifest = self._manifest(config)
        trial_root = (
            self.output_root
            / config.task_id
            / config.mode
            / f"seed-{config.seed}"
        )
        trial_root.mkdir(parents=True, exist_ok=False)
        ledger = SQLiteExperimentLedger(trial_root / "experience.sqlite3")
        loop = ExperienceLoop(
            ledger=ledger,
            retriever=KeywordExperienceRetriever(ledger),
            verifier=self.verifier,
            knowledge_gate=KnowledgeGate(
                domain=self.domain,
                model_family=config.model,
            ),
            evaluation_contract=self.contract,
            mode="closed-loop" if config.mode == "closed-loop" else "record",
        )

        total_tokens = 0
        solution_digests: list[str] = []
        generation_failures: list[str] = []
        trajectory: list[
            tuple[int, VerificationRecord, ExperimentAttempt, RecallContext]
        ] = []
        max_iterations = int(config.budget["iterations"])
        for iteration in range(1, max_iterations + 1):
            recall = loop.before_run(
                RecallRequest(
                    query=self.task.query,
                    task_id=config.task_id,
                    domain=self.domain,
                    dataset_id=config.dataset_digest,
                    model_family=config.model,
                    max_items=int(config.budget.get("recall_items", 6)),
                    token_budget=int(config.budget.get("recall_tokens", 2500)),
                    include_negative=True,
                )
            )
            generation = self._generate(config, recall, iteration)
            total_tokens += generation.tokens
            if generation.failure_kind:
                generation_failures.append(generation.failure_kind)
            solution_code = self._normalize_solution(generation.solution_code)
            solution_digest = _digest(solution_code)
            solution_digests.append(solution_digest)

            attempt_dir = trial_root / f"attempt-{iteration}"
            attempt_dir.mkdir()
            solution_path = attempt_dir / "solution.py"
            solution_path.write_text(solution_code + "\n", encoding="utf-8")
            manifest_path = attempt_dir / "trial_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    manifest.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            log_path = attempt_dir / "run.log"
            log_path.write_text(
                json.dumps(
                    {
                        "iteration": iteration,
                        "mode": config.mode,
                        "seed": config.seed,
                        "recall_snapshot_id": recall.snapshot_id,
                        "citations": [item.citation_id for item in recall.items],
                        "solution_digest": solution_digest,
                        "candidate_generation_failure": generation.failure_kind,
                        "candidate_generation_cache_hit": generation.cache_hit,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
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
                "statement": (
                    f"Candidate {solution_digest[:12]} conforms to "
                    f"{self.contract.contract_id}@{self.contract.version}."
                ),
                "mechanism": generation.analysis.strip()
                or "Implement the public candidate Interface.",
                "expected_metric": self.contract.primary_metric.name,
                "metric_direction": self.contract.primary_metric.direction,
                "conditions": [
                    "fixed evaluator digest",
                    "fixed paired seed and budget",
                    "CPU functional-conformance scope",
                ],
                "parent_experience_ids": parent_ids,
                "citations": [item.citation_id for item in recall.items],
            }
            hypothesis = Hypothesis(
                hypothesis_id=_digest(
                    {
                        **hypothesis_payload,
                        "manifest": manifest.manifest_digest,
                        "iteration": iteration,
                        "solution": solution_digest,
                    }
                ),
                created_at=now,
                **hypothesis_payload,
            )
            attempt = ExperimentAttempt(
                attempt_id=_digest(
                    {
                        "manifest": manifest.manifest_digest,
                        "iteration": iteration,
                        "solution": solution_digest,
                        "recall": recall.snapshot_id,
                    }
                ),
                run_id=f"{config.task_id}:{config.mode}:{config.seed}",
                iteration_id=f"{config.mode}:{config.seed}:{iteration}",
                task_id=config.task_id,
                hypothesis_id=hypothesis.hypothesis_id,
                code_revision=solution_digest,
                dataset_id=config.dataset_digest,
                dataset_digest=config.dataset_digest,
                model_config_digest=self.generator.configuration_digest,
                seed=config.seed,
                budget=config.budget,
                evaluation_contract_id=(
                    f"{self.contract.contract_id}@{self.contract.version}"
                ),
                recall_snapshot_id=recall.snapshot_id,
                status="completed",
                created_at=now,
            )
            refs = [
                _artifact(solution_path, media_type="text/x-python"),
                _artifact(log_path, media_type="application/json"),
                _artifact(manifest_path, media_type="application/json"),
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
                    f"platform={platform.system()}-{platform.machine()};"
                    f"container={self.contract.container_image}"
                ),
            )
            outcome = loop.after_run(
                RunCompletion(
                    hypothesis=hypothesis,
                    attempt=attempt,
                    observation=observation,
                    analysis=(
                        f"Candidate rationale: {generation.analysis.strip() or 'none'}"
                    ),
                    iteration_number=iteration,
                    max_iterations=max_iterations,
                )
            )
            if outcome.verification is None:
                raise RuntimeError("recording mode did not produce verification")
            trajectory.append((iteration, outcome.verification, attempt, recall))
            if outcome.action == "completed":
                break

        selected_iteration, selected_verification, selected_attempt, selected_recall = (
            self._select_best_verified(trajectory)
        )
        metric_name = self.contract.primary_metric.name
        score = selected_verification.verified_metrics.get(metric_name, 0.0)
        evidence = selected_verification.evidence_refs
        failure_signature = self._failure_signature(
            selected_verification.valid,
            selected_verification.passed,
            selected_verification.violations,
            selected_verification.public_feedback,
            solution_digests,
            generation_failures,
        )
        return TrialResult(
            score=score,
            valid=selected_verification.valid,
            tokens=total_tokens,
            wall_seconds=time.monotonic() - started,
            failure_signature=failure_signature,
            artifact_refs=[ref.path for ref in evidence],
            artifact_digests={Path(ref.path).name: ref.sha256 for ref in evidence},
            score_source="verification_record",
            verification_id=selected_verification.verification_id,
            verification_ids=[
                verification.verification_id
                for _, verification, _, _ in trajectory
            ],
            attempt_id=selected_attempt.attempt_id,
            attempt_ids=[attempt.attempt_id for _, _, attempt, _ in trajectory],
            selected_iteration=selected_iteration,
            recall_snapshot_id=selected_recall.snapshot_id,
            manifest_digest=manifest.manifest_digest,
            comparison_digest=manifest.comparison_digest,
            evaluator_digest=selected_verification.evaluator_digest,
        )

    def _select_best_verified(
        self,
        trajectory: list[
            tuple[int, VerificationRecord, ExperimentAttempt, RecallContext]
        ],
    ) -> tuple[int, VerificationRecord, ExperimentAttempt, RecallContext]:
        if not trajectory:
            raise RuntimeError("trial produced no verified trajectory")
        metric_name = self.contract.primary_metric.name
        valid = [
            item
            for item in trajectory
            if item[1].valid and metric_name in item[1].verified_metrics
        ]
        if not valid:
            return trajectory[-1]
        reverse = self.contract.primary_metric.direction == "maximize"
        return sorted(
            valid,
            key=lambda item: (
                item[1].verified_metrics[metric_name],
                -item[0] if reverse else item[0],
            ),
            reverse=reverse,
        )[0]

    def _validate_configuration(self, config: TrialConfiguration) -> None:
        if config.task_id != self.task.task_id:
            raise ValueError("trial configuration task does not match Adapter task")
        expected_version = f"{self.contract.contract_id}@{self.contract.version}"
        if config.evaluator_version != expected_version:
            raise ValueError(
                f"evaluator version must be {expected_version!r}, "
                f"got {config.evaluator_version!r}"
            )
        iterations = config.budget.get("iterations")
        if not isinstance(iterations, int) or iterations < 1:
            raise ValueError("trial budget requires a positive integer iterations")

    def _manifest(self, config: TrialConfiguration) -> VerifiedTrialManifest:
        task_source_digest = self.task.metadata.get("source_digest")
        if not isinstance(task_source_digest, str):
            task_source_digest = _digest(
                {
                    "task_id": self.task.task_id,
                    "query": self.task.query,
                    "goal": self.task.goal,
                }
            )
        return VerifiedTrialManifest(
            task_id=config.task_id,
            mode=config.mode,
            seed=config.seed,
            model=config.model,
            budget=config.budget,
            evaluator_contract_id=self.contract.contract_id,
            evaluator_contract_version=self.contract.version,
            evaluator_contract_digest=_file_digest(self.contract_path),
            evaluator_digest=self.verifier.evaluator_digest(self.contract),
            evaluator_container_image=self.contract.container_image or "",
            task_source_digest=task_source_digest,
            interface_digest=_file_digest(self.interface_path),
            dataset_digest=config.dataset_digest,
            code_revision=config.code_revision,
            generator_configuration_digest=self.generator.configuration_digest,
        )

    def _generate(
        self,
        config: TrialConfiguration,
        recall: RecallContext,
        iteration: int,
    ) -> CandidateGeneration:
        try:
            return self.generator.generate(
                CandidateRequest(
                    task=self.task,
                    configuration=config,
                    interface_text=self.interface_text,
                    recall=recall,
                    iteration=iteration,
                )
            )
        except Exception as exc:
            return CandidateGeneration(
                solution_code=(
                    "def assign_noise(*args, **kwargs):\n"
                    f"    raise RuntimeError({type(exc).__name__!r})\n"
                    "def quantize(*args, **kwargs):\n"
                    f"    raise RuntimeError({type(exc).__name__!r})\n"
                    "def codes_to_index(*args, **kwargs):\n"
                    f"    raise RuntimeError({type(exc).__name__!r})\n"
                    "def index_to_codes(*args, **kwargs):\n"
                    f"    raise RuntimeError({type(exc).__name__!r})\n"
                ),
                analysis=f"candidate_generation_failed:{type(exc).__name__}",
                failure_kind=type(exc).__name__,
            )

    @staticmethod
    def _normalize_solution(solution: str) -> str:
        normalized = solution.strip()
        fenced = re.fullmatch(
            r"```(?:python)?\s*\n(?P<code>.*)\n```",
            normalized,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if fenced:
            normalized = fenced.group("code").strip()
        elif normalized.lower().startswith(("```python\n", "```\n")):
            normalized = normalized.split("\n", 1)[1]
            if normalized.rstrip().endswith("```"):
                normalized = normalized.rstrip()[:-3]
            normalized = normalized.strip()
        if not normalized or "\x00" in normalized:
            raise ValueError("candidate solution is empty or malformed")
        if len(normalized) > 100_000:
            raise ValueError("candidate solution exceeds 100,000 characters")
        return normalized

    @staticmethod
    def _failure_signature(
        valid: bool,
        passed: bool,
        violations: list[str],
        public_feedback: list[str],
        solution_digests: list[str],
        generation_failures: list[str],
    ) -> str | None:
        if passed:
            return None
        if not valid:
            return "invalid:" + _digest(sorted(violations))[:16]
        if generation_failures:
            return "candidate-generation:" + _digest(generation_failures)[:16]
        if len(solution_digests) > 1 and len(set(solution_digests)) == 1:
            return "repeated-candidate:" + solution_digests[-1][:16]
        return "verified-negative:" + _digest(sorted(public_feedback))[:16]
