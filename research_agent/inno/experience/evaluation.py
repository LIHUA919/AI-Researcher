from __future__ import annotations

import hashlib
import inspect
import json
import math
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator
import yaml

from research_agent.inno.experience.models import (
    ArtifactRef,
    Observation,
    VerificationRecord,
)


class EvaluationError(RuntimeError):
    """Raised when an evaluator cannot produce a trustworthy result."""


class PrimaryMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    direction: Literal["maximize", "minimize"]


class ValidityRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    require_finite_metrics: bool = True
    max_failed_repetitions: int = Field(default=0, ge=0)
    max_public_feedback_items: int = Field(default=8, ge=0, le=100)
    max_public_feedback_chars: int = Field(default=4000, ge=0, le=100_000)


class EvaluationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    contract_id: str
    version: str = "1"
    task_id: str
    entrypoint: str | None = None
    result_file: str = "verification_result.json"
    timeout_seconds: float = Field(default=900, gt=0)
    repetitions: int = Field(default=1, ge=1)
    required_artifacts: list[str] = Field(default_factory=list)
    primary_metric: PrimaryMetric
    baseline: float
    validity: ValidityRules = Field(default_factory=ValidityRules)
    private_data_dir: str | None = None
    container_image: str | None = None

    @field_validator("result_file")
    @classmethod
    def validate_result_file(cls, value: str) -> str:
        return cls._validate_artifact_name(value, field_name="result_file")

    @field_validator("required_artifacts")
    @classmethod
    def validate_required_artifacts(cls, values: list[str]) -> list[str]:
        normalized = [
            cls._validate_artifact_name(value, field_name="required_artifacts")
            for value in values
        ]
        if len(normalized) != len(set(normalized)):
            raise ValueError("required_artifacts must not contain duplicates")
        return normalized

    @staticmethod
    def _validate_artifact_name(value: str, *, field_name: str) -> str:
        candidate = value.strip()
        if (
            not candidate
            or candidate in {".", ".."}
            or "/" in candidate
            or "\\" in candidate
        ):
            raise ValueError(f"{field_name} entries must be plain file names")
        return candidate


EvaluatorFn = Callable[[EvaluationContract, Observation], dict[str, Any]]
_PINNED_IMAGE_PATTERN = re.compile(r".+@sha256:[0-9a-f]{64}\Z", re.IGNORECASE)


class Verifier(Protocol):
    def verify(
        self,
        contract: EvaluationContract,
        observation: Observation,
    ) -> VerificationRecord: ...


def load_evaluation_contract(path: str | Path) -> EvaluationContract:
    contract_path = Path(path)
    try:
        payload = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise EvaluationError(f"cannot load evaluation contract: {contract_path}") from exc
    if not isinstance(payload, dict):
        raise EvaluationError(f"evaluation contract must be a mapping: {contract_path}")
    return EvaluationContract.model_validate(payload)


def _digest_callable(evaluator: EvaluatorFn) -> str:
    try:
        source = inspect.getsource(evaluator)
    except (OSError, TypeError):
        source = repr(evaluator)
    identity = f"{evaluator.__module__}:{evaluator.__qualname__}\n{source}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _artifact_names(observation: Observation) -> set[str]:
    return {Path(ref.path).name for ref in observation.artifact_refs}


def _artifact_integrity_violations(observation: Observation) -> list[str]:
    violations: list[str] = []
    seen_names: set[str] = set()
    for ref in observation.artifact_refs:
        path = Path(ref.path)
        if path.name in seen_names:
            violations.append(f"duplicate_artifact_name:{path.name}")
            continue
        seen_names.add(path.name)
        try:
            content = path.read_bytes()
        except OSError:
            violations.append(f"artifact_unreadable:{path.name}")
            continue
        if hashlib.sha256(content).hexdigest() != ref.sha256:
            violations.append(f"artifact_digest_mismatch:{path.name}")
        if len(content) != ref.size_bytes:
            violations.append(f"artifact_size_mismatch:{path.name}")
    return violations


