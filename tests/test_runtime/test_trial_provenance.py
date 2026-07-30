from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import stat

import pytest

from research_agent.inno.experience.intervention import (
    InterventionProposal,
    InterventionRecord,
    semantic_digest,
)
from research_agent.inno.experience.models import ArtifactRef
from research_agent.runtime.adaptive_experiment import TrialPreflight
from research_agent.runtime.trial_provenance import (
    ImmutableEnvelopeConflict,
    atomic_write_canonical_json,
    bind_trial_provenance,
    evidence_bundle_digest,
    content_digest,
    raw_sha256,
)


def test_immutable_json_rejects_existing_symlink_with_matching_bytes(
    tmp_path: Path,
) -> None:
    backing_path = tmp_path / "backing.json"
    backing_path.write_bytes(b'{"attempt_key":"run-1:iteration-001"}')
    envelope_path = tmp_path / "attempt_spec.json"
    envelope_path.symlink_to(backing_path)

    with pytest.raises(ImmutableEnvelopeConflict, match="symlink"):
        atomic_write_canonical_json(
            envelope_path,
            {"attempt_key": "run-1:iteration-001"},
        )


def test_immutable_json_rejects_symlink_in_parent_directory_chain(
    tmp_path: Path,
) -> None:
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ImmutableEnvelopeConflict, match="parent.*symlink"):
        atomic_write_canonical_json(
            linked_parent / "attempt_spec.json",
            {"attempt_key": "run-1:iteration-001"},
        )

    assert not (real_parent / "attempt_spec.json").exists()


def test_immutable_json_revalidates_and_seals_existing_matching_bytes(
    tmp_path: Path,
) -> None:
    envelope_path = tmp_path / "attempt_spec.json"
    expected = b'{"attempt_key":"run-1:iteration-001"}'
    envelope_path.write_bytes(expected)
    envelope_path.chmod(0o644)

    ref = atomic_write_canonical_json(
        envelope_path,
        {"attempt_key": "run-1:iteration-001"},
    )

    assert envelope_path.read_bytes() == expected
    assert stat.S_IMODE(envelope_path.stat().st_mode) == 0o444
    assert ref.sha256 == raw_sha256(expected)
    assert ref.size_bytes == len(expected)


