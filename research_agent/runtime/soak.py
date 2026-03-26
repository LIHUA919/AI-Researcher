from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_agent.runtime import GoalDrivenSupervisor, MasterRuntime


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_cache_path(cache_prefix: str, instance_id: str, model: str) -> str:
    return f"{cache_prefix}_{instance_id}_{model.replace('/', '__')}"


def build_run_command(args: argparse.Namespace) -> list[str]:
    return [
        args.python_bin,
        args.entry_script,
        "--instance_path",
        args.instance_path,
        "--task_level",
        args.task_level,
        "--model",
        args.model,
        "--workplace_name",
        args.workplace_name,
        "--cache_path",
        args.cache_prefix,
        "--port",
        str(args.port),
        "--max_iter_times",
        str(args.max_iter_times),
        "--category",
        args.category,
        "--container_name",
        args.container_name,
    ]


def build_soak_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("AUTO_SELECT_FIRST_OPTION", "1")
    env.setdefault("LLM_REQUEST_TIMEOUT", str(args.llm_timeout))
    env.setdefault("LLM_RETRY_ATTEMPTS", str(args.llm_retry_attempts))
    env.setdefault("LLM_RETRY_BACKOFF_SECONDS", str(args.llm_retry_backoff_seconds))
    env.setdefault("MODEL_FALLBACKS", args.model_fallbacks or args.model)
    return env


def write_long_run_report(cache_path: str, payload: dict[str, Any]) -> str:
    os.makedirs(cache_path, exist_ok=True)
    output_path = os.path.join(cache_path, "long_run_report.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)
    return output_path


def load_stage_events(cache_path: str) -> list[dict[str, Any]]:
    events_path = Path(cache_path) / "stage_events.jsonl"
    if not events_path.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))
    return events


def summarize_stage_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "event_count": len(events),
        "stages": {},
    }
    for event in events:
        stage = event.get("stage")
        if not stage:
            continue
        stage_summary = summary["stages"].setdefault(
            stage,
            {
                "events": 0,
                "latest_status": None,
                "latest_timestamp": None,
            },
        )
        stage_summary["events"] += 1
        stage_summary["latest_status"] = event.get("status")
        stage_summary["latest_timestamp"] = event.get("timestamp")
    return summary


def run_soak_test(args: argparse.Namespace) -> str:
    with open(args.instance_path, "r", encoding="utf-8") as f:
        instance = json.load(f)
    instance_id = instance["instance_id"]
    cache_path = compute_cache_path(args.cache_prefix, instance_id, args.model)
    runtime = MasterRuntime(cache_path)
    command = build_run_command(args)

    env = build_soak_env(args)

    started_at = utc_now_iso()
    supervisor = GoalDrivenSupervisor(
        runtime=runtime,
        run_id=instance_id,
        command=command,
        cwd=args.cwd,
        env=env,
        max_restarts=args.max_restarts,
        poll_interval_seconds=args.poll_interval_seconds,
        stale_timeout_seconds=args.stale_timeout_seconds,
    )
    result = supervisor.run()
    ended_at = utc_now_iso()
    goal = runtime.evaluate_goal()
    stage_events = load_stage_events(cache_path)
    report_path = write_long_run_report(
        cache_path,
        {
            "run_id": instance_id,
            "instance_path": args.instance_path,
            "started_at": started_at,
            "ended_at": ended_at,
            "status": result.status,
            "restart_count": result.restart_count,
            "returncode": result.returncode,
            "last_error": result.last_error,
            "completed_stages": goal.completed_stages,
            "incomplete_stages": goal.incomplete_stages,
            "latest_artifact": runtime.latest_artifact(),
            "cache_path": cache_path,
            "command": command,
            "restart_history": [
                {
                    "timestamp": event.timestamp,
                    "event": event.event,
                    "restart_count": event.restart_count,
                    "stage_name": event.stage_name,
                    "reason": event.reason,
                    "returncode": event.returncode,
                }
                for event in result.events
            ],
            "stage_event_summary": summarize_stage_events(stage_events),
        },
    )
    return report_path


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance_path", type=str, required=True)
    parser.add_argument("--task_level", type=str, default="task1")
    parser.add_argument("--category", type=str, default="vq")
    parser.add_argument("--entry_script", type=str, default="research_agent/run_infer_plan.py")
    parser.add_argument("--python_bin", type=str, default=sys.executable)
    parser.add_argument("--cwd", type=str, default=os.getcwd())
    parser.add_argument("--model", type=str, default="gpt-4o-2024-08-06")
    parser.add_argument("--workplace_name", type=str, default="workplace")
    parser.add_argument("--cache_prefix", type=str, default="cache_soak")
    parser.add_argument("--container_name", type=str, default="paper_eval")
    parser.add_argument("--port", type=int, default=12345)
    parser.add_argument("--max_iter_times", type=int, default=0)
    parser.add_argument("--max_restarts", type=int, default=2)
    parser.add_argument("--poll_interval_seconds", type=float, default=60.0)
    parser.add_argument("--stale_timeout_seconds", type=int, default=1800)
    parser.add_argument("--llm_timeout", type=int, default=180)
    parser.add_argument("--llm_retry_attempts", type=int, default=3)
    parser.add_argument("--llm_retry_backoff_seconds", type=int, default=5)
    parser.add_argument("--model_fallbacks", type=str, default="")
    return parser.parse_args()


if __name__ == "__main__":
    report = run_soak_test(get_args())
    print(report)
