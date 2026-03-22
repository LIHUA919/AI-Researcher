from research_agent.inno.evals.bench_runner import BenchmarkRunner, BenchmarkTask
from research_agent.inno.evals.evaluator import build_default_research_evaluator
from research_agent.inno.evals.trace import ResearchRunTrace, RetrievalItem


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
