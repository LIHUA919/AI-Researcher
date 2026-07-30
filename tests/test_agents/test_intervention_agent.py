import asyncio

import pytest

from research_agent.inno.agents.inno_agent.intervention_agent import (
    StructuredLLMInterventionPlanner,
    get_intervention_agent,
)
from research_agent.inno.experience import (
    AdaptiveExperimentPolicy,
    Hypothesis,
    InterventionKnob,
    semantic_digest,
)
from research_agent.runtime.adaptive_experiment import (
    InterventionPlanningContext,
    InterventionProposalError,
    PreviousAttemptFeedback,
)


def test_intervention_agent_can_only_submit_one_schema_bound_decision():
    agent = get_intervention_agent(model="test-model")

    assert [function.__name__ for function in agent.functions] == [
        "submit_intervention"
    ]
    assert agent.tool_choice == "required"
    assert agent.parallel_tool_calls is False
    assert agent.max_turns == 2

    instructions = agent.instructions(
        {
            "intervention_catalog": {
                "decision_point": "vq.quantizer_optimization",
                "knobs": {"commitment_weight": [0.1, 0.25, 0.5]},
            },
            "previous_attempt_feedback": {
                "verified_metrics": {"codebook_utilization": 0.25}
            },
            "recall_context": {"items": []},
        }
    )
    assert "one allowlisted knob" in instructions
    assert "must not propose seed" in instructions
    assert "previous verified feedback" in instructions


class _RepairingAgentModule:
    def __init__(self):
        self.calls = 0

    async def __call__(self, messages, context_variables, iter_times=None):
        self.calls += 1
        proposal = {
            "decision_point": "vq.quantizer_optimization",
            "knob": "not_allowlisted" if self.calls == 1 else "commitment_weight",
            "target": 0.5,
            "cited_knowledge_ids": [],
            "expected_primary_metric_direction": "increase",
            "guardrail_risks": [],
            "rationale": "Exercise exactly one governed quantizer parameter.",
        }
        usage = dict(context_variables.get("llm_usage") or {})
        usage["calls"] = int(usage.get("calls", 0)) + 1
        return messages, {
            **context_variables,
            "submitted_intervention": proposal,
            "llm_usage": usage,
        }


def _planning_context():
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
    config = {
        "dataset_id": "cifar10",
        "commitment_weight": 0.25,
        "seed": 401,
    }
    return InterventionPlanningContext(
        hypothesis=Hypothesis(
            hypothesis_id="hypothesis-1",
            task_id="one_layer_vq:task1",
            statement="Increase codebook utilization.",
            mechanism="A different commitment pressure changes assignments.",
            expected_metric="codebook_utilization",
            metric_direction="maximize",
        ),
        policy=policy,
        previous=PreviousAttemptFeedback(
            attempt_id="attempt-1",
            intervention_id="intervention-1",
            config_digest=semantic_digest(
                "ai-researcher/run-config/v1",
                config,
            ),
            effective_config=config,
            verified_metrics={"codebook_utilization": 0.2},
            outcome="negative",
            guardrail_violations=[],
        ),
        recall_context=None,
    )


def test_structured_planner_repairs_once_and_returns_system_bound_proposal():
    module = _RepairingAgentModule()
    planner = StructuredLLMInterventionPlanner(
        agent_module=module,
        domain="vq",
        schema_id="one-layer-vq-phase-a@1",
    )

    proposal = asyncio.run(planner.propose(_planning_context()))

    assert module.calls == 2
    assert proposal.domain == "vq"
    assert proposal.schema_id == "one-layer-vq-phase-a@1"
    assert proposal.knob == "commitment_weight"
    assert proposal.target == 0.5
    assert planner.last_llm_usage["calls"] == 2


class _AlwaysInvalidAgentModule:
    async def __call__(self, messages, context_variables, iter_times=None):
        return messages, {
            **context_variables,
            "submitted_intervention": {
                "decision_point": "vq.quantizer_optimization",
                "knob": "commitment_weight",
                "target": 9.0,
                "cited_knowledge_ids": [],
                "expected_primary_metric_direction": "increase",
                "guardrail_risks": [],
                "rationale": "Invalid outside-catalog value.",
            },
        }


def test_structured_planner_fails_closed_after_one_repair():
    planner = StructuredLLMInterventionPlanner(
        agent_module=_AlwaysInvalidAgentModule(),
        domain="vq",
        schema_id="one-layer-vq-phase-a@1",
    )

    with pytest.raises(InterventionProposalError):
        asyncio.run(planner.propose(_planning_context()))