def test_immutable_json_revalidates_and_seals_concurrent_matching_create(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope_path = tmp_path / "attempt_spec.json"
    expected = b'{"attempt_key":"run-1:iteration-001"}'

    def simulate_concurrent_create(
        source: str,
        target: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        del source, src_dir_fd, follow_symlinks
        descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o644,
            dir_fd=dst_dir_fd,
        )
        try:
            os.write(descriptor, expected)
        finally:
            os.close(descriptor)
        raise FileExistsError

    monkeypatch.setattr(
        "research_agent.runtime.trial_provenance.os.link",
        simulate_concurrent_create,
    )

    ref = atomic_write_canonical_json(
        envelope_path,
        {"attempt_key": "run-1:iteration-001"},
    )

    assert envelope_path.read_bytes() == expected
    assert stat.S_IMODE(envelope_path.stat().st_mode) == 0o444
    assert ref.sha256 == raw_sha256(expected)
    assert ref.size_bytes == len(expected)


def test_immutable_json_rejects_concurrently_created_matching_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backing_path = tmp_path / "backing.json"
    backing_path.write_bytes(b'{"attempt_key":"run-1:iteration-001"}')
    envelope_path = tmp_path / "attempt_spec.json"

    def simulate_concurrent_symlink(
        source: str,
        target: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        del source, src_dir_fd, follow_symlinks
        os.symlink(backing_path, target, dir_fd=dst_dir_fd)
        raise FileExistsError

    monkeypatch.setattr(
        "research_agent.runtime.trial_provenance.os.link",
        simulate_concurrent_symlink,
    )

    with pytest.raises(ImmutableEnvelopeConflict, match="symlink"):
        atomic_write_canonical_json(
            envelope_path,
            {"attempt_key": "run-1:iteration-001"},
        )


def test_immutable_json_rejects_parent_path_swap_during_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "attempt"
    displaced_parent = tmp_path / "attempt-displaced"
    parent.mkdir()
    envelope_path = parent / "attempt_spec.json"
    real_link = os.link

    def swap_parent_then_link(
        source: str,
        target: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        parent.rename(displaced_parent)
        parent.mkdir()
        real_link(
            source,
            target,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(
        "research_agent.runtime.trial_provenance.os.link",
        swap_parent_then_link,
    )

    with pytest.raises(
        ImmutableEnvelopeConflict,
        match="parent directory changed",
    ):
        atomic_write_canonical_json(
            envelope_path,
            {"attempt_key": "run-1:iteration-001"},
        )

    assert not envelope_path.exists()
    assert (displaced_parent / envelope_path.name).exists()


def test_content_identity_is_domain_separated_and_byte_exact() -> None:
    payload = b"schema_version: 2\ncontract_id: example\n"

    contract_digest = content_digest(
        "ai-researcher/contract/v1",
        payload,
    )

    assert contract_digest == content_digest(
        "ai-researcher/contract/v1",
        payload,
    )
    assert contract_digest != content_digest(
        "ai-researcher/contract/v1",
        payload + b"\n",
    )
    assert contract_digest != content_digest(
        "ai-researcher/another-content/v1",
        payload,
    )


def test_trial_provenance_binds_verified_evidence_to_its_intervention(
    tmp_path: Path,
) -> None:
    proposal = InterventionProposal(
        domain="synthetic",
        schema_id="synthetic.response-surface/v1",
        decision_point="synthetic.response_surface",
        knob=None,
        target=None,
        cited_knowledge_ids=[],
        expected_primary_metric_direction="unchanged",
        guardrail_risks=[],
        rationale="System-generated baseline.",
    )
    proposal_digest = semantic_digest(
        "ai-researcher/proposal/v1",
        proposal.model_dump(mode="json"),
    )
    effective_config = {
        "dataset_id": "synthetic",
        "gain": 1.0,
        "seed": 401,
    }
    config_digest = semantic_digest(
        "ai-researcher/run-config/v1",
        effective_config,
    )
    intervention_digest = semantic_digest(
        "ai-researcher/intervention/v1",
        {"gain": 1.0},
    )
    intervention = InterventionRecord(
        intervention_id="intervention-1",
        run_id="run-1",
        iteration_id="iteration-001",
        task_id="synthetic:task1",
        hypothesis_id="hypothesis-1",
        recall_snapshot_id="off",
        previous_intervention_id=None,
        proposal=proposal,
        proposal_digest=proposal_digest,
        resolved_config=effective_config,
        config_digest=config_digest,
        intervention_digest=intervention_digest,
        manipulation_status="baseline",
        violations=[],
        created_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
    )
    preflight = TrialPreflight(
        attempt_key="run-1:iteration-001",
        proposal_digest=proposal_digest,
        intervention_digest=intervention_digest,
        config_digest=config_digest,
        source_digest="1" * 64,
        dataset_digest="2" * 64,
        environment_digest="3" * 64,
        contract_digest="4" * 64,
        evaluator_digest="5" * 64,
        attempt_spec_digest="6" * 64,
        effective_config=effective_config,
        manipulation_status="baseline",
    )
    envelope_ref = atomic_write_canonical_json(
        tmp_path / "attempt_spec.json",
        {"attempt_key": preflight.attempt_key},
    )

    provenance = bind_trial_provenance(
        attempt_id="attempt-1",
        observation_id="observation-1",
        intervention=intervention,
        preflight=preflight,
        evidence_digest="7" * 64,
        execution_envelope_ref=envelope_ref,
        created_at=datetime(2026, 7, 30, 1, tzinfo=timezone.utc),
    )

    assert provenance.intervention_id == intervention.intervention_id
    assert provenance.config_digest == intervention.config_digest
    assert provenance.attempt_spec_digest == preflight.attempt_spec_digest
    assert len(provenance.provenance_id) == 64


def test_evidence_bundle_rejects_ambiguous_logical_artifact_names() -> None:
    refs = [
        ArtifactRef(
            path="/attempt-a/run.log",
            sha256="1" * 64,
            size_bytes=10,
        ),
        ArtifactRef(
            path="/attempt-b/run.log",
            sha256="2" * 64,
            size_bytes=20,
        ),
    ]

    try:
        evidence_bundle_digest(refs)
    except ValueError as exc:
        assert "unique logical names" in str(exc)
    else:
        raise AssertionError("ambiguous evidence names must be rejected")
