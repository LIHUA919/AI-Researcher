import copy
import sqlite3
import json
from pathlib import Path
from types import SimpleNamespace

import benchmark.run_one_layer_vq_closed_loop_v3 as runner
import pytest
from benchmark.run_one_layer_vq_closed_loop_v3 import (
    CONTRACT_PATH,
    arm_order,
    build_trial_command,
    collect_trial,
    prepare_dry_run,
    summarize_trials,
)


def test_v3_arm_order_is_seed_counterbalanced():
    assert arm_order(0) == ("control", "treatment")
    assert arm_order(1) == ("treatment", "control")


def test_v3_trial_command_changes_only_semantic_memory_budget_between_arms(
    tmp_path,
):
    common = {
        "python": Path("/test/python"),
        "model": "test-model",
        "output_root": tmp_path,
        "seed": 401,
        "port": 13000,
    }

    control, _, _ = build_trial_command(arm="control", **common)
    treatment, _, _ = build_trial_command(arm="treatment", **common)

    assert str(CONTRACT_PATH) in control
    assert str(CONTRACT_PATH) in treatment
    assert control[control.index("--cache-policy") + 1] == "disabled"
    assert treatment[treatment.index("--cache-policy") + 1] == "disabled"
    assert control[control.index("--recall-item-budget") + 1] == "0"
    assert control[control.index("--recall-token-budget") + 1] == "0"
    assert treatment[treatment.index("--recall-item-budget") + 1] == "8"
    assert treatment[treatment.index("--recall-token-budget") + 1] == "3000"
    assert control[
        control.index("--adaptive-execution-timeout-seconds") + 1
    ] == str(runner.DEFAULT_TRIAL_TIMEOUT_SECONDS)
    assert treatment[
        treatment.index("--adaptive-execution-timeout-seconds") + 1
    ] == str(runner.DEFAULT_TRIAL_TIMEOUT_SECONDS)

    def scientific_arguments(command):
        ignored = {
            "--container_name",
            "--cache_path",
            "--experience-store",
            "--recall-item-budget",
            "--recall-token-budget",
        }
        return {
            command[index]: command[index + 1]
            for index in range(2, len(command), 2)
            if command[index] not in ignored
        }

    assert scientific_arguments(control) == scientific_arguments(treatment)


def test_v3_summary_reports_gain_only_for_comparable_verified_pair():
    provenance = {
        "source_digest": "a" * 64,
        "dataset_digest": "b" * 64,
        "environment_digest": "c" * 64,
        "contract_digest": "d" * 64,
        "evaluator_digest": "e" * 64,
    }
    trials = [
        {
            "seed": 401,
            "arm": "control",
            "score": 0.25,
            "valid": True,
            "manifest_match": True,
            "manipulation_status": "baseline",
            "immediate_feedback": [
                {
                    "attempt_id": "control-attempt",
                    "intervention_id": "control-intervention",
                    "config_digest": "f" * 64,
                    "effective_config": {},
                    "verified_metrics": {"codebook_utilization": 0.25},
                    "outcome": "negative",
                    "guardrail_violations": [],
                }
            ],
            "recall": {"item_count": 0, "knowledge_ids": []},
            "citation_to_action": [],
            "interventions": [],
            **provenance,
        },
        {
            "seed": 401,
            "arm": "treatment",
            "score": 0.5,
            "valid": True,
            "manifest_match": True,
            "manipulation_status": "changed",
            "immediate_feedback": [
                {
                    "attempt_id": "treatment-attempt",
                    "intervention_id": "treatment-intervention",
                    "config_digest": "f" * 64,
                    "effective_config": {},
                    "verified_metrics": {"codebook_utilization": 0.5},
                    "outcome": "negative",
                    "guardrail_violations": [],
                }
            ],
            "recall": {
                "item_count": 1,
                "knowledge_ids": ["knowledge-1"],
            },
            "citation_to_action": [
                {
                    "knowledge_id": "knowledge-1",
                    "intervention_id": "treatment-intervention",
                    "knob": "projection_lr_multiplier",
                    "target": 2.0,
                }
            ],
            "interventions": [
                {
                    "intervention_id": "treatment-intervention",
                    "intervention_digest": "1" * 64,
                    "manipulation_status": "changed",
                }
            ],
            **provenance,
        },
    ]

    report = summarize_trials(
        trials,
        seeds=[401],
        model="test-model",
        revision="f" * 64,
    )

    assert report["paired_deltas"] == [0.25]
    assert report["paired_provenance_match"] == [True]
    assert report["paired_feedback_structure_match"] == [True]
    assert report["recall"]["item_count"] == 1
    assert report["citation_to_action"][0]["knowledge_id"] == "knowledge-1"
    assert report["distinct_intervention_count"] == 1
    assert report["manifest_match_rate"] == 1.0
    assert report["semantic_memory_valid"] is True
    assert report["phase_a_chain_valid"] is True
    assert report["phase_a_diagnostic_mean_paired_delta"] == 0.25
    assert report["claim_valid"] is False
    assert report["experience_gain"] is None


