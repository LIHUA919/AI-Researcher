from research_agent.inno.evals.metrics import evidence_coverage, plan_executability
from research_agent.inno.evals.trace import ResearchRunTrace, RetrievalItem, ToolCallTrace


def test_evidence_coverage_scores_supported_claims():
    trace = ResearchRunTrace(
        run_id="r1",
        task_id="t1",
        query="test",
        claims=["vector quantization improves compression", "uses contrastive loss"],
    )
    trace.add_retrieval(
        RetrievalItem(
            source_type="paper",
            identifier="p1",
            title="Vector quantization improves compression",
            content="This paper shows vector quantization improves compression.",
        )
    )
    trace.add_tool_call(
        ToolCallTrace(
            agent_name="Survey Agent",
            tool_name="paper_search",
            output_summary="The method uses contrastive loss for representation learning.",
        )
    )

    result = evidence_coverage(trace)

    assert result["score"] == 1.0
    assert result["unsupported_claims"] == []


def test_evidence_coverage_ignores_failed_tool_calls():
    trace = ResearchRunTrace(
        run_id="r2",
        task_id="t2",
        query="test",
        claims=["uses contrastive loss"],
    )
    trace.add_tool_call(
        ToolCallTrace(
            agent_name="Survey Agent",
            tool_name="paper_search",
            success=False,
            output_summary="The method uses contrastive loss for representation learning.",
            error_message="upstream tool failed",
        )
    )

    result = evidence_coverage(trace)

    assert result["score"] == 0.0
    assert result["unsupported_claims"] == ["uses contrastive loss"]


def test_evidence_coverage_empty_claims_scores_full():
    trace = ResearchRunTrace(run_id="r3", task_id="t3", query="test")

    result = evidence_coverage(trace)

    assert result["score"] == 1.0
    assert result["supported_claims"] == []
    assert result["unsupported_claims"] == []


def test_plan_executability_reports_missing_sections():
    plan = {
        "dataset": {"name": "CIFAR-10"},
        "model": {"architecture": "ResNet"},
        "training": {},
    }

    result = plan_executability(plan)

    assert result["score"] == 0.5
    assert "testing" in result["missing_sections"]
