from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from research_agent.inno.experience import (
    ArtifactRef,
    CallableVerifier,
    CommandVerifier,
    ContainerVerifier,
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
            "public_feedback": ["The revised configuration remains stable."],
        }

    verification = CallableVerifier(evaluator).verify(contract(), raw_observation)

    assert verification.valid is True
    assert verification.passed is True
    assert verification.outcome == "positive"
    assert verification.verified_metrics == {"score": 0.75}
    assert verification.verified_metrics != raw_observation.metrics
    assert verification.public_feedback == [
        "The revised configuration remains stable."
    ]


def test_public_feedback_is_bounded_and_must_be_a_string_list(tmp_path):
    verification = CallableVerifier(
        lambda *_: {
            "metrics": {"score": 0.75},
            "repetitions": 1,
            "public_feedback": ["one", "two"],
        }
    ).verify(
        contract(
            validity={
                "max_public_feedback_items": 1,
                "max_public_feedback_chars": 20,
            }
        ),
        observation(tmp_path),
    )

    assert verification.valid is False
    assert "too_many_public_feedback_items" in verification.violations

    malformed = CallableVerifier(
        lambda *_: {
            "metrics": {"score": 0.75},
            "repetitions": 1,
            "public_feedback": "not-a-list",
        }
    ).verify(contract(), observation(tmp_path))

    assert malformed.valid is False
    assert "public_feedback_not_string_list" in malformed.violations


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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("result_file", "../verification_result.json"),
        ("result_file", "/tmp/verification_result.json"),
        ("required_artifacts", ["../metrics.json"]),
        ("required_artifacts", ["metrics.json", "metrics.json"]),
    ],
)
def test_evaluation_contract_rejects_unsafe_artifact_names(field, value):
    with pytest.raises(ValidationError):
        contract(**{field: value})


def test_evaluator_digest_covers_all_contract_files(tmp_path):
    (tmp_path / "evaluate.py").write_text("# entrypoint\n", encoding="utf-8")
    helper = tmp_path / "hidden_cases.json"
    helper.write_text('{"expected": 1}\n', encoding="utf-8")
    verifier = CommandVerifier(contract_dir=tmp_path)
    evaluation_contract = contract(entrypoint="python evaluate.py {attempt_dir}")

    before = verifier._evaluator_digest(evaluation_contract)
    helper.write_text('{"expected": 2}\n', encoding="utf-8")
    after = verifier._evaluator_digest(evaluation_contract)

    assert before != after


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


def test_command_verifier_rejects_tampered_observation_artifacts(tmp_path):
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    raw_observation = observation(attempt_dir)
    (attempt_dir / "metrics.json").write_text('{"score": 999}', encoding="utf-8")

    verification = CommandVerifier(contract_dir=tmp_path).verify(
        contract(entrypoint="python evaluate.py {attempt_dir}"),
        raw_observation,
    )

    assert verification.valid is False
    assert "artifact_digest_mismatch:metrics.json" in verification.violations