def test_v3_summary_blocks_claim_without_recalled_citation_to_action():
    provenance = {
        "source_digest": "a" * 64,
        "dataset_digest": "b" * 64,
        "environment_digest": "c" * 64,
        "contract_digest": "d" * 64,
        "evaluator_digest": "e" * 64,
    }
    trials = [
        {
            "seed": 401,
            "arm": "control",
            "score": 0.25,
            "valid": True,
            "manifest_match": True,
            "manipulation_status": "baseline",
            "immediate_feedback": [{"shape": "same"}],
            "recall": {"item_count": 0, "knowledge_ids": []},
            "citation_to_action": [],
            "interventions": [],
            **provenance,
        },
        {
            "seed": 401,
            "arm": "treatment",
            "score": 0.5,
            "valid": True,
            "manifest_match": True,
            "manipulation_status": "changed",
            "immediate_feedback": [{"shape": "same"}],
            "recall": {"item_count": 0, "knowledge_ids": []},
            "citation_to_action": [],
            "interventions": [
                {
                    "intervention_id": "treatment-intervention",
                    "intervention_digest": "1" * 64,
                    "manipulation_status": "changed",
                }
            ],
            **provenance,
        },
    ]

    report = summarize_trials(
        copy.deepcopy(trials),
        seeds=[401],
        model="test-model",
        revision="f" * 64,
    )

    assert report["manipulation_valid"] is True
    assert report["semantic_memory_valid"] is False
    assert report["phase_a_chain_valid"] is False
    assert report["claim_valid"] is False
    assert report["experience_gain"] is None


def test_v3_summary_blocks_claim_when_manipulation_is_no_effect():
    provenance = {
        "source_digest": "a" * 64,
        "dataset_digest": "b" * 64,
        "environment_digest": "c" * 64,
        "contract_digest": "d" * 64,
        "evaluator_digest": "e" * 64,
    }
    trials = [
        {
            "seed": 401,
            "arm": arm,
            "score": score,
            "valid": True,
            "manifest_match": True,
            "manipulation_status": status,
            **provenance,
        }
        for arm, score, status in (
            ("control", 0.25, "baseline"),
            ("treatment", 0.5, "no_effect"),
        )
    ]

    report = summarize_trials(
        trials,
        seeds=[401],
        model="test-model",
        revision="f" * 64,
    )

    assert report["manipulation_valid"] is False
    assert report["no_op_rate"] == 0.5
    assert report["claim_valid"] is False
    assert report["experience_gain"] is None


def test_v3_summary_marks_digest_mismatch_pair_incomparable():
    shared = {
        "dataset_digest": "b" * 64,
        "environment_digest": "c" * 64,
        "contract_digest": "d" * 64,
        "evaluator_digest": "e" * 64,
        "score": 0.5,
        "valid": True,
        "manifest_match": True,
    }
    trials = [
        {
            **shared,
            "seed": 401,
            "arm": "control",
            "source_digest": "a" * 64,
            "manipulation_status": "baseline",
        },
        {
            **shared,
            "seed": 401,
            "arm": "treatment",
            "source_digest": "f" * 64,
            "manipulation_status": "changed",
        },
    ]

    report = summarize_trials(
        trials,
        seeds=[401],
        model="test-model",
        revision="f" * 64,
    )

    assert report["paired_provenance_match"] == [False]
    assert report["paired_deltas"] == [None]
    assert report["claim_valid"] is False
    assert report["experience_gain"] is None


