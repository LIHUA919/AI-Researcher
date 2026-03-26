import json

from research_agent.inno.evals import (
    build_and_save_eval_result,
    build_research_run_trace,
    save_eval_artifacts,
)
from research_agent.inno.evals.bench_runner import (
    AsyncBenchmarkRunner,
    BenchmarkRunner,
    BenchmarkTask,
)
from research_agent.inno.evals.evaluator import build_default_research_evaluator
from research_agent.inno.evals.trace import ResearchRunTrace, RetrievalItem
from research_agent.inno.evals.trace import AgentStepTrace, ToolCallTrace
from research_agent.inno_common import build_plan_result


def _make_trace(task: BenchmarkTask) -> ResearchRunTrace:
    trace = ResearchRunTrace(
        run_id="run-1",
        task_id=task.task_id,
        query=task.query,
        goal=task.goal,
        claims=["the model uses vector quantization"],
        plan={
            "dataset": {"name": "ImageNet"},
            "model": {"architecture": "VQ-VAE"},
            "training": {"loss": "reconstruction"},
            "testing": {"metric": "fid"},
        },
    )
    trace.add_retrieval(
        RetrievalItem(
            source_type="paper",
            identifier="paper-1",
            title="The model uses vector quantization",
            content="The model uses vector quantization in the bottleneck.",
        )
    )
    return trace


def test_goal_driven_evaluator_passes_complete_trace():
    evaluator = build_default_research_evaluator("deliver an executable research plan")
    task = BenchmarkTask(
        task_id="task-1",
        query="build a VQ plan",
        goal="deliver an executable research plan",
    )
    runner = BenchmarkRunner(evaluator=evaluator, run_fn=_make_trace)

    report = runner.run_task(task)

    assert report.passed is True
    assert report.failure_reasons == []


def test_goal_driven_evaluator_emits_next_actions_on_failure():
    evaluator = build_default_research_evaluator("deliver an executable research plan")
    task = BenchmarkTask(task_id="task-2", query="bad trace", goal="same")

    def bad_trace(_: BenchmarkTask) -> ResearchRunTrace:
        return ResearchRunTrace(
            run_id="run-2",
            task_id="task-2",
            query="bad trace",
            claims=["unsupported claim"],
            plan={"dataset": {"name": "x"}},
        )

    report = BenchmarkRunner(evaluator=evaluator, run_fn=bad_trace).run_task(task)

    assert report.passed is False
    assert any("evidence" in reason for reason in report.failure_reasons)
    assert any("Fill missing plan sections" in action for action in report.next_actions)


def test_evaluator_prefers_trace_goal():
    evaluator = build_default_research_evaluator("evaluator default goal")
    trace = _make_trace(
        BenchmarkTask(task_id="task-3", query="q", goal="trace goal")
    )

    report = evaluator.evaluate(trace)

    assert report.goal == "trace goal"


def test_evaluator_falls_back_to_evaluator_goal_when_trace_goal_empty():
    evaluator = build_default_research_evaluator("evaluator default goal")
    trace = ResearchRunTrace(run_id="r4", task_id="task-4", query="q")

    report = evaluator.evaluate(trace)

    assert report.goal == "evaluator default goal"


async def _async_make_trace(task: BenchmarkTask) -> ResearchRunTrace:
    return _make_trace(task)


def test_async_benchmark_runner_run_task():
    import asyncio

    evaluator = build_default_research_evaluator("deliver an executable research plan")
    runner = AsyncBenchmarkRunner(evaluator=evaluator, run_fn=_async_make_trace)
    task = BenchmarkTask(task_id="task-5", query="build a VQ plan", goal="goal")

    report = asyncio.run(runner.run_task(task))

    assert report.passed is True
    assert report.task_id == "task-5"


def test_async_benchmark_runner_run_many_preserves_order():
    import asyncio

    evaluator = build_default_research_evaluator("deliver an executable research plan")
    runner = AsyncBenchmarkRunner(evaluator=evaluator, run_fn=_async_make_trace)
    tasks = [
        BenchmarkTask(task_id="task-a", query="a", goal="goal-a"),
        BenchmarkTask(task_id="task-b", query="b", goal="goal-b"),
    ]

    reports = asyncio.run(runner.run_many(tasks))

    assert [report.task_id for report in reports] == ["task-a", "task-b"]


