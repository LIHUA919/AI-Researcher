from __future__ import annotations

import hashlib
import inspect
import json
import math
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import sys
from typing import Any, Callable, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
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


class MetricBounds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "MetricBounds":
        if self.minimum is None and self.maximum is None:
            raise ValueError("at least one metric bound is required")
        if any(
            bound is not None and not math.isfinite(bound)
            for bound in (self.minimum, self.maximum)
        ):
            raise ValueError("metric bounds must be finite")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("metric minimum cannot exceed maximum")
        return self


class ValidityRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    require_finite_metrics: bool = True
    max_failed_repetitions: int = Field(default=0, ge=0)
    metric_bounds: dict[str, MetricBounds] = Field(default_factory=dict)


JsonScalar = str | int | float | bool | None


def _validate_finite_json_scalars(
    values: dict[str, JsonScalar],
) -> dict[str, JsonScalar]:
    for name, value in values.items():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    return values


def _validate_logical_paths(paths: list[str]) -> list[str]:
    if len(paths) != len(set(paths)):
        raise ValueError("logical file paths must be unique")
    for raw_path in paths:
        path = PurePosixPath(raw_path)
        if (
            not raw_path
            or path.is_absolute()
            or ".." in path.parts
            or raw_path != path.as_posix()
        ):
            raise ValueError(f"invalid logical file path: {raw_path!r}")
    return paths


class InterventionKnob(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    value_type: Literal["number"]
    allowed_values: list[float] = Field(min_length=1)

    @field_validator("allowed_values")
    @classmethod
    def validate_allowed_values(cls, values: list[float]) -> list[float]:
        if any(not math.isfinite(value) for value in values):
            raise ValueError("allowed knob values must be finite")
        if len(values) != len(set(values)):
            raise ValueError("allowed knob values must be unique")
        return values


class AdaptiveExperimentPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    policy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    decision_point: str = Field(min_length=1)
    no_op_policy: Literal[
        "reject_before_execution",
        "execute_and_mark",
    ]
    max_changes_per_attempt: Literal[1]
    defaults: dict[str, JsonScalar]
    knobs: dict[str, InterventionKnob]
    fixed_config: dict[str, JsonScalar]
    source_files: list[str] = Field(min_length=1)
    expected_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("defaults", "fixed_config")
    @classmethod
    def validate_scalar_mapping(
        cls,
        values: dict[str, JsonScalar],
    ) -> dict[str, JsonScalar]:
        return _validate_finite_json_scalars(values)

    @field_validator("source_files")
    @classmethod
    def validate_source_files(cls, paths: list[str]) -> list[str]:
        return _validate_logical_paths(paths)

    @model_validator(mode="after")
    def validate_catalog(self) -> "AdaptiveExperimentPolicy":
        if set(self.defaults) != set(self.knobs):
            raise ValueError("catalog defaults must exactly match knob names")
        overlap = set(self.fixed_config) & set(self.knobs)
        if overlap:
            raise ValueError(
                "fixed config cannot contain mutable knobs: "
                + ", ".join(sorted(overlap))
            )
        for name, default in self.defaults.items():
            if type(default) is not float:
                raise ValueError(f"default for {name!r} must be a float")
            if default not in self.knobs[name].allowed_values:
                raise ValueError(
                    f"default for {name!r} must be an allowed value"
                )
        return self


class EvaluationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1, 2] = 1
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
    evidence_instructions: str | None = None
    validity: ValidityRules = Field(default_factory=ValidityRules)
    private_data_dir: str | None = None
    evaluator_files: list[str] = Field(default_factory=list)
    adaptive_experiment: AdaptiveExperimentPolicy | None = None

    @field_validator("evaluator_files")
    @classmethod
    def validate_evaluator_files(cls, paths: list[str]) -> list[str]:
        return _validate_logical_paths(paths)

    @model_validator(mode="after")
    def validate_adaptive_schema(self) -> "EvaluationContract":
        if self.adaptive_experiment is not None and self.schema_version != 2:
            raise ValueError(
                "adaptive_experiment requires evaluation contract schema 2"
            )
        if self.adaptive_experiment is not None and not self.evaluator_files:
            raise ValueError(
                "adaptive contract requires explicit evaluator_files"
            )
        return self


EvaluatorFn = Callable[[EvaluationContract, Observation], dict[str, Any]]


class Verifier(Protocol):
    def verify(
        self,
        contract: EvaluationContract,
        observation: Observation,
    ) -> VerificationRecord: ...


def evaluator_identity(
    contract: EvaluationContract,
    contract_dir: str | Path,
) -> str:
    root = Path(contract_dir).resolve()
    if not contract.evaluator_files:
        parts = [contract.entrypoint or ""]
        if contract.entrypoint:
            for token in shlex.split(contract.entrypoint):
                candidate = (root / token).resolve()
                if candidate.is_file() and (
                    candidate.parent == root or root in candidate.parents
                ):
                    parts.append(candidate.read_text(encoding="utf-8"))
        return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()

    files = []
    for logical_path in sorted(contract.evaluator_files):
        candidate = (root / logical_path).resolve()
        if not candidate.is_file() or root not in candidate.parents:
            raise EvaluationError(
                f"declared evaluator file is missing or outside contract dir: "
                f"{logical_path}"
            )
        content = candidate.read_bytes()
        files.append(
            {
                "path": logical_path,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )
    payload = json.dumps(
        {
            "entrypoint": contract.entrypoint or "",
            "files": files,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(
        b"ai-researcher/evaluator-set/v1\0" + payload
    ).hexdigest()


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


def _artifact_integrity_violations(
    observation: Observation,
) -> list[str]:
    violations: list[str] = []
    names = [Path(ref.path).name for ref in observation.artifact_refs]
    duplicates = sorted(
        name for name in set(names) if names.count(name) > 1
    )
    violations.extend(
        f"duplicate_artifact:{name}" for name in duplicates
    )
    for ref in observation.artifact_refs:
        name = Path(ref.path).name
        try:
            content = Path(ref.path).read_bytes()
        except OSError:
            violations.append(f"artifact_missing:{name}")
            continue
        if (
            len(content) != ref.size_bytes
            or hashlib.sha256(content).hexdigest() != ref.sha256
        ):
            violations.append(f"artifact_changed:{name}")
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
    reported_violations = result.get("violations", [])
    if (
        not isinstance(reported_violations, list)
        or any(not isinstance(item, str) or not item for item in reported_violations)
    ):
        violations.append("evaluator_violations_not_string_list")
    else:
        violations.extend(reported_violations)
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

    for name, bounds in contract.validity.metric_bounds.items():
        numeric = metrics.get(name)
        if numeric is None:
            violations.append(f"missing_bounded_metric:{name}")
            continue
        if bounds.minimum is not None and numeric < bounds.minimum:
            violations.append(f"metric_below_minimum:{name}")
        if bounds.maximum is not None and numeric > bounds.maximum:
            violations.append(f"metric_above_maximum:{name}")

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

    violations = list(dict.fromkeys(violations))
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
        return evaluator_identity(contract, self.contract_dir)

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

        violations = _artifact_integrity_violations(observation)
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
