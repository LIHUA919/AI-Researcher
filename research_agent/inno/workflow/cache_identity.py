from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CachePolicy = Literal["reuse", "refresh", "disabled"]


class CacheIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    stage: str
    normalized_input: Any
    model_configuration: dict[str, Any] = Field(default_factory=dict)
    tool_configuration: dict[str, Any] = Field(default_factory=dict)
    recall_snapshot_id: str = "off"
    code_revision: str = ""
    dataset_digest: str = ""
    evaluation_contract_version: str = ""

    def digest(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def behavioral_cache_key(**values: Any) -> str:
    return CacheIdentity(**values).digest()
