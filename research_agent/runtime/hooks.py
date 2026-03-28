from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any


@dataclass(frozen=True)
class RuntimeHookEvent:
    timestamp: str
    event_type: str
    cache_path: str
    run_id: str | None = None
    stage_name: str | None = None
    status: str | None = None
    payload: dict[str, Any] | None = None


class RuntimeHooks:
    def emit(self, event: RuntimeHookEvent) -> None:  # pragma: no cover - default no-op
        return


class JsonlRuntimeHooks(RuntimeHooks):
    def __init__(self, cache_path: str, file_name: str = "runtime_events.jsonl"):
        self.cache_path = cache_path
        self.file_name = file_name

    def emit(self, event: RuntimeHookEvent) -> None:
        output_path = os.path.join(self.cache_path, self.file_name)
        os.makedirs(self.cache_path, exist_ok=True)
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")


def make_runtime_event(
    *,
    event_type: str,
    cache_path: str,
    run_id: str | None = None,
    stage_name: str | None = None,
    status: str | None = None,
    payload: dict[str, Any] | None = None,
) -> RuntimeHookEvent:
    return RuntimeHookEvent(
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type=event_type,
        cache_path=cache_path,
        run_id=run_id,
        stage_name=stage_name,
        status=status,
        payload=payload or {},
    )
