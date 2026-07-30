"""Independent digest primitives used by the V3 external evaluator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

import numpy as np


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def semantic_digest(domain: str, value: object) -> str:
    return hashlib.sha256(
        domain.encode("ascii") + b"\0" + canonical_json_bytes(value)
    ).hexdigest()


def content_digest(domain: str, content: bytes) -> str:
    """Hash raw content without making its filesystem path semantic."""

    return hashlib.sha256(domain.encode("ascii") + b"\0" + content).hexdigest()


def file_set_digest(
    domain: str,
    files: Mapping[str, str | Path],
) -> str:
    entries = []
    for logical_name, raw_path in sorted(files.items()):
        logical_path = Path(logical_name)
        if logical_path.is_absolute() or ".." in logical_path.parts:
            raise ValueError(f"invalid logical source path: {logical_name!r}")
        content = Path(raw_path).read_bytes()
        entries.append(
            {
                "path": logical_path.as_posix(),
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )
    return semantic_digest(domain, entries)


def evaluator_identity(contract: Mapping[str, object], contract_dir: Path) -> str:
    raw_files = contract.get("evaluator_files")
    if not isinstance(raw_files, list) or not all(
        isinstance(item, str) for item in raw_files
    ):
        raise ValueError("V3 contract evaluator_files must be a string list")
    files = []
    root = contract_dir.resolve()
    for logical_name in sorted(raw_files):
        logical_path = Path(logical_name)
        candidate = (root / logical_path).resolve()
        if (
            logical_path.is_absolute()
            or ".." in logical_path.parts
            or not candidate.is_file()
            or root not in candidate.parents
        ):
            raise ValueError(f"invalid evaluator file: {logical_name!r}")
        content = candidate.read_bytes()
        files.append(
            {
                "path": logical_path.as_posix(),
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )
    return semantic_digest(
        "ai-researcher/evaluator-set/v1",
        {
            "entrypoint": contract.get("entrypoint") or "",
            "files": files,
        },
    )


def evidence_payload_digest(arrays: Mapping[str, np.ndarray]) -> str:
    """Recompute the frozen protocol's framed raw-array evidence digest."""

    digest = hashlib.sha256()
    digest.update(b"ai-researcher/evidence-payload/v1\0")
    for name in sorted(arrays):
        array = np.ascontiguousarray(arrays[name])
        header = canonical_json_bytes(
            {
                "name": name,
                "dtype": array.dtype.str,
                "shape": list(array.shape),
            }
        )
        body = array.tobytes(order="C")
        for field in (header, body):
            digest.update(len(field).to_bytes(8, "big"))
            digest.update(field)
    return digest.hexdigest()
