import json
from types import SimpleNamespace

from benchmark.run_model_experience_smoke import (
    OpenAICompatibleOperatorSelector,
)
from research_agent.inno.evals import TrialConfiguration
from research_agent.inno.experience import (
    RecallContext,
    RecallItem,
    RecallRequest,
)


def test_model_selector_includes_cited_verified_evidence_and_tracks_usage():
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        tool_calls=[
                            SimpleNamespace(
                                function=SimpleNamespace(
                                    arguments=json.dumps(
                                        {
                                            "operator": "identity",
                                            "reason": "square was verified negative",
                                        }
                                    )
                                )
                            )
                        ]
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=5),
        )

    selector = OpenAICompatibleOperatorSelector.__new__(
        OpenAICompatibleOperatorSelector
    )
    selector.model = "test-model"
    selector.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )
    request = RecallRequest(
        query="select",
        task_id="operator-selection-model-smoke",
        domain="external-model-behavioral-smoke",
        dataset_id="hidden-identity-transform@1",
        model_family="test-model",
    )
    recall = RecallContext(
        snapshot_id="snapshot",
        memory_snapshot_id="memory",
        request=request,
        items=[
            RecallItem(
                citation_id="knowledge:negative-square",
                knowledge_id="negative-square",
                lesson=(
                    "Do not repeat operator `square` if its independently "
                    "verified outcome is negative."
                ),
                outcome="negative",
                source_experience_ids=["experience-1"],
                score=1.0,
                score_breakdown={"relevance": 1.0},
                token_count=20,
            )
        ],
        token_count=20,
    )
    config = TrialConfiguration(
        task_id=request.task_id,
        mode="closed-loop",
        seed=1,
        model="test-model",
        budget={"iterations": 2},
        evaluator_version="operator-selection-identity@1",
        dataset_digest=request.dataset_id,
        code_revision="test",
    )

    selection = selector(config, recall)

    assert selection.operator == "identity"
    assert selection.tokens == 25
    assert "knowledge:negative-square" in captured["messages"][1]["content"]
    assert captured["tool_choice"] == "required"
