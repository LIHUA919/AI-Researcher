from __future__ import annotations

import copy
import json
from typing import Any, Literal, Protocol

from pydantic import ValidationError

from research_agent.inno.experience.intervention import InterventionProposal
from research_agent.inno.types import Agent, Result
from research_agent.runtime.adaptive_experiment import (
    InterventionPlanningContext,
    InterventionProposalError,
)


def submit_intervention(
    decision_point: str,
    knob: str,
    target: float,
    cited_knowledge_ids: list[str],
    expected_primary_metric_direction: Literal[
        "increase",
        "decrease",
        "unchanged",
    ],
    guardrail_risks: list[str],
    rationale: str,
) -> Result:
    """Return the sole typed decision that the orchestrator may validate."""

    payload = {
        "decision_point": decision_point,
        "knob": knob,
        "target": target,
        "cited_knowledge_ids": cited_knowledge_ids,
        "expected_primary_metric_direction": (
            expected_primary_metric_direction
        ),
        "guardrail_risks": guardrail_risks,
        "rationale": rationale,
    }
    return Result(
        value=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        context_variables={"submitted_intervention": payload},
    )


class _AgentModule(Protocol):
    async def __call__(
        self,
        messages: list[dict[str, str]],
        context_variables: dict[str, Any],
        iter_times: Any = None,
    ) -> tuple[list[dict], dict[str, Any]]: ...


class FixedInterventionPlanner:
    """Deterministic planner for dry runs and Interface tests."""

    def __init__(self, proposal: InterventionProposal) -> None:
        self.proposal = proposal
        self.invocation_count = 0

    async def propose(
        self,
        context: InterventionPlanningContext,
    ) -> InterventionProposal:
        self.invocation_count += 1
        return self.proposal


class StructuredLLMInterventionPlanner:
    """Translate one tool-only Agent call into a policy-bound proposal."""

    def __init__(
        self,
        *,
        agent_module: _AgentModule,
        domain: str,
        schema_id: str,
    ) -> None:
        self.agent_module = agent_module
        self.domain = domain
        self.schema_id = schema_id
        self.last_llm_usage: dict[str, Any] = {}

    async def propose(
        self,
        context: InterventionPlanningContext,
    ) -> InterventionProposal:
        context_variables = {
            "intervention_catalog": context.policy.model_dump(mode="json"),
            "previous_attempt_feedback": context.previous.model_dump(mode="json"),
            "recall_context": (
                context.recall_context.model_dump(mode="json")
                if context.recall_context is not None
                else {"items": []}
            ),
        }
        messages: list[dict[str, str]] = [
            {
                "role": "user",
                "content": (
                    "Select one catalog intervention for the next verified "
                    "Experiment Attempt and submit it with the required tool."
                ),
            }
        ]
        last_error = "missing structured tool result"
        self.last_llm_usage = {}
        for invocation in range(2):
            messages, returned_context = await self.agent_module(
                messages,
                dict(context_variables),
                iter_times=f"intervention-{invocation + 1}",
            )
            context_variables = returned_context
            self.last_llm_usage = copy.deepcopy(
                returned_context.get("llm_usage") or {}
            )
            raw = returned_context.get("submitted_intervention")
            try:
                proposal = self._validate_submission(raw, context)
            except (TypeError, ValueError, ValidationError) as exc:
                last_error = str(exc)
                if invocation == 0:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "The submitted intervention violated the catalog. "
                                "Repair it once using exactly one allowed knob, an "
                                "exact allowed target, and only supplied citations."
                            ),
                        }
                    )
                    continue
                break
            return proposal
        raise InterventionProposalError(
            "invalid structured intervention after one repair: "
            f"{last_error}"
        )

    def _validate_submission(
        self,
        raw: Any,
        context: InterventionPlanningContext,
    ) -> InterventionProposal:
        if not isinstance(raw, dict):
            raise TypeError("tool result must be an object")
        proposal = InterventionProposal.model_validate(
            {
                "domain": self.domain,
                "schema_id": self.schema_id,
                **raw,
            }
        )
        policy = context.policy
        if proposal.decision_point != policy.decision_point:
            raise ValueError("decision point is not allowed")
        if proposal.knob not in policy.knobs:
            raise ValueError("knob is not allowlisted")
        target = proposal.target
        if (
            isinstance(target, bool)
            or not isinstance(target, (int, float))
            or float(target) not in policy.knobs[proposal.knob].allowed_values
        ):
            raise ValueError("target is not an exact allowed value")
        allowed_citations = {
            item.knowledge_id
            for item in (
                context.recall_context.items
                if context.recall_context is not None
                else []
            )
        }
        if any(
            citation not in allowed_citations
            for citation in proposal.cited_knowledge_ids
        ):
            raise ValueError("proposal cites Knowledge outside Recall Context")
        if not proposal.rationale.strip():
            raise ValueError("rationale must not be empty")
        narrative = " ".join(
            [proposal.rationale, *proposal.guardrail_risks]
        ).lower()
        forbidden_fragments = {
            "--",
            "python ",
            "seed",
            "dataset_id",
            "train_split",
            "test_split",
            "train_samples",
            "test_samples",
            "epochs",
            "batch_size",
            "codebook_size",
            "latent_dim",
            "quantizer_variant",
            "base_learning_rate",
            "device_policy",
            "evaluator",
            "attempt_spec",
        }
        if (
            "/" in narrative
            or "\\" in narrative
            or any(fragment in narrative for fragment in forbidden_fragments)
        ):
            raise ValueError(
                "proposal narrative contains a command, path, or fixed field"
            )
        return proposal


def get_intervention_agent(model: str) -> Agent:
    def instructions(context_variables: dict) -> str:
        catalog = json.dumps(
            context_variables.get("intervention_catalog") or {},
            ensure_ascii=False,
            sort_keys=True,
        )
        previous = json.dumps(
            context_variables.get("previous_attempt_feedback") or {},
            ensure_ascii=False,
            sort_keys=True,
        )
        recall = json.dumps(
            context_variables.get("recall_context") or {"items": []},
            ensure_ascii=False,
            sort_keys=True,
        )
        return f"""\
You are the Intervention Planner for one verified Experiment Attempt.

Choose exactly one allowlisted knob and target at the declared decision point,
then call `submit_intervention`. The orchestrator, not you, derives from_value,
the complete effective config, IDs, digests, and execution command.

You must not propose seed, dataset, split, sample counts, epochs, batch size,
codebook size, latent dimension, quantizer variant, base learning rate,
device policy, evaluator settings, evidence settings, paths, or source edits.
Do not invent Knowledge citations. Every cited ID must occur in the supplied
Recall Context. If Recall Context is empty, cited_knowledge_ids must be empty.
Use the previous verified feedback, including verified metrics and guardrail
violations, as immediate feedback for the next decision.

Intervention Catalog:
{catalog}

Previous verified feedback:
{previous}

Recall Context:
{recall}
"""

    return Agent(
        name="Intervention Planner",
        model=model,
        instructions=instructions,
        functions=[submit_intervention],
        tool_choice="required",
        parallel_tool_calls=False,
        max_turns=2,
    )
