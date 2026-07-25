from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys

import pytest

from research_agent.inno.experience import (
    ArtifactRef,
    CallableVerifier,
    CommandVerifier,
    EvaluationContract,
    Observation,
    PrimaryMetric,
    load_evaluation_contract,
)


NOW = datetime(2026, 7, 25, tzinfo=timezone.utc)


def artifact_ref(path: Path) -> ArtifactRef:
    content = path.read_bytes()
    return ArtifactRef(
        path=str(path),
        sha256=hashlib.sha256(content).hexdigest(),
        media_type="application/json",
        size_bytes=len(content),
    )


def observation(tmp_path: Path) -> Observation:
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text('{"score": 0.8}', encoding="utf-8")
    log_path = tmp_path / "run.log"
    log_path.write_text("completed\n", encoding="utf-8")
    return Observation(
        observation_id="observation-1",
        attempt_id="attempt-1",
        exit_code=0,
        metrics={"score": 0.8},
        artifact_refs=[artifact_ref(metrics_path), artifact_ref(log_path)],
        started_at=NOW,
        completed_at=NOW,
        environment_fingerprint="python=3.11",
    )


def contract(**updates) -> EvaluationContract:
    values = {
        "contract_id": "deterministic-score",
        "version": "1",
        "task_id": "task-1",
        "repetitions": 1,
        "required_artifacts": ["metrics.json", "run.log"],
        "primary_metric": PrimaryMetric(name="score", direction="maximize"),
        "baseline": 0.5,
    }
    values.update(updates)
    return EvaluationContract(**values)


def test_callable_verifier_is_authority_for_verified_metrics(tmp_path):
    raw_observation = observation(tmp_path)

    def evaluator(evaluation_contract, observed):
        assert evaluation_contract.task_id == "task-1"
        assert observed.metrics == {"score": 0.8}
        return {
            "metrics": {"score": 0.75},
            "repetitions": 1,
            "failed_repetitions": 0,
        }

    verification = CallableVerifier(evaluator).verify(contract(), raw_observation)

    assert verification.valid is True
    assert verification.passed is True
    assert verification.outcome == "positive"
    assert verification.verified_metrics == {"score": 0.75}
    assert verification.verified_metrics != raw_observation.metrics


def test_callable_verifier_respects_minimize_direction(tmp_path):
    verification = CallableVerifier(
        lambda *_: {"metrics": {"loss": 0.4}, "repetitions": 1}
    ).verify(
        contract(
            primary_metric=PrimaryMetric(name="loss", direction="minimize"),
            baseline=0.5,
        ),
        observation(tmp_path),
    )

    assert verification.passed is True
    assert verification.baseline_comparison["delta"] == pytest.approx(0.1)


def test_nonfinite_missing_artifact_and_wrong_repetitions_are_invalid(tmp_path):
    raw_observation = observation(tmp_path)
    incomplete = raw_observation.model_copy(
        update={"artifact_refs": [raw_observation.artifact_refs[0]]}
    )
    verification = CallableVerifier(
        lambda *_: {"metrics": {"score": float("nan")}, "repetitions": 1}
    ).verify(contract(repetitions=3), incomplete)

    assert verification.valid is False
    assert verification.outcome == "invalid"
    assert "metric_not_finite:score" in verification.violations
    assert "missing_artifact:run.log" in verification.violations
    assert "repetition_count_mismatch" in verification.violations


def test_callable_exception_becomes_invalid_verification(tmp_path):
    def failing_evaluator(*_):
        raise RuntimeError("boom")

    verification = CallableVerifier(failing_evaluator).verify(
        contract(),
        observation(tmp_path),
    )

    assert verification.valid is False
    assert "evaluator_error:RuntimeError" in verification.violations


def test_load_evaluation_contract_from_yaml(tmp_path):
    path = tmp_path / "contract.yaml"
    path.write_text(
        """
schema_version: 1
contract_id: score
version: "2"
task_id: task-1
repetitions: 2
required_artifacts: [metrics.json]
primary_metric:
  name: score
  direction: maximize
baseline: 0.5
""".strip(),
        encoding="utf-8",
    )

    loaded = load_evaluation_contract(path)

    assert loaded.contract_id == "score"
    assert loaded.version == "2"
    assert loaded.repetitions == 2


def test_command_verifier_reads_machine_result_not_stdout(tmp_path):
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    raw_observation = observation(attempt_dir)
    evaluator_path = tmp_path / "evaluate.py"
    evaluator_path.write_text(
        """
import json
from pathlib import Path
import sys

attempt_dir = Path(sys.argv[1])
print('diagnostic score=999')
(attempt_dir / 'verification_result.json').write_text(
    json.dumps({'metrics': {'score': 0.7}, 'repetitions': 1}),
    encoding='utf-8',
)
""".strip(),
        encoding="utf-8",
    )
    evaluation_contract = contract(
        entrypoint=f"{sys.executable} {evaluator_path} {{attempt_dir}}",
    )

    verification = CommandVerifier(contract_dir=tmp_path).verify(
        evaluation_contract,
        raw_observation,
    )

    assert verification.valid is True
    assert verification.verified_metrics == {"score": 0.7}
    assert Path(verification.evidence_refs[-1].path).name == "verification_result.json"


def test_command_verifier_requires_result_file(tmp_path):
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    raw_observation = observation(attempt_dir)
    evaluator_path = tmp_path / "evaluate.py"
    evaluator_path.write_text("print('score=1.0')\n", encoding="utf-8")

    verification = CommandVerifier(contract_dir=tmp_path).verify(
        contract(entrypoint=f"{sys.executable} {evaluator_path}"),
        raw_observation,
    )

    assert verification.valid is False
    assert "missing_or_invalid_result_file" in verification.violations


def test_command_verifier_timeout_is_invalid(tmp_path):
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    raw_observation = observation(attempt_dir)
    evaluator_path = tmp_path / "evaluate.py"
    evaluator_path.write_text(
        "import time\ntime.sleep(5)\n",
        encoding="utf-8",
    )

    verification = CommandVerifier(contract_dir=tmp_path).verify(
        contract(
            entrypoint=f"{sys.executable} {evaluator_path}",
            timeout_seconds=0.01,
        ),
        raw_observation,
    )

    assert verification.valid is False
    assert "evaluator_timeout" in verification.violations