def _verification_from_result(
    *,
    contract: EvaluationContract,
    observation: Observation,
    evaluator_digest: str,
    result: dict[str, Any],
    evaluator_violations: list[str] | None = None,
    additional_evidence_refs: list[ArtifactRef] | None = None,
) -> VerificationRecord:
    violations = list(evaluator_violations or [])
    metrics_value = result.get("metrics", {})
    if not isinstance(metrics_value, dict):
        metrics_value = {}
        violations.append("metrics_not_mapping")

    metrics: dict[str, float] = {}
    for name, value in metrics_value.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            violations.append(f"metric_not_numeric:{name}")
            continue
        numeric = float(value)
        if contract.validity.require_finite_metrics and not math.isfinite(numeric):
            violations.append(f"metric_not_finite:{name}")
            continue
        metrics[str(name)] = numeric

    public_feedback_value = result.get("public_feedback", [])
    public_feedback: list[str] = []
    if not isinstance(public_feedback_value, list) or any(
        not isinstance(item, str) for item in public_feedback_value
    ):
        violations.append("public_feedback_not_string_list")
    else:
        public_feedback = [
            item.strip() for item in public_feedback_value if item.strip()
        ]
        if len(public_feedback) > contract.validity.max_public_feedback_items:
            violations.append("too_many_public_feedback_items")
        if (
            sum(len(item) for item in public_feedback)
            > contract.validity.max_public_feedback_chars
        ):
            violations.append("public_feedback_too_large")

    primary_name = contract.primary_metric.name
    if primary_name not in metrics:
        violations.append(f"missing_primary_metric:{primary_name}")

    missing_artifacts = sorted(
        set(contract.required_artifacts) - _artifact_names(observation)
    )
    violations.extend(f"missing_artifact:{name}" for name in missing_artifacts)

    failed_repetitions = result.get("failed_repetitions", 0)
    if not isinstance(failed_repetitions, int) or failed_repetitions < 0:
        violations.append("invalid_failed_repetitions")
    elif failed_repetitions > contract.validity.max_failed_repetitions:
        violations.append("too_many_failed_repetitions")
    completed_repetitions = result.get("repetitions")
    if completed_repetitions != contract.repetitions:
        violations.append("repetition_count_mismatch")

    valid = not violations
    metric_value = metrics.get(primary_name)
    delta = 0.0
    passed = False
    outcome: Literal["positive", "neutral", "negative", "invalid"] = "invalid"
    if valid and metric_value is not None:
        if contract.primary_metric.direction == "maximize":
            delta = metric_value - contract.baseline
        else:
            delta = contract.baseline - metric_value
        passed = delta > 0
        outcome = "positive" if delta > 0 else "negative" if delta < 0 else "neutral"

    canonical_result = json.dumps(
        {
            "observation_id": observation.observation_id,
            "contract_id": contract.contract_id,
            "contract_version": contract.version,
            "evaluator_digest": evaluator_digest,
            "metrics": metrics,
            "public_feedback": public_feedback,
            "violations": violations,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    verification_id = hashlib.sha256(canonical_result.encode("utf-8")).hexdigest()

    return VerificationRecord(
        verification_id=verification_id,
        observation_id=observation.observation_id,
        contract_id=contract.contract_id,
        contract_version=contract.version,
        evaluator_digest=evaluator_digest,
        valid=valid,
        passed=passed,
        outcome=outcome,
        verified_metrics=metrics,
        baseline_comparison={
            "metric": primary_name,
            "baseline": contract.baseline,
            "value": metric_value if metric_value is not None else "missing",
            "delta": delta,
            "direction": contract.primary_metric.direction,
        },
        violations=violations,
        public_feedback=public_feedback,
        evidence_refs=[*observation.artifact_refs, *(additional_evidence_refs or [])],
        created_at=observation.completed_at,
    )


class CallableVerifier:
    def __init__(self, evaluator: EvaluatorFn) -> None:
        self.evaluator = evaluator
        self.evaluator_digest = _digest_callable(evaluator)

    def verify(
        self,
        contract: EvaluationContract,
        observation: Observation,
    ) -> VerificationRecord:
        try:
            result = self.evaluator(contract, observation)
        except Exception as exc:
            return _verification_from_result(
                contract=contract,
                observation=observation,
                evaluator_digest=self.evaluator_digest,
                result={},
                evaluator_violations=[f"evaluator_error:{type(exc).__name__}"],
            )
        if not isinstance(result, dict):
            result = {}
            violations = ["evaluator_result_not_mapping"]
        else:
            violations = []
        return _verification_from_result(
            contract=contract,
            observation=observation,
            evaluator_digest=self.evaluator_digest,
            result=result,
            evaluator_violations=violations,
        )


class CommandVerifier:
    def __init__(self, *, contract_dir: str | Path, private_root: str | Path | None = None) -> None:
        self.contract_dir = Path(contract_dir).resolve()
        self.private_root = Path(private_root).resolve() if private_root else None

    def _evaluator_digest(self, contract: EvaluationContract) -> str:
        digest = hashlib.sha256()
        digest.update((contract.entrypoint or "").encode("utf-8"))
        for candidate in sorted(self.contract_dir.rglob("*")):
            if (
                not candidate.is_file()
                or candidate.is_symlink()
                or "__pycache__" in candidate.parts
                or candidate.suffix in {".pyc", ".pyo"}
            ):
                continue
            relative = candidate.relative_to(self.contract_dir).as_posix()
            digest.update(b"\0")
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(hashlib.sha256(candidate.read_bytes()).digest())
        return digest.hexdigest()

    def evaluator_digest(self, contract: EvaluationContract) -> str:
        """Return the immutable identity of evaluator code and runtime inputs."""
        return self._evaluator_digest(contract)

    def verify(
        self,
        contract: EvaluationContract,
        observation: Observation,
    ) -> VerificationRecord:
        evaluator_digest = self._evaluator_digest(contract)
        attempt_dir = self._attempt_dir(observation)
        integrity_violations = _artifact_integrity_violations(observation)
        if integrity_violations:
            return _verification_from_result(
                contract=contract,
                observation=observation,
                evaluator_digest=evaluator_digest,
                result={},
                evaluator_violations=integrity_violations,
            )
        if not contract.entrypoint:
            return _verification_from_result(
                contract=contract,
                observation=observation,
                evaluator_digest=evaluator_digest,
                result={},
                evaluator_violations=["missing_evaluator_entrypoint"],
            )

        private_data_dir = ""
        if contract.private_data_dir:
            if self.private_root is None:
                return _verification_from_result(
                    contract=contract,
                    observation=observation,
                    evaluator_digest=evaluator_digest,
                    result={},
                    evaluator_violations=["private_data_root_not_configured"],
                )
            private_data_dir = str(
                (self.private_root / contract.private_data_dir).resolve()
            )
            resolved_private = Path(private_data_dir)
            if (
                resolved_private != self.private_root
                and self.private_root not in resolved_private.parents
            ):
                return _verification_from_result(
                    contract=contract,
                    observation=observation,
                    evaluator_digest=evaluator_digest,
                    result={},
                    evaluator_violations=["private_data_outside_root"],
                )

        command = [
            token.format(
                attempt_dir=str(attempt_dir),
                private_data_dir=private_data_dir,
            )
            for token in shlex.split(contract.entrypoint)
        ]
        if command and command[0] in {"python", "python3"}:
            command[0] = sys.executable
        try:
            completed = subprocess.run(
                command,
                cwd=self.contract_dir,
                capture_output=True,
                text=True,
                timeout=contract.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _verification_from_result(
                contract=contract,
                observation=observation,
                evaluator_digest=evaluator_digest,
                result={},
                evaluator_violations=["evaluator_timeout"],
            )
        except OSError as exc:
            return _verification_from_result(
                contract=contract,
                observation=observation,
                evaluator_digest=evaluator_digest,
                result={},
                evaluator_violations=[f"evaluator_start_error:{type(exc).__name__}"],
            )

        violations: list[str] = []
        if completed.returncode != 0:
            violations.append(f"evaluator_exit_code:{completed.returncode}")
        result_path = attempt_dir / contract.result_file
        try:
            result_bytes = result_path.read_bytes()
            result = json.loads(result_bytes)
            result_ref = ArtifactRef(
                path=str(result_path),
                sha256=hashlib.sha256(result_bytes).hexdigest(),
                media_type="application/json",
                size_bytes=len(result_bytes),
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            result = {}
            result_ref = None
            violations.append("missing_or_invalid_result_file")
        if not isinstance(result, dict):
            result = {}
            violations.append("evaluator_result_not_mapping")

        return _verification_from_result(
            contract=contract,
            observation=observation,
            evaluator_digest=evaluator_digest,
            result=result,
            evaluator_violations=violations,
            additional_evidence_refs=[result_ref] if result_ref is not None else [],
        )

    @staticmethod
    def _attempt_dir(observation: Observation) -> Path:
        if not observation.artifact_refs:
            raise EvaluationError("observation has no artifact references")
        paths = [Path(ref.path).resolve() for ref in observation.artifact_refs]
        common = Path(paths[0]).parent
        if any(path.parent != common for path in paths[1:]):
            raise EvaluationError("observation artifacts must share one attempt directory")
        return common


class ContainerVerifier(CommandVerifier):
    """Run an evaluator in a networkless, read-only Docker sandbox."""

    def __init__(
        self,
        *,
        contract_dir: str | Path,
        image: str | None = None,
        private_root: str | Path | None = None,
        docker_binary: str = "docker",
        memory_limit: str = "2g",
        cpu_limit: str = "2",
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        super().__init__(contract_dir=contract_dir, private_root=private_root)
        self.image = image
        self.docker_binary = docker_binary
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.runner = runner

    def _evaluator_digest(self, contract: EvaluationContract) -> str:
        command_digest = super()._evaluator_digest(contract)
        image = contract.container_image or self.image or ""
        return hashlib.sha256(f"{image}\n{command_digest}".encode("utf-8")).hexdigest()

    def verify(
        self,
        contract: EvaluationContract,
        observation: Observation,
    ) -> VerificationRecord:
        evaluator_digest = self._evaluator_digest(contract)
        image = contract.container_image or self.image
        if not image:
            return _verification_from_result(
                contract=contract,
                observation=observation,
                evaluator_digest=evaluator_digest,
                result={},
                evaluator_violations=["missing_evaluator_container_image"],
            )
        if _PINNED_IMAGE_PATTERN.fullmatch(image) is None:
            return _verification_from_result(
                contract=contract,
                observation=observation,
                evaluator_digest=evaluator_digest,
                result={},
                evaluator_violations=["evaluator_container_image_not_pinned"],
            )
        if not contract.entrypoint:
            return _verification_from_result(
                contract=contract,
                observation=observation,
                evaluator_digest=evaluator_digest,
                result={},
                evaluator_violations=["missing_evaluator_entrypoint"],
            )
        integrity_violations = _artifact_integrity_violations(observation)
        if integrity_violations:
            return _verification_from_result(
                contract=contract,
                observation=observation,
                evaluator_digest=evaluator_digest,
                result={},
                evaluator_violations=integrity_violations,
            )
        attempt_dir = self._attempt_dir(observation)
        if (
            attempt_dir == self.contract_dir
            or self.contract_dir in attempt_dir.parents
        ):
            return _verification_from_result(
                contract=contract,
                observation=observation,
                evaluator_digest=evaluator_digest,
                result={},
                evaluator_violations=["attempt_inside_evaluator_contract"],
            )
        private_mount = self._private_mount(contract)
        if isinstance(private_mount, str):
            return _verification_from_result(
                contract=contract,
                observation=observation,
                evaluator_digest=evaluator_digest,
                result={},
                evaluator_violations=[private_mount],
            )
        if any(path.is_symlink() for path in self.contract_dir.rglob("*")):
            return _verification_from_result(
                contract=contract,
                observation=observation,
                evaluator_digest=evaluator_digest,
                result={},
                evaluator_violations=["evaluator_contract_contains_symlink"],
            )

        with tempfile.TemporaryDirectory(
            prefix=".ai-researcher-evaluator-",
            dir=attempt_dir.parent,
        ) as temp_dir:
            isolated_evaluator = Path(temp_dir) / "evaluator"
            shutil.copytree(self.contract_dir, isolated_evaluator)
            self._make_root_only(isolated_evaluator)
            isolated_attempt = Path(temp_dir) / "attempt"
            isolated_attempt.mkdir()
            for ref in observation.artifact_refs:
                shutil.copy2(ref.path, isolated_attempt / Path(ref.path).name)
            isolated_private: Path | None = None
            if private_mount is not None:
                isolated_private = Path(temp_dir) / "private"
                shutil.copytree(private_mount, isolated_private)
                self._make_root_only(isolated_private)

            evaluator_command = [
                token.format(
                    attempt_dir="/attempt",
                    private_data_dir="/private" if private_mount else "",
                )
                for token in shlex.split(contract.entrypoint)
            ]
            run_command = [
                self.docker_binary,
                "run",
                "--rm",
                "--pull",
                "never",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--cap-add",
                "SETUID",
                "--cap-add",
                "SETGID",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "128",
                "--memory",
                self.memory_limit,
                "--cpus",
                self.cpu_limit,
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=64m",
                "--mount",
                f"type=bind,src={isolated_attempt},dst=/attempt",
                "--workdir",
                "/evaluator",
            ]
            if isolated_private is not None:
                run_command.extend(
                    [
                        "--mount",
                        f"type=bind,src={isolated_private},dst=/private,readonly",
                    ]
                )
            run_command.extend([image, *evaluator_command])
            evaluator_volume: str | None = None
            try:
                volume_result = self.runner(
                    [self.docker_binary, "volume", "create"],
                    capture_output=True,
                    text=True,
                    timeout=contract.timeout_seconds,
                    check=False,
                )
                if volume_result.returncode != 0:
                    completed = volume_result
                else:
                    evaluator_volume = volume_result.stdout.strip()
                    if not evaluator_volume:
                        raise OSError("docker volume create returned no volume name")
                    populated = self.runner(
                        [
                            self.docker_binary,
                            "run",
                            "--rm",
                            "--pull",
                            "never",
                            "--network",
                            "none",
                            "--mount",
                            (
                                f"type=bind,src={isolated_evaluator},"
                                "dst=/source,readonly"
                            ),
                            "--mount",
                            (
                                f"type=volume,src={evaluator_volume},"
                                "dst=/evaluator"
                            ),
                            image,
                            "sh",
                            "-c",
                            (
                                "cp -a /source/. /evaluator/ && "
                                "chown -R 0:0 /evaluator && "
                                "find /evaluator -type d -exec chmod 700 {} + && "
                                "find /evaluator -type f -exec chmod 600 {} +"
                            ),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=contract.timeout_seconds,
                        check=False,
                    )
                    if populated.returncode != 0:
                        completed = populated
                    else:
                        evaluator_mount = (
                            f"type=volume,src={evaluator_volume},"
                            "dst=/evaluator,readonly"
                        )
                        run_command[
                            run_command.index("--workdir") : run_command.index(
                                "--workdir"
                            )
                        ] = ["--mount", evaluator_mount]
                        completed = self.runner(
                            run_command,
                            capture_output=True,
                            text=True,
                            timeout=contract.timeout_seconds,
                            check=False,
                        )
            except subprocess.TimeoutExpired:
                return _verification_from_result(
                    contract=contract,
                    observation=observation,
                    evaluator_digest=evaluator_digest,
                    result={},
                    evaluator_violations=["evaluator_timeout"],
                )
            except OSError as exc:
                return _verification_from_result(
                    contract=contract,
                    observation=observation,
                    evaluator_digest=evaluator_digest,
                    result={},
                    evaluator_violations=[
                        f"evaluator_container_start_error:{type(exc).__name__}"
                    ],
                )
            finally:
                if evaluator_volume:
                    self.runner(
                        [
                            self.docker_binary,
                            "volume",
                            "rm",
                            "--force",
                            evaluator_volume,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )

            violations: list[str] = []
            if completed.returncode != 0:
                stderr = completed.stderr.lower()
                if completed.returncode == 125 and (
                    "no such image" in stderr or "unable to find image" in stderr
                ):
                    violations.append("evaluator_image_unavailable")
                else:
                    violations.append(f"evaluator_exit_code:{completed.returncode}")
            isolated_result = isolated_attempt / contract.result_file
            destination_result = attempt_dir / contract.result_file
            try:
                result_bytes = isolated_result.read_bytes()
                result = json.loads(result_bytes)
                destination_result.write_bytes(result_bytes)
                result_ref = ArtifactRef(
                    path=str(destination_result),
                    sha256=hashlib.sha256(result_bytes).hexdigest(),
                    media_type="application/json",
                    size_bytes=len(result_bytes),
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                result = {}
                result_ref = None
                violations.append("missing_or_invalid_result_file")
            if not isinstance(result, dict):
                result = {}
                violations.append("evaluator_result_not_mapping")
            return _verification_from_result(
                contract=contract,
                observation=observation,
                evaluator_digest=evaluator_digest,
                result=result,
                evaluator_violations=violations,
                additional_evidence_refs=(
                    [result_ref] if result_ref is not None else []
                ),
            )

    @staticmethod
    def _make_root_only(root: Path) -> None:
        for path in sorted(root.rglob("*"), reverse=True):
            path.chmod(0o700 if path.is_dir() else 0o600)
        root.chmod(0o700)

    def _private_mount(self, contract: EvaluationContract) -> Path | str | None:
        if not contract.private_data_dir:
            return None
        if self.private_root is None:
            return "private_data_root_not_configured"
        resolved = (self.private_root / contract.private_data_dir).resolve()
        if resolved != self.private_root and self.private_root not in resolved.parents:
            return "private_data_outside_root"
        if not resolved.is_dir():
            return "private_data_directory_missing"
        return resolved
