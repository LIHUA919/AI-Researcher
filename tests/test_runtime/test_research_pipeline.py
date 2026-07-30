from pathlib import Path

from research_agent.inno.experience import RecallContext, RecallItem, RecallRequest
from research_agent.runtime import (
    ProvidedIdeaStrategy,
    ReferenceIdeationStrategy,
    ResearchPipeline,
    RunRequest,
    implementation_ready,
    render_recall_guidance,
    write_stage_artifact,
)


def run_request(tmp_path, *, intent="Use a learned transform"):
    return RunRequest(
        run_id="run-1",
        task_id="task-1",
        entrypoint="test",
        task_level="task1",
        model="model",
        workplace_name="workplace",
        cache_path=str(tmp_path),
        intent=intent,
        expected_metric="score",
        conditions=["cifar10"],
    )


def write_artifacts(root: Path):
    project = root / "project"
    project.mkdir()
    script = project / "run_training_testing.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    artifacts = {
        "prepare": [
            (
                "prepare_stage/prepare_result.json",
                {
                    "reference_papers": ["paper"],
                    "reference_paths": ["/repo"],
                },
            )
        ],
        "survey": [
            ("survey_stage/survey_result.json", {"survey_report": "survey"})
        ],
        "plan": [
            ("plan_stages/dataset_plan.json", {"dataset_description": "dataset"}),
            ("plan_stages/training_plan.json", {"training_pipeline": "train"}),
            ("plan_stages/testing_plan.json", {"test_metric": "score"}),
            ("plan_stages/plan_report.json", {"plan_report": "plan"}),
        ],
        "implement": [
            (
                "implement_stage/project_manifest.json",
                {
                    "project_manifest": {
                        "project_root": str(project),
                        "exists": True,
                        "key_paths": {"main_script": str(script)},
                    }
                },
            )
        ],
        "judge": [("judge_stage/judge_report.json", {"judge_report": "pass"})],
        "submit": [("submit_stage/submit_result.json", {"submit_result": "score=1"})],
        "analyze": [
            ("analyze_stage/analysis_report.json", {"analysis_report": "analysis"})
        ],
    }
    for stage, stage_artifacts in artifacts.items():
        for relative_path, payload in stage_artifacts:
            write_stage_artifact(root / relative_path, stage=stage, payload=payload)


def test_shared_pipeline_enforces_stage_order_and_finalizes(tmp_path):
    write_artifacts(tmp_path)
    pipeline = ResearchPipeline.start(run_request(tmp_path))

    for stage in (
        "prepare",
        "survey",
        "plan",
        "implement",
        "judge",
        "submit",
        "analyze",
    ):
        pipeline.complete_stage(stage)
        pipeline.progress()

    result = pipeline.finalize()

    assert result.all_criteria_met is True
    assert pipeline.run_context.stage_state["analyze"]["status"] == "completed"


def test_both_intent_strategies_cross_the_same_hypothesis_interface(tmp_path):
    request = run_request(tmp_path)
    recall = RecallContext(
        snapshot_id="snapshot-1",
        memory_snapshot_id="memory-1",
        request=RecallRequest(
            query="q",
            task_id="task-1",
            domain="vision",
            dataset_id="cifar10",
            model_family="vq",
        ),
        items=[
            RecallItem(
                citation_id="knowledge:k1",
                knowledge_id="k1",
                lesson="Avoid the unstable baseline.",
                outcome="negative",
                source_experience_ids=["experience-1"],
                score=1.0,
                score_breakdown={"relevance": 1.0},
                token_count=5,
            )
        ],
        token_count=5,
    )

    provided = ProvidedIdeaStrategy().build_hypothesis(request, recall)
    reference = ReferenceIdeationStrategy().build_hypothesis(request, recall)

    assert provided.statement == request.intent
    assert reference.statement == request.intent
    assert provided.parent_experience_ids == ["experience-1"]
    assert reference.parent_experience_ids == ["experience-1"]
    assert provided.citations == ["knowledge:k1"]
    assert provided.mechanism != reference.mechanism


def test_implementation_readiness_uses_typed_judge_state_not_prose():
    assert implementation_ready(
        {"suggestion_dict": {"fully_correct": True, "suggestion": None}}
    )
    assert not implementation_ready(
        {"final_output": '{"fully_correct": true}'}
    )


def test_recall_context_becomes_cited_decision_guidance(tmp_path):
    request = run_request(tmp_path)
    recall = RecallContext(
        snapshot_id="snapshot-1",
        memory_snapshot_id="memory-1",
        request=RecallRequest(
            query="q",
            task_id=request.task_id,
            domain="vision",
            dataset_id="cifar10",
            model_family="vq",
        ),
        items=[
            RecallItem(
                citation_id="knowledge:k1",
                knowledge_id="k1",
                lesson="Do not reuse the unstable optimizer.",
                outcome="negative",
                source_experience_ids=["experience-1"],
                score=1.0,
                score_breakdown={"relevance": 1.0},
                token_count=7,
            )
        ],
        token_count=7,
    )

    guidance = render_recall_guidance(recall)

    assert "knowledge:k1" in guidance
    assert "negative" in guidance
    assert "Do not reuse the unstable optimizer." in guidance
    assert "revise the current Hypothesis" in guidance
