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
    MetricBounds,
    Observation,
    PrimaryMetric,
    ValidityRules,
    load_evaluation_contract,
)
from research_agent.inno.experience.evaluation import (
    AdaptiveExperimentPolicy,
    InterventionKnob,
    evaluator_identity,
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


def test_secondary_metric_bounds_are_validity_guardrails(tmp_path):
    verification = CallableVerifier(
        lambda *_: {
            "metrics": {"score": 0.8, "reconstruction_psnr_db": 4.0},
            "repetitions": 1,
        }
    ).verify(
        contract(
            validity=ValidityRules(
                metric_bounds={
                    "reconstruction_psnr_db": MetricBounds(minimum=10.0)
                }
            )
        ),
        observation(tmp_path),
    )

    assert verification.valid is False
    assert verification.passed is False
    assert verification.outcome == "invalid"
    assert (
        "metric_below_minimum:reconstruction_psnr_db"
        in verification.violations
    )


@pytest.mark.parametrize(
    "non_finite",
    [float("nan"), float("inf"), float("-inf")],
)
def test_metric_bounds_reject_non_finite_limits(non_finite):
    with pytest.raises(ValueError, match="metric bounds must be finite"):
        MetricBounds(minimum=non_finite)

    with pytest.raises(ValueError, match="metric bounds must be finite"):
        MetricBounds(maximum=non_finite)


def test_schema_two_contract_owns_a_strict_intervention_catalog():
    policy = AdaptiveExperimentPolicy(
        policy_id="one-layer-vq-phase-a",
        version="1",
        decision_point="vq.quantizer_optimization",
        no_op_policy="reject_before_execution",
        max_changes_per_attempt=1,
        defaults={
            "projection_lr_multiplier": 1.0,
            "commitment_weight": 0.25,
        },
        knobs={
            "projection_lr_multiplier": InterventionKnob(
                value_type="number",
                allowed_values=[0.5, 1.0, 2.0],
            ),
            "commitment_weight": InterventionKnob(
                value_type="number",
                allowed_values=[0.1, 0.25, 0.5],
            ),
        },
        fixed_config={"dataset_id": "cifar10", "epochs": 2},
        source_files=[
            "protocol.py",
            "run_training_testing.py",
            "attempt_spec.py",
        ],
        expected_source_digest="a" * 64,
    )

    adaptive_contract = EvaluationContract(
        schema_version=2,
        contract_id="one-layer-vq-cifar10-adaptive",
        version="3-phase-a",
        task_id="one_layer_vq:task1",
        evaluator_files=["evaluate_v3.py", "provenance_schema.py"],
        primary_metric=PrimaryMetric(
            name="codebook_utilization",
            direction="maximize",
        ),
        baseline=0.95,
        adaptive_experiment=policy,
    )

    assert adaptive_contract.adaptive_experiment == policy
    assert adaptive_contract.evaluator_files == [
        "evaluate_v3.py",
        "provenance_schema.py",
    ]


def test_intervention_catalog_rejects_mutable_knob_in_fixed_config():
    with pytest.raises(
        ValueError,
        match="fixed config cannot contain mutable knobs",
    ):
        AdaptiveExperimentPolicy(
            policy_id="one-layer-vq-phase-a",
            version="1",
            decision_point="vq.quantizer_optimization",
            no_op_policy="reject_before_execution",
            max_changes_per_attempt=1,
            defaults={"commitment_weight": 0.25},
            knobs={
                "commitment_weight": InterventionKnob(
                    value_type="number",
                    allowed_values=[0.1, 0.25, 0.5],
                )
            },
            fixed_config={
                "dataset_id": "cifar10",
                "commitment_weight": 0.25,
            },
            source_files=["protocol.py"],
            expected_source_digest="a" * 64,
        )


def test_adaptive_contract_requires_explicit_evaluator_files():
    policy = AdaptiveExperimentPolicy(
        policy_id="one-layer-vq-phase-a",
        version="1",
        decision_point="vq.quantizer_optimization",
        no_op_policy="reject_before_execution",
        max_changes_per_attempt=1,
        defaults={"commitment_weight": 0.25},
        knobs={
            "commitment_weight": InterventionKnob(
                value_type="number",
                allowed_values=[0.25, 0.5],
            )
        },
        fixed_config={"dataset_id": "cifar10"},
        source_files=["protocol.py"],
        expected_source_digest="a" * 64,
    )

    with pytest.raises(
        ValueError,
        match="adaptive contract requires explicit evaluator_files",
    ):
        EvaluationContract(
            schema_version=2,
            contract_id="adaptive",
            task_id="one_layer_vq:task1",
            primary_metric=PrimaryMetric(
                name="codebook_utilization",
                direction="maximize",
            ),
            baseline=0.95,
            adaptive_experiment=policy,
        )


def test_intervention_catalog_rejects_integer_numeric_defaults():
    with pytest.raises(
        ValueError,
        match="default for 'projection_lr_multiplier' must be a float",
    ):
        AdaptiveExperimentPolicy(
            policy_id="one-layer-vq-phase-a",
            version="1",
            decision_point="vq.quantizer_optimization",
            no_op_policy="reject_before_execution",
            max_changes_per_attempt=1,
            defaults={"projection_lr_multiplier": 1},
            knobs={
                "projection_lr_multiplier": InterventionKnob(
                    value_type="number",
                    allowed_values=[1.0, 2.0],
                )
            },
            fixed_config={"dataset_id": "cifar10"},
            source_files=["protocol.py"],
            expected_source_digest="a" * 64,
        )


def test_evaluator_identity_covers_every_declared_helper(tmp_path):
    (tmp_path / "evaluate_v3.py").write_text("print('v3')\n", encoding="utf-8")
    helper = tmp_path / "provenance_schema.py"
    helper.write_text("VERSION = 1\n", encoding="utf-8")
    evaluation_contract = contract(
        schema_version=2,
        evaluator_files=["evaluate_v3.py", "provenance_schema.py"],
    )

    before = evaluator_identity(evaluation_contract, tmp_path)
    helper.write_text("VERSION = 2\n", encoding="utf-8")
    after = evaluator_identity(evaluation_contract, tmp_path)

    assert before != after


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


def test_command_verifier_preserves_evaluator_reported_violations(tmp_path):
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
(attempt_dir / 'verification_result.json').write_text(
    json.dumps({
        'metrics': {},
        'repetitions': 1,
        'failed_repetitions': 1,
        'violations': ['evidence_invalid:index_out_of_range'],
    }),
    encoding='utf-8',
)
""".strip(),
        encoding="utf-8",
    )

    verification = CommandVerifier(contract_dir=tmp_path).verify(
        contract(entrypoint=f"{sys.executable} {evaluator_path} {{attempt_dir}}"),
        raw_observation,
    )

    assert verification.valid is False
    assert "evidence_invalid:index_out_of_range" in verification.violations


def test_command_verifier_rejects_evidence_changed_during_evaluation(
    tmp_path,
):
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
(attempt_dir / 'run.log').write_text('tampered\\n', encoding='utf-8')
(attempt_dir / 'verification_result.json').write_text(
    json.dumps({'metrics': {'score': 0.7}, 'repetitions': 1}),
    encoding='utf-8',
)
""".strip(),
        encoding="utf-8",
    )

    verification = CommandVerifier(contract_dir=tmp_path).verify(
        contract(
            entrypoint=f"{sys.executable} {evaluator_path} {{attempt_dir}}"
        ),
        raw_observation,
    )

    assert verification.valid is False
    assert "artifact_changed:run.log" in verification.violations


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
