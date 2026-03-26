import json
from argparse import Namespace
from pathlib import Path

from research_agent.runtime.soak import (
    build_run_command,
    build_soak_env,
    compute_cache_path,
    load_stage_events,
    summarize_stage_events,
)


def test_compute_cache_path_uses_requested_model_suffix():
    cache_path = compute_cache_path("cache_soak", "one_layer_vq", "openai/gpt-4o-2024-08-06")

    assert cache_path == "cache_soak_one_layer_vq_openai__gpt-4o-2024-08-06"


def test_build_run_command_includes_required_arguments():
    args = Namespace(
        python_bin=".venv/bin/python",
        entry_script="research_agent/run_infer_plan.py",
        instance_path="benchmark/final/vq/one_layer_vq.json",
        task_level="task1",
        model="gpt-4o-2024-08-06",
        workplace_name="workplace",
        cache_prefix="cache_soak",
        port=12345,
        max_iter_times=0,
        category="vq",
        container_name="paper_eval",
    )

    command = build_run_command(args)

    assert command[0] == ".venv/bin/python"
    assert "--instance_path" in command
    assert "benchmark/final/vq/one_layer_vq.json" in command
    assert "--category" in command
    assert "vq" in command


def test_build_soak_env_defaults_model_fallbacks_to_primary_model():
    args = Namespace(
        llm_timeout=180,
        llm_retry_attempts=3,
        llm_retry_backoff_seconds=5,
        model_fallbacks="",
        model="gpt-4o-2024-08-06",
    )

    env = build_soak_env(args)

    assert env["AUTO_SELECT_FIRST_OPTION"] == "1"
    assert env["MODEL_FALLBACKS"] == "gpt-4o-2024-08-06"


def test_load_stage_events_reads_jsonl(tmp_path):
    events_path = Path(tmp_path) / "stage_events.jsonl"
    events_path.write_text(
        "\n".join(
            [
                json.dumps({"timestamp": "2026-03-26T00:00:00+00:00", "stage": "prepare", "status": "completed"}),
                json.dumps({"timestamp": "2026-03-26T00:01:00+00:00", "stage": "plan", "status": "completed"}),
            ]
        ),
        encoding="utf-8",
    )

    events = load_stage_events(str(tmp_path))

    assert len(events) == 2
    assert events[0]["stage"] == "prepare"


def test_summarize_stage_events_counts_latest_status():
    summary = summarize_stage_events(
        [
            {"timestamp": "2026-03-26T00:00:00+00:00", "stage": "prepare", "status": "running"},
            {"timestamp": "2026-03-26T00:01:00+00:00", "stage": "prepare", "status": "completed"},
            {"timestamp": "2026-03-26T00:02:00+00:00", "stage": "plan", "status": "failed"},
        ]
    )

    assert summary["event_count"] == 3
    assert summary["stages"]["prepare"]["events"] == 2
    assert summary["stages"]["prepare"]["latest_status"] == "completed"
    assert summary["stages"]["plan"]["latest_status"] == "failed"
