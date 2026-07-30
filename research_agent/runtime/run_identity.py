from __future__ import annotations

import hashlib
from pathlib import Path
import re


def _safe_component(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-.")
    return normalized or "run"


def _cache_identity(cache_path: str | Path) -> str:
    resolved = str(Path(cache_path).resolve())
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:12]


def isolated_workspace_root(
    base_dir: str | Path,
    *,
    instance_id: str,
    model: str,
    cache_path: str | Path,
) -> Path:
    """Return a workspace unique to one top-level cache identity."""

    label = (
        f"task_{_safe_component(instance_id)}_"
        f"{_safe_component(model)}_{_cache_identity(cache_path)}"
    )
    return Path(base_dir) / "workplace_paper" / label


def isolated_container_name(
    base_name: str,
    instance_id: str,
    cache_path: str | Path,
) -> str:
    """Return a Docker-safe container name unique to one top-level run."""

    prefix = (
        f"{_safe_component(base_name)[:28]}-"
        f"{_safe_component(instance_id)[:16]}-"
    )
    return f"{prefix}{_cache_identity(cache_path)}"[:63]
