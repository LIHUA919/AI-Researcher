from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from typing import Annotated, Any, Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator
from pydantic import model_validator

from research_agent.inno.experience.models import ArtifactRef, ImmutableModel


Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
JsonScalar = StrictStr | StrictInt | StrictFloat | StrictBool | None


def semantic_digest(domain: str, value: Any) -> str:
    """Return a domain-separated SHA-256 digest of canonical JSON."""
    _validate_json_value(value)
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(domain.encode("ascii") + b"\0" + payload).hexdigest()


def _validate_json_value(value: object) -> None:
    if value is None or type(value) in {str, int, float, bool}:
        _validate_scalar(value)
        return
    if type(value) is list:
        for item in value:
            _validate_json_value(item)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("semantic digest requires strict JSON string keys")
            _validate_json_value(item)
        return
    raise ValueError("semantic digest requires strict JSON values")


def _validate_scalar(value: object) -> object:
    if value is not None and type(value) not in {str, int, float, bool}:
        raise ValueError(
            "value must be a strict JSON scalar without implicit conversion"
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON scalar floats must be finite")
    return value


class KnobChange(ImmutableModel):
    name: str
    from_value: JsonScalar
    to_value: JsonScalar

    _from_value_is_finite = field_validator("from_value", mode="before")(
        _validate_scalar
    )
    _to_value_is_finite = field_validator("to_value", mode="before")(
        _validate_scalar
    )

    @model_validator(mode="after")
    def boolean_is_not_a_numeric_value(self) -> "KnobChange":
        values = (self.from_value, self.to_value)
        has_bool = any(isinstance(value, bool) for value in values)
        has_number = any(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in values
        )
        if has_bool and has_number:
            raise ValueError("boolean cannot substitute for a numeric knob value")
        return self


class InterventionProposal(ImmutableModel):
    domain: str
    schema_id: str
    decision_point: str
    knob: str | None
    target: JsonScalar
    cited_knowledge_ids: list[str]
    expected_primary_metric_direction: Literal["increase", "decrease", "unchanged"]
    guardrail_risks: list[str]
    rationale: str

    _target_is_finite = field_validator("target", mode="before")(_validate_scalar)

    @field_validator("cited_knowledge_ids")
    @classmethod
    def deduplicate_citations(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))


class InterventionRecord(ImmutableModel):
    intervention_id: str
    run_id: str
    iteration_id: str
    task_id: str
    hypothesis_id: str
    recall_snapshot_id: str
    previous_intervention_id: str | None
    proposal: InterventionProposal
    proposal_digest: Sha256
    resolved_config: dict[str, JsonScalar] | None
    config_digest: Sha256 | None
    intervention_digest: Sha256 | None
    manipulation_status: Literal["baseline", "changed", "no_effect", "rejected"]
    violations: list[str]
    created_at: datetime

    @field_validator("resolved_config", mode="before")
    @classmethod
    def resolved_config_is_finite(
        cls,
        value: object,
    ) -> object:
        if isinstance(value, dict):
            for item in value.values():
                _validate_scalar(item)
        return value

    @model_validator(mode="after")
    def validate_disposition(self) -> "InterventionRecord":
        expected_proposal_digest = semantic_digest(
            "ai-researcher/proposal/v1",
            self.proposal.model_dump(mode="json"),
        )
        if self.proposal_digest != expected_proposal_digest:
            raise ValueError("proposal_digest does not match proposal")

        if self.manipulation_status == "baseline":
            if self.previous_intervention_id is not None:
                raise ValueError("baseline cannot have a previous intervention")
            if self.proposal.knob is not None or self.proposal.target is not None:
                raise ValueError("baseline proposal cannot select a knob or target")
        elif self.manipulation_status in {"changed", "no_effect"}:
            if self.previous_intervention_id is None:
                raise ValueError(
                    f"{self.manipulation_status} requires a previous intervention"
                )
            if self.proposal.knob is None:
                raise ValueError(
                    f"{self.manipulation_status} proposal must select a knob"
                )

        if self.manipulation_status == "rejected":
            if (
                self.resolved_config is not None
                or self.config_digest is not None
                or self.intervention_digest is not None
            ):
                raise ValueError("rejected intervention cannot have resolved digests")
            if not self.violations:
                raise ValueError("rejected intervention requires at least one violation")
            return self

        if (
            self.resolved_config is None
            or self.config_digest is None
            or self.intervention_digest is None
        ):
            raise ValueError(
                "accepted intervention requires resolved_config and all resolved digests"
            )
        if self.violations:
            raise ValueError("accepted intervention cannot have violations")
        expected_config_digest = semantic_digest(
            "ai-researcher/run-config/v1",
            self.resolved_config,
        )
        if self.config_digest != expected_config_digest:
            raise ValueError("config_digest does not match resolved_config")
        return self


class TrialProvenanceRecord(ImmutableModel):
    provenance_id: str
    attempt_id: str
    observation_id: str
    intervention_id: str
    proposal_digest: Sha256
    intervention_digest: Sha256
    source_digest: Sha256
    config_digest: Sha256
    environment_digest: Sha256
    dataset_digest: Sha256
    contract_digest: Sha256
    evaluator_digest: Sha256
    attempt_spec_digest: Sha256
    evidence_digest: Sha256
    execution_envelope_ref: ArtifactRef
    created_at: datetime


def validate_content_derived_intervention_id(
    record: InterventionRecord,
) -> None:
    """Validate production digest IDs while retaining legacy named IDs."""

    if not _looks_like_sha256(record.intervention_id):
        return
    prefix = "iteration-"
    if (
        not record.iteration_id.startswith(prefix)
        or not record.iteration_id.removeprefix(prefix).isdigit()
    ):
        raise ValueError(
            "content-derived intervention_id requires a numeric iteration_id"
        )
    expected = semantic_digest(
        "ai-researcher/intervention-record-id/v1",
        {
            "run_id": record.run_id,
            "iteration_number": int(record.iteration_id.removeprefix(prefix)),
            "proposal_digest": record.proposal_digest,
            "manipulation_status": record.manipulation_status,
            "intervention_digest": record.intervention_digest,
            "config_digest": record.config_digest,
        },
    )
    if record.intervention_id != expected:
        raise ValueError("content-derived intervention_id does not match record")


def validate_content_derived_provenance_id(
    record: TrialProvenanceRecord,
) -> None:
    """Validate production digest IDs while retaining legacy named IDs."""

    if not _looks_like_sha256(record.provenance_id):
        return
    expected = semantic_digest(
        "ai-researcher/trial-provenance-id/v1",
        {
            "attempt_id": record.attempt_id,
            "observation_id": record.observation_id,
            "intervention_id": record.intervention_id,
            "proposal_digest": record.proposal_digest,
            "intervention_digest": record.intervention_digest,
            "source_digest": record.source_digest,
            "config_digest": record.config_digest,
            "environment_digest": record.environment_digest,
            "dataset_digest": record.dataset_digest,
            "contract_digest": record.contract_digest,
            "evaluator_digest": record.evaluator_digest,
            "attempt_spec_digest": record.attempt_spec_digest,
            "evidence_digest": record.evidence_digest,
            "execution_envelope": {
                "sha256": record.execution_envelope_ref.sha256,
                "size_bytes": record.execution_envelope_ref.size_bytes,
            },
        },
    )
    if record.provenance_id != expected:
        raise ValueError("content-derived provenance_id does not match record")


def _looks_like_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