def test_v3_collect_trial_reads_typed_provenance_and_intervention(
    monkeypatch,
    tmp_path,
):
    digests = {
        "source_digest": "a" * 64,
        "dataset_digest": "b" * 64,
        "environment_digest": "c" * 64,
        "contract_digest": "d" * 64,
        "evaluator_digest": "e" * 64,
        "proposal_digest": "1" * 64,
        "intervention_digest": "2" * 64,
        "config_digest": "3" * 64,
    }
    attempt_spec = tmp_path / "attempt_spec.json"
    attempt_spec.write_text(
        runner._canonical_json(
            {
                "provenance": {
                    name: value
                    for name, value in digests.items()
                    if name
                    not in {
                        "proposal_digest",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "evaluation_manifest.json"
    manifest.write_text(
        runner._canonical_json(
            {
                "attempt_spec_sha256": runner._raw_sha256(
                    attempt_spec.read_bytes()
                ),
                "contract": {
                    "digest": digests["contract_digest"],
                },
                "provenance": {
                    "proposal_digest": digests["proposal_digest"],
                    "intervention_digest": digests["intervention_digest"],
                    "config_digest": digests["config_digest"],
                    "source_digest": digests["source_digest"],
                    "dataset_digest": digests["dataset_digest"],
                    "environment_digest": digests["environment_digest"],
                    "evaluator_digest": digests["evaluator_digest"],
                    "manipulation_status": "changed",
                },
            }
        ),
        encoding="utf-8",
    )
    observation = SimpleNamespace(
        observation_id="observation-2",
        artifact_refs=[
            SimpleNamespace(path=str(attempt_spec)),
            SimpleNamespace(path=str(manifest)),
        ],
    )
    verification = SimpleNamespace(
        verification_id="verification-2",
        valid=True,
        outcome="positive",
        verified_metrics={"codebook_utilization": 0.75},
        violations=[],
        evidence_refs=observation.artifact_refs,
    )
    attempt = SimpleNamespace(
        attempt_id="attempt-2",
        run_id="one_layer_vq",
        iteration_id="iteration-002",
    )
    experience = SimpleNamespace(
        attempt=attempt,
        observation=observation,
        verification=verification,
    )
    proposal = SimpleNamespace(
        knob="projection_lr_multiplier",
        target=2.0,
        cited_knowledge_ids=["knowledge-1"],
    )
    intervention = SimpleNamespace(
        intervention_id="intervention-2",
        iteration_id="iteration-002",
        proposal=proposal,
        proposal_digest=digests["proposal_digest"],
        intervention_digest=digests["intervention_digest"],
        config_digest=digests["config_digest"],
        resolved_config={"projection_lr_multiplier": 2.0},
        manipulation_status="changed",
    )
    provenance = SimpleNamespace(
        intervention_id=intervention.intervention_id,
        **digests,
    )
    recall_context = SimpleNamespace(
        items=[
            SimpleNamespace(
                knowledge_id="knowledge-1",
                citation_id="citation-1",
            )
        ]
    )

    class StubLedger:
        def query(self, query):
            return [experience]

        def list_interventions(self, run_id):
            assert run_id == "one_layer_vq"
            return [intervention]

        def list_recall_contexts(self):
            return [recall_context]

        def find_trial_provenance(self, observation_id):
            assert observation_id == observation.observation_id
            return provenance

    monkeypatch.setattr(runner, "_open_ledger", lambda path: StubLedger())
    store_path = tmp_path / "experience.sqlite3"
    store_path.touch()

    trial = collect_trial(
        seed=401,
        arm="treatment",
        cache_path=tmp_path / "cache",
        store_path=store_path,
        wall_seconds=3.5,
        return_code=0,
    )

    assert trial["score"] == 0.75
    assert trial["valid"] is True
    assert trial["manifest_match"] is True
    assert trial["manipulation_status"] == "changed"
    assert trial["source_digest"] == digests["source_digest"]
    assert trial["recall"]["knowledge_ids"] == ["knowledge-1"]
    assert trial["citation_to_action"] == [
        {
            "knowledge_id": "knowledge-1",
            "intervention_id": "intervention-2",
            "knob": "projection_lr_multiplier",
            "target": 2.0,
        }
    ]
    assert trial["immediate_feedback"][0]["verified_metrics"] == {
        "codebook_utilization": 0.75
    }


def test_v3_dry_run_prepares_baselines_without_fake_trial_records(tmp_path):
    output_root = tmp_path / "dry-run"

    report = prepare_dry_run(
        output_root=output_root,
        seeds=[401],
    )

    assert report["status"] == "dry_run_completed"
    assert report["contract"]["schema_version"] == 2
    assert report["dataset"]["archive_identity_valid"] is True
    assert report["arm_order"] == {"401": ["control", "treatment"]}
    assert len(report["trials"]) == 2
    for trial in report["trials"]:
        assert trial["planner_invocation_count"] == 0
        assert trial["execution_started"] is False
        assert trial["manipulation_status"] == "baseline"
        assert trial["preflight"]["source_digest"] == report["contract"][
            "expected_source_digest"
        ]
        spec_path = Path(trial["attempt_spec_path"])
        assert spec_path.is_file()
        assert {path.name for path in spec_path.parent.iterdir()} == {
            "attempt_spec.json"
        }
        with sqlite3.connect(trial["experience_store"]) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM intervention_records"
            ).fetchone()[0] == 1
            for table in (
                "experiment_attempts",
                "observations",
                "verification_records",
                "experience_records",
            ):
                assert connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0] == 0


def test_v3_dry_run_cli_never_probes_credentials_or_starts_process(
    monkeypatch,
    tmp_path,
):
    calls = []

    def fake_prepare_dry_run(*, output_root, seeds):
        calls.append((output_root, seeds))
        return {"status": "dry_run_completed"}

    monkeypatch.setattr(runner, "prepare_dry_run", fake_prepare_dry_run)
    monkeypatch.setattr(
        runner,
        "credential_probe",
        lambda model: (_ for _ in ()).throw(
            AssertionError("credential probe must not run")
        ),
    )
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("subprocess must not run")
        ),
    )

    result = runner.main(
        [
            "--seeds",
            "401",
            "--output-root",
            str(tmp_path),
            "--dry-run",
        ]
    )

    assert result == 0
    assert calls == [(tmp_path.resolve(), [401])]


def test_v3_cli_rejects_nonpositive_trial_timeout(tmp_path):
    with pytest.raises(SystemExit, match="trial timeout"):
        runner.main(
            [
                "--seeds",
                "401",
                "--model",
                "test-model",
                "--output-root",
                str(tmp_path),
                "--trial-timeout-seconds",
                "0",
                "--skip-credential-probe",
            ]
        )


def test_v3_redactor_handles_case_insensitive_sensitive_names(monkeypatch):
    secrets = {
        "provider_key": "lowercase-key-value",
        "database_PASSWORD": "password-value",
        "Authorization": "Bearer authorization-value",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)

    authorization_header = "Authorization: Basic inline-credential"
    redacted = runner._redacted_text(
        " ".join([*secrets.values(), authorization_header])
    )

    for value in secrets.values():
        assert value not in redacted
    assert "inline-credential" not in redacted
    assert redacted.count("[REDACTED]") == len(secrets) + 1


def test_v3_timeout_writes_partial_typed_report_and_redacts_log(
    monkeypatch,
    tmp_path,
):
    secret = "sk-test-secret-value"
    monkeypatch.setenv("TEST_API_KEY", secret)
    monkeypatch.setattr(runner, "_load_environment", lambda: None)
    monkeypatch.setattr(runner, "source_revision", lambda: "f" * 64)
    cleaned_containers = []

    def timeout_run(command, **kwargs):
        kwargs["log"].write(f"provider error contained {secret}\n")
        kwargs["log"].flush()
        raise runner.subprocess.TimeoutExpired(
            cmd=command,
            timeout=kwargs["timeout_seconds"],
        )

    monkeypatch.setattr(runner, "_run_trial_process", timeout_run)
    monkeypatch.setattr(
        runner,
        "_cleanup_trial_container",
        cleaned_containers.append,
    )

    def fake_collect_trial(**values):
        assert values["return_code"] == 124
        return {
            "seed": values["seed"],
            "arm": values["arm"],
            "score": None,
            "valid": False,
            "manifest_match": False,
            "manipulation_status": "rejected",
            "failure_signature": "process_exit_124",
            "recall": {"item_count": 0, "knowledge_ids": []},
            "citation_to_action": [],
            "interventions": [],
            "immediate_feedback": [],
            **{
                field: None
                for field in runner.PAIR_PROVENANCE_FIELDS
            },
        }

    monkeypatch.setattr(runner, "collect_trial", fake_collect_trial)

    result = runner.main(
        [
            "--seeds",
            "401",
            "--model",
            "test-model",
            "--output-root",
            str(tmp_path),
            "--trial-timeout-seconds",
            "0.01",
            "--skip-credential-probe",
        ]
    )

    manifest = json.loads(
        (tmp_path / "run_manifest.json").read_text(encoding="utf-8")
    )
    report = json.loads(
        (tmp_path / "paired_report.json").read_text(encoding="utf-8")
    )
    runner_log = Path(
        manifest["trials"][0]["runner_log"]
    ).read_text(encoding="utf-8")

    assert result == 124
    assert manifest["status"] == "trial_failed"
    assert manifest["trials"][0]["timed_out"] is True
    assert manifest["trials"][0]["failure_signature"] == "trial_timeout"
    assert cleaned_containers == ["vq-v3-401-control"]
    assert report["claim_valid"] is False
    assert secret not in runner_log
    assert "[REDACTED]" in runner_log
