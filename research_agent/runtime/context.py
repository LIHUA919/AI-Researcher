from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RunContext:
    run_id: str
    cache_path: str
    entrypoint: str
    task_level: str
    model: str
    workplace_name: str
    instance_path: str | None = None
    stage_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def refresh_stage_state(self, stage_state: dict[str, Any]) -> dict[str, Any]:
        self.stage_state = dict(stage_state)
        return self.stage_state

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    def to_context_variables(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "working_dir": self.workplace_name,
            "stage_state": self.stage_state,
            "runtime_context": self.to_payload(),
        }
        if extra:
            payload.update(extra)
        return payload


def refresh_runtime_context_variables(
    context_variables: dict[str, Any],
    run_context: RunContext,
    stage_state: dict[str, Any],
) -> dict[str, Any]:
    context_variables["stage_state"] = run_context.refresh_stage_state(stage_state)
    context_variables["runtime_context"] = run_context.to_payload()
    return context_variables
