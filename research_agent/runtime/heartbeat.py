from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_runtime_json(cache_path: str, file_name: str, payload: dict[str, Any]) -> str:
    os.makedirs(cache_path, exist_ok=True)
    output_path = os.path.join(cache_path, file_name)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)
    return output_path


def read_runtime_json(cache_path: str, file_name: str) -> dict[str, Any]:
    output_path = os.path.join(cache_path, file_name)
    if not os.path.exists(output_path):
        return {}
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def parse_runtime_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def write_heartbeat(
    cache_path: str,
    *,
    current_stage: str | None,
    status: str,
    last_error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    return write_runtime_json(
        cache_path,
        "heartbeat.json",
        {
            "current_stage": current_stage,
            "status": status,
            "last_error": last_error,
            "updated_at": utc_now_iso(),
            "metadata": metadata or {},
        },
    )


def write_run_status(
    cache_path: str,
    *,
    run_id: str,
    status: str,
    current_stage: str | None,
    completed_stages: list[str],
    incomplete_stages: list[str],
    latest_artifact: str | None = None,
    last_error: str | None = None,
) -> str:
    return write_runtime_json(
        cache_path,
        "run_status.json",
        {
            "run_id": run_id,
            "status": status,
            "current_stage": current_stage,
            "completed_stages": completed_stages,
            "incomplete_stages": incomplete_stages,
            "latest_artifact": latest_artifact,
            "last_error": last_error,
            "updated_at": utc_now_iso(),
        },
    )