def test_build_research_run_trace_adapter_sets_minimal_fields():
    trace = build_research_run_trace(
        run_id="run-adapter",
        task_id="task-adapter",
        query="query",
        goal="goal",
        claims=["1. First claim.\n\n2. Second claim with more detail."],
        plan={"dataset": {"name": "x"}},
        final_output={"summary": "done"},
        metadata={"source": "run_infer_plan"},
    )

    assert trace.run_id == "run-adapter"
    assert trace.task_id == "task-adapter"
    assert trace.goal == "goal"
    assert trace.claims == ["First claim.", "Second claim with more detail."]
    assert trace.plan == {"dataset": {"name": "x"}}
    assert trace.final_output == {"summary": "done"}
    assert trace.metadata == {"source": "run_infer_plan"}
    assert trace.tool_calls == []
    assert trace.agent_steps == []
    assert len(trace.retrieved_items) == 2


def test_build_research_run_trace_preserves_runtime_trace():
    trace = build_research_run_trace(
        run_id="run-runtime",
        task_id="task-runtime",
        query="query",
        tool_calls=[
            ToolCallTrace(
                agent_name="Flow",
                tool_name="github_search",
                output_summary="retrieved repos",
            )
        ],
        agent_steps=[
            AgentStepTrace(
                agent_name="Survey Agent",
                input_summary="input",
                output_summary="output",
            )
        ],
    )

    assert len(trace.tool_calls) == 1
    assert trace.tool_calls[0].tool_name == "github_search"
    assert len(trace.agent_steps) == 1
    assert trace.agent_steps[0].agent_name == "Survey Agent"


def test_save_eval_artifacts_writes_trace_and_report(tmp_dir):
    trace = build_research_run_trace(
        run_id="run-artifacts",
        task_id="task-artifacts",
        query="query",
        goal="goal",
        claims=["claim"],
        plan={"dataset": {"name": "x"}},
        final_output={"summary": "done"},
    )
    report = build_default_research_evaluator("goal").evaluate(trace)

    paths = save_eval_artifacts(tmp_dir, trace, report)

    with open(paths["trace_path"], "r", encoding="utf-8") as f:
        trace_payload = json.load(f)
    with open(paths["report_path"], "r", encoding="utf-8") as f:
        report_payload = json.load(f)

    assert trace_payload["task_id"] == "task-artifacts"
    assert report_payload["goal"] == "goal"


def test_build_and_save_eval_result_creates_bundle(tmp_dir):
    result = build_and_save_eval_result(
        {
            "task_id": "task-bundle",
            "query": "query",
            "goal": "goal",
            "claims": ["claim"],
            "plan": {"dataset": {"name": "x"}},
            "final_output": {"summary": "done"},
            "metadata": {"source": "flow"},
        },
        tmp_dir,
    )

    assert result["flow_result"]["task_id"] == "task-bundle"
    assert result["eval_trace"].task_id == "task-bundle"
    assert result["eval_report"].goal == "goal"
    assert result["artifact_paths"]["trace_path"].endswith("trace.json")


def test_build_plan_result_prefers_structured_plan_sections():
    plan_res = "def forward(self): pass"
    context_variables = {
        "dataset_plan": {"dataset_description": "CIFAR-10"},
        "model_survey": "Use a one-layer VQ bottleneck.",
        "training_plan": {"loss_function": "reconstruction + commitment"},
        "testing_plan": {"test_metric": "bits/dim"},
    }

    normalized = build_plan_result(plan_res, context_variables)

    assert normalized != plan_res
    assert "# Dataset Plan" in normalized
    assert "CIFAR-10" in normalized
    assert "# Training Plan" in normalized
    assert "reconstruction + commitment" in normalized
    assert "# Testing Plans" in normalized


def test_build_plan_result_falls_back_when_no_structured_plan_sections():
    plan_res = "raw tool output"

    normalized = build_plan_result(plan_res, {})

    assert normalized == plan_res
