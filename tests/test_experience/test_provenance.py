from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from research_agent.inno.experience import (
    ArtifactRef,
    InterventionProposal,
    InterventionRecord,
    KnobChange,
    TrialProvenanceRecord,
    semantic_digest,
)


NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)


def test_semantic_digest_is_canonical_and_rejects_implicit_json_conversion():
    assert semantic_digest("test/v1", {"b": 2, "a": 1}) == semantic_digest(
        "test/v1",
        {"a": 1, "b": 2},
    )
    with pytest.raises(ValueError, match="strict JSON"):
        semantic_digest("test/v1", {"target": Decimal("2.0")})


def test_baseline_intervention_requires_digest_of_complete_resolved_config():
    proposal = InterventionProposal(
        domain="vq",
        schema_id="vq.intervention@1",
        decision_point="optimizer",
        knob=None,
        target=None,
        cited_knowledge_ids=[],
        expected_primary_metric_direction="unchanged",
        guardrail_risks=[],
        rationale="Establish the fixed Phase A baseline.",
    )
    resolved_config = {
        "learning_rate": 0.0003,
        "projection_lr_multiplier": 1.0,
        "seed": 401,
    }
    values = {
        "intervention_id": "intervention-baseline",
        "run_id": "run-1",
        "iteration_id": "iteration-1",
        "task_id": "one_layer_vq:task1",
        "hypothesis_id": "hypothesis-1",
        "recall_snapshot_id": "empty",
        "previous_intervention_id": None,
        "proposal": proposal,
        "proposal_digest": semantic_digest(
            "ai-researcher/proposal/v1",
            proposal.model_dump(mode="json"),
        ),
        "resolved_config": resolved_config,
        "config_digest": semantic_digest(
            "ai-researcher/run-config/v1",
            resolved_config,
        ),
        "intervention_digest": "a" * 64,
        "manipulation_status": "baseline",
        "violations": [],
        "created_at": NOW,
    }

    record = InterventionRecord(**values)

    assert record.resolved_config == resolved_config
    with pytest.raises(ValidationError, match="config_digest"):
        InterventionRecord(**{**values, "config_digest": "b" * 64})


def test_rejected_intervention_retains_proposal_but_has_no_resolved_config():
    proposal = InterventionProposal(
        domain="vq",
        schema_id="vq.intervention@1",
        decision_point="optimizer",
        knob="unknown_knob",
        target=2.0,
        cited_knowledge_ids=["knowledge-1", "knowledge-1"],
        expected_primary_metric_direction="increase",
        guardrail_risks=["policy_violation"],
        rationale="Exercise the fail-closed proposal path.",
    )
    values = {
        "intervention_id": "intervention-rejected",
        "run_id": "run-1",
        "iteration_id": "iteration-2",
        "task_id": "one_layer_vq:task1",
        "hypothesis_id": "hypothesis-1",
        "recall_snapshot_id": "snapshot-1",
        "previous_intervention_id": "intervention-baseline",
        "proposal": proposal,
        "proposal_digest": semantic_digest(
            "ai-researcher/proposal/v1",
            proposal.model_dump(mode="json"),
        ),
        "resolved_config": None,
        "config_digest": None,
        "intervention_digest": None,
        "manipulation_status": "rejected",
        "violations": ["unknown_knob"],
        "created_at": NOW,
    }

    record = InterventionRecord(**values)

    assert record.proposal.cited_knowledge_ids == ["knowledge-1"]
    with pytest.raises(ValidationError, match="at least one violation"):
        InterventionRecord(**{**values, "violations": []})


def test_knob_change_only_accepts_finite_json_scalars():
    change = KnobChange(
        name="projection_lr_multiplier",
        from_value=1.0,
        to_value=2.0,
    )

    assert change.to_value == 2.0
    with pytest.raises(ValidationError, match="finite"):
        KnobChange(
            name="projection_lr_multiplier",
            from_value=1.0,
            to_value=float("nan"),
        )
    with pytest.raises(ValidationError, match="strict JSON scalar"):
        KnobChange(
            name="projection_lr_multiplier",
            from_value=1.0,
            to_value=Decimal("2.0"),
        )


def test_bool_cannot_substitute_for_a_numeric_knob_value():
    with pytest.raises(ValidationError, match="boolean"):
        KnobChange(
            name="projection_lr_multiplier",
            from_value=1.0,
            to_value=True,
        )


def test_trial_provenance_requires_sha256_identities():
    values = {
        "provenance_id": "provenance-1",
        "attempt_id": "attempt-1",
        "observation_id": "observation-1",
        "intervention_id": "intervention-1",
        "proposal_digest": "a" * 64,
        "intervention_digest": "b" * 64,
        "source_digest": "c" * 64,
        "config_digest": "d" * 64,
        "environment_digest": "e" * 64,
        "dataset_digest": "f" * 64,
        "contract_digest": "0" * 64,
        "evaluator_digest": "1" * 64,
        "attempt_spec_digest": "2" * 64,
        "evidence_digest": "3" * 64,
        "execution_envelope_ref": ArtifactRef(
            path="raw-evidence/attempt_spec.json",
            sha256="4" * 64,
            media_type="application/json",
            size_bytes=512,
        ),
        "created_at": NOW,
    }

    record = TrialProvenanceRecord(**values)

    assert record.source_digest == "c" * 64
    with pytest.raises(ValidationError, match="source_digest"):
        TrialProvenanceRecord(**{**values, "source_digest": "not-a-sha256"})