def test_container_verifier_uses_isolated_networkless_runtime(tmp_path):
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    raw_observation = observation(attempt_dir)
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    evaluator_path = contract_dir / "evaluate.py"
    evaluator_path.write_text("# deterministic evaluator\n", encoding="utf-8")
    captured = {}

    def fake_docker(command, **kwargs):
        action = command[1]
        if action == "volume" and command[2] == "create":
            return subprocess.CompletedProcess(command, 0, "evaluator-volume\n", "")
        if action == "run" and "dst=/source,readonly" in " ".join(command):
            source_mount = next(
                command[index + 1]
                for index, token in enumerate(command)
                if token == "--mount" and "dst=/source" in command[index + 1]
            )
            host_evaluator = Path(
                next(
                    value.removeprefix("src=")
                    for value in source_mount.split(",")
                    if value.startswith("src=")
                )
            )
            captured["evaluator_mode"] = host_evaluator.stat().st_mode & 0o777
            captured["evaluator_file_mode"] = (
                (host_evaluator / "evaluate.py").stat().st_mode & 0o777
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if action == "run":
            captured["command"] = command
            captured["kwargs"] = kwargs
            mounts = [
                command[index + 1]
                for index, token in enumerate(command)
                if token == "--mount"
            ]
            attempt_mount = next(item for item in mounts if "dst=/attempt" in item)
            captured["host_attempt"] = Path(
                next(
                    value.removeprefix("src=")
                    for value in attempt_mount.split(",")
                    if value.startswith("src=")
                )
            )
            (captured["host_attempt"] / "verification_result.json").write_text(
                json.dumps({"metrics": {"score": 0.7}, "repetitions": 1}),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        assert action == "volume" and command[2] == "rm"
        return subprocess.CompletedProcess(command, 0, "", "")

    verification = ContainerVerifier(
        contract_dir=contract_dir,
        runner=fake_docker,
    ).verify(
        contract(
            entrypoint="python evaluate.py {attempt_dir}",
            container_image=(
                "python:3.11-alpine@sha256:"
                "25976e9d34a0fab1f278cae931f34c8303d97bf0c0d7f85b6b4dcf641d7702a4"
            ),
        ),
        raw_observation,
    )

    command = captured["command"]
    assert command[:3] == ["docker", "run", "--rm"]
    assert command[command.index("--pull") + 1] == "never"
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert ["--cap-drop", "ALL"] == command[
        command.index("--cap-drop") : command.index("--cap-drop") + 2
    ]
    assert ["--cap-add", "SETUID"] == command[
        command.index("--cap-add") : command.index("--cap-add") + 2
    ]
    second_cap_add = command.index("--cap-add", command.index("--cap-add") + 1)
    assert command[second_cap_add : second_cap_add + 2] == ["--cap-add", "SETGID"]
    assert "no-new-privileges" in command
    assert captured["kwargs"]["timeout"] == 900
    assert captured["evaluator_mode"] == 0o700
    assert captured["evaluator_file_mode"] == 0o600
    assert verification.valid is True
    assert verification.verified_metrics == {"score": 0.7}
    assert (attempt_dir / "verification_result.json").is_file()


def test_container_verifier_rejects_mutable_image_tag(tmp_path):
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    raw_observation = observation(attempt_dir)

    verification = ContainerVerifier(contract_dir=tmp_path).verify(
        contract(
            entrypoint="python evaluate.py {attempt_dir}",
            container_image="python:3.11-alpine",
        ),
        raw_observation,
    )

    assert verification.valid is False
    assert "evaluator_container_image_not_pinned" in verification.violations


def test_container_verifier_rejects_symlinked_evaluator_contract(tmp_path):
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    raw_observation = observation(attempt_dir)
    target = tmp_path / "outside.py"
    target.write_text("# outside contract\n", encoding="utf-8")
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    (contract_dir / "evaluate.py").symlink_to(target)

    verification = ContainerVerifier(contract_dir=contract_dir).verify(
        contract(
            entrypoint="python evaluate.py {attempt_dir}",
            container_image=(
                "python:3.11-alpine@sha256:"
                "25976e9d34a0fab1f278cae931f34c8303d97bf0c0d7f85b6b4dcf641d7702a4"
            ),
        ),
        raw_observation,
    )

    assert verification.valid is False
    assert "evaluator_contract_contains_symlink" in verification.violations


@pytest.mark.skipif(
    os.getenv("RUN_DOCKER_TESTS") != "1",
    reason="requires an explicitly enabled Docker daemon",
)
def test_checked_in_contract_runs_in_real_container(tmp_path):
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    raw_observation = observation(attempt_dir)
    contract_dir = (
        Path(__file__).resolve().parents[2]
        / "benchmark"
        / "evaluators"
        / "deterministic_score"
    )
    evaluation_contract = load_evaluation_contract(contract_dir / "contract.yaml")

    verification = ContainerVerifier(contract_dir=contract_dir).verify(
        evaluation_contract,
        raw_observation,
    )

    assert verification.valid is True, verification.violations
    assert verification.passed is True
    assert verification.verified_metrics == {"score": 0.8}
