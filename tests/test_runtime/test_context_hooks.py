import json
from pathlib import Path

from research_agent.runtime import JsonlRuntimeHooks, MasterRuntime, RunContext, refresh_runtime_context_variables


def test_run_context_exports_runtime_payload(tmp_dir):
    run_context = RunContext(
        run_id="run-ctx",
        cache_path=tmp_dir,
        entrypoint="run_infer_plan",
        task_level="task1",
        model="gpt-4o-2024-08-06",
        workplace_name="workplace",
        instance_path="benchmark/example.json",
    )
    context_variables = run_context.to_context_variables(extra={"date_limit": "2024-01-01"})

    assert context_variables["working_dir"] == "workplace"
    assert context_variables["runtime_context"]["run_id"] == "run-ctx"
    assert context_variables["runtime_context"]["entrypoint"] == "run_infer_plan"
    assert context_variables["date_limit"] == "2024-01-01"


def test_refresh_runtime_context_variables_updates_stage_state(tmp_dir):
    run_context = RunContext(
        run_id="run-ctx",
        cache_path=tmp_dir,
        entrypoint="run_infer_plan",
        task_level="task1",
        model="gpt-4o-2024-08-06",
        workplace_name="workplace",
    )
    context_variables = run_context.to_context_variables()
    refresh_runtime_context_variables(
        context_variables,
        run_context,
        {"prepare": {"status": "completed", "artifacts": {}, "metadata": {}}},
    )

    assert context_variables["stage_state"]["prepare"]["status"] == "completed"
    assert context_variables["runtime_context"]["stage_state"]["prepare"]["status"] == "completed"


def test_master_runtime_emits_jsonl_hook_events(tmp_dir):
    runtime = MasterRuntime(tmp_dir, hooks=JsonlRuntimeHooks(tmp_dir))
    runtime.record_stage_completion(
        "prepare",
        artifacts={"prepare_result": f"{tmp_dir}/prepare_stage/prepare_result.json"},
        metadata={"source": "test"},
    )
    runtime.write_runtime_status(run_id="run-hook", status="running")

    events_path = Path(tmp_dir) / "runtime_events.jsonl"
    lines = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]

    assert any(event["event_type"] == "stage_completed" for event in lines)
    assert any(event["event_type"] == "runtime_status_written" for event in lines)
