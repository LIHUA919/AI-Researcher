from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from datetime import datetime
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping, Protocol

import numpy as np

from research_agent.inno.experience.intervention import (
    InterventionRecord,
    TrialProvenanceRecord,
    semantic_digest,
)
from research_agent.inno.experience.models import ArtifactRef


class ImmutableEnvelopeConflict(FileExistsError):
    """Raised when an immutable envelope path has different bytes."""


def canonical_json_bytes(value: Any) -> bytes:
    """Encode semantic JSON without lossy fallback conversions."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def raw_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def content_digest(domain: str, content: bytes) -> str:
    """Hash byte-exact content without introducing a path identity."""

    return hashlib.sha256(domain.encode("ascii") + b"\0" + content).hexdigest()


def artifact_ref(path: str | Path) -> ArtifactRef:
    artifact_path = Path(path).resolve()
    content = artifact_path.read_bytes()
    media_type = (
        mimetypes.guess_type(artifact_path.name)[0] or "application/octet-stream"
    )
    return ArtifactRef(
        path=str(artifact_path),
        sha256=raw_sha256(content),
        media_type=media_type,
        size_bytes=len(content),
    )


def _read_descriptor_bytes(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while chunk := os.read(descriptor, 1024 * 1024):
        chunks.append(chunk)
    return b"".join(chunks)


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _open_directory_chain(
    parent: Path,
    *,
    create: bool,
) -> tuple[int, os.stat_result]:
    absolute_parent = Path(os.path.abspath(parent))
    descriptor = os.open(absolute_parent.anchor, _directory_open_flags())
    try:
        for component in absolute_parent.parts[1:]:
            try:
                next_descriptor = os.open(
                    component,
                    _directory_open_flags(),
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                if not create:
                    raise ImmutableEnvelopeConflict(
                        "immutable JSON parent directory changed or disappeared: "
                        f"{absolute_parent}"
                    ) from None
                try:
                    os.mkdir(component, mode=0o755, dir_fd=descriptor)
                except FileExistsError:
                    pass
                try:
                    next_descriptor = os.open(
                        component,
                        _directory_open_flags(),
                        dir_fd=descriptor,
                    )
                except OSError as exc:
                    raise ImmutableEnvelopeConflict(
                        "immutable JSON parent directory must not contain a symlink "
                        f"or non-directory entry: {absolute_parent}"
                    ) from exc
            except OSError as exc:
                raise ImmutableEnvelopeConflict(
                    "immutable JSON parent directory must not contain a symlink "
                    f"or non-directory entry: {absolute_parent}"
                ) from exc

            opened_stat = os.fstat(next_descriptor)
            path_stat = os.stat(
                component,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
            if (
                stat.S_ISLNK(path_stat.st_mode)
                or not stat.S_ISDIR(path_stat.st_mode)
                or not stat.S_ISDIR(opened_stat.st_mode)
                or (path_stat.st_dev, path_stat.st_ino)
                != (opened_stat.st_dev, opened_stat.st_ino)
            ):
                os.close(next_descriptor)
                raise ImmutableEnvelopeConflict(
                    "immutable JSON parent directory must not contain a symlink "
                    f"or changed entry: {absolute_parent}"
                )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, os.fstat(descriptor)
    except BaseException:
        os.close(descriptor)
        raise


def _verify_parent_directory_identity(
    parent: Path,
    expected_stat: os.stat_result,
) -> None:
    descriptor, current_stat = _open_directory_chain(parent, create=False)
    try:
        if (current_stat.st_dev, current_stat.st_ino) != (
            expected_stat.st_dev,
            expected_stat.st_ino,
        ):
            raise ImmutableEnvelopeConflict(
                "immutable JSON parent directory changed while writing: "
                f"{parent}"
            )
    finally:
        os.close(descriptor)


def _target_entry_exists(
    parent_descriptor: int,
    target_name: str,
    target: Path,
) -> bool:
    try:
        target_stat = os.stat(
            target_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(target_stat.st_mode):
        raise ImmutableEnvelopeConflict(
            f"immutable JSON path must not be a symlink: {target}"
        )
    if not stat.S_ISREG(target_stat.st_mode):
        raise ImmutableEnvelopeConflict(
            f"immutable JSON path must be a regular file: {target}"
        )
    return True


def _verify_and_seal_immutable_json(
    parent_descriptor: int,
    target_name: str,
    target: Path,
    expected_content: bytes,
    *,
    conflict_context: str,
) -> ArtifactRef:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(
            target_name,
            flags,
            dir_fd=parent_descriptor,
        )
    except OSError as exc:
        raise ImmutableEnvelopeConflict(
            f"immutable JSON {conflict_context}; path could not be opened as a "
            f"regular non-symlink file: {target}"
        ) from exc

    try:
        expected_sha256 = raw_sha256(expected_content)
        opened_stat = os.fstat(descriptor)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise ImmutableEnvelopeConflict(
                f"immutable JSON {conflict_context}; target is not a regular file: "
                f"{target}"
            )
        opened_content = _read_descriptor_bytes(descriptor)
        if (
            opened_content != expected_content
            or raw_sha256(opened_content) != expected_sha256
        ):
            raise ImmutableEnvelopeConflict(
                f"immutable JSON {conflict_context} with other bytes: {target}"
            )

        os.fchmod(descriptor, 0o444)
        sealed_content = _read_descriptor_bytes(descriptor)
        sealed_stat = os.fstat(descriptor)
        try:
            path_stat = os.stat(
                target_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ImmutableEnvelopeConflict(
                f"immutable JSON {conflict_context}; path disappeared while sealing: "
                f"{target}"
            ) from exc
        if stat.S_ISLNK(path_stat.st_mode):
            raise ImmutableEnvelopeConflict(
                f"immutable JSON {conflict_context}; path must not be a symlink: "
                f"{target}"
            )
        if (
            not stat.S_ISREG(path_stat.st_mode)
            or (path_stat.st_dev, path_stat.st_ino)
            != (sealed_stat.st_dev, sealed_stat.st_ino)
            or sealed_content != expected_content
            or raw_sha256(sealed_content) != expected_sha256
            or stat.S_IMODE(sealed_stat.st_mode) != 0o444
        ):
            raise ImmutableEnvelopeConflict(
                f"immutable JSON {conflict_context}; identity changed while sealing: "
                f"{target}"
            )
        media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return ArtifactRef(
            path=str(target),
            sha256=expected_sha256,
            media_type=media_type,
            size_bytes=len(sealed_content),
        )
    finally:
        os.close(descriptor)


def atomic_write_canonical_json(path: str | Path, value: Any) -> ArtifactRef:
    """Atomically create an immutable canonical-JSON execution envelope."""

    target = Path(os.path.abspath(Path(path)))
    if not target.name:
        raise ImmutableEnvelopeConflict("immutable JSON path must name a file")
    content = canonical_json_bytes(value)
    parent_descriptor, parent_stat = _open_directory_chain(
        target.parent,
        create=True,
    )
    temporary_name: str | None = None
    try:
        if _target_entry_exists(parent_descriptor, target.name, target):
            ref = _verify_and_seal_immutable_json(
                parent_descriptor,
                target.name,
                target,
                content,
                conflict_context="already exists",
            )
        else:
            for _ in range(128):
                candidate = f".{target.name}.{secrets.token_hex(8)}.tmp"
                try:
                    descriptor = os.open(
                        candidate,
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                        dir_fd=parent_descriptor,
                    )
                except FileExistsError:
                    continue
                temporary_name = candidate
                break
            else:
                raise ImmutableEnvelopeConflict(
                    f"could not reserve immutable JSON temporary file: {target}"
                )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(
                    temporary_name,
                    target.name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError:
                conflict_context = "was concurrently created"
            else:
                conflict_context = "was created"
            ref = _verify_and_seal_immutable_json(
                parent_descriptor,
                target.name,
                target,
                content,
                conflict_context=conflict_context,
            )
        _verify_parent_directory_identity(target.parent, parent_stat)
        return ref
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def file_set_digest(
    domain: str,
    files: Mapping[str, str | Path],
) -> str:
    entries = []
    for logical_name, raw_path in sorted(files.items()):
        if Path(logical_name).is_absolute() or ".." in Path(logical_name).parts:
            raise ValueError(f"file-set name must be a logical path: {logical_name!r}")
        path = Path(raw_path)
        content = path.read_bytes()
        entries.append(
            {
                "path": Path(logical_name).as_posix(),
                "sha256": raw_sha256(content),
                "size_bytes": len(content),
            }
        )
    return semantic_digest(domain, entries)


def evidence_bundle_digest(refs: list[ArtifactRef]) -> str:
    logical_names = [Path(ref.path).name for ref in refs]
    if len(logical_names) != len(set(logical_names)):
        raise ValueError("evidence artifacts must have unique logical names")
    entries = [
        {
            "path": Path(ref.path).name,
            "sha256": ref.sha256,
            "size_bytes": ref.size_bytes,
        }
        for ref in sorted(refs, key=lambda item: Path(item.path).name)
    ]
    return semantic_digest("ai-researcher/evidence-bundle/v1", entries)


def evidence_payload_digest(arrays: Mapping[str, np.ndarray]) -> str:
    """Hash named arrays with explicit dtype, shape, and byte framing."""

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


def build_v3_attempt_id(
    *,
    run_id: str,
    iteration_id: str,
    task_id: str,
    hypothesis_id: str,
    intervention_id: str,
    seed: int,
    recall_snapshot_id: str,
    intervention_digest: str,
    source_digest: str,
    config_digest: str,
    dataset_digest: str,
    environment_digest: str,
    contract_digest: str,
    evaluator_digest: str,
) -> str:
    return semantic_digest(
        "ai-researcher/attempt/v3",
        {
            "run_id": run_id,
            "iteration_id": iteration_id,
            "task_id": task_id,
            "hypothesis_id": hypothesis_id,
            "intervention_id": intervention_id,
            "seed": seed,
            "recall_snapshot_id": recall_snapshot_id,
            "intervention_digest": intervention_digest,
            "source_digest": source_digest,
            "config_digest": config_digest,
            "dataset_digest": dataset_digest,
            "environment_digest": environment_digest,
            "contract_digest": contract_digest,
            "evaluator_digest": evaluator_digest,
        },
    )


def build_v3_observation_id(
    *,
    attempt_id: str,
    artifact_refs: list[ArtifactRef],
    exit_code: int,
    error: Mapping[str, Any] | None,
) -> str:
    return semantic_digest(
        "ai-researcher/observation/v3",
        {
            "attempt_id": attempt_id,
            "artifacts": [
                {
                    "path": Path(ref.path).name,
                    "sha256": ref.sha256,
                    "size_bytes": ref.size_bytes,
                }
                for ref in sorted(
                    artifact_refs,
                    key=lambda item: Path(item.path).name,
                )
            ],
            "exit_code": exit_code,
            "error": error,
        },
    )


def build_trial_provenance_id(
    *,
    attempt_id: str,
    observation_id: str,
    intervention_id: str,
    proposal_digest: str,
    intervention_digest: str,
    source_digest: str,
    config_digest: str,
    environment_digest: str,
    dataset_digest: str,
    contract_digest: str,
    evaluator_digest: str,
    attempt_spec_digest: str,
    evidence_digest: str,
    execution_envelope_ref: ArtifactRef,
) -> str:
    return semantic_digest(
        "ai-researcher/trial-provenance-id/v1",
        {
            "attempt_id": attempt_id,
            "observation_id": observation_id,
            "intervention_id": intervention_id,
            "proposal_digest": proposal_digest,
            "intervention_digest": intervention_digest,
            "source_digest": source_digest,
            "config_digest": config_digest,
            "environment_digest": environment_digest,
            "dataset_digest": dataset_digest,
            "contract_digest": contract_digest,
            "evaluator_digest": evaluator_digest,
            "attempt_spec_digest": attempt_spec_digest,
            "evidence_digest": evidence_digest,
            "execution_envelope": {
                "sha256": execution_envelope_ref.sha256,
                "size_bytes": execution_envelope_ref.size_bytes,
            },
        },
    )


class _TrialPreflightLike(Protocol):
    proposal_digest: str
    intervention_digest: str
    config_digest: str
    source_digest: str
    dataset_digest: str
    environment_digest: str
    contract_digest: str
    evaluator_digest: str
    attempt_spec_digest: str


def bind_trial_provenance(
    *,
    attempt_id: str,
    observation_id: str,
    intervention: InterventionRecord,
    preflight: _TrialPreflightLike,
    evidence_digest: str,
    execution_envelope_ref: ArtifactRef,
    created_at: datetime,
) -> TrialProvenanceRecord:
    """Bind post-snapshot evidence to the exact pre-run Intervention."""

    if (
        intervention.proposal_digest != preflight.proposal_digest
        or intervention.intervention_digest != preflight.intervention_digest
        or intervention.config_digest != preflight.config_digest
    ):
        raise ValueError(
            "Trial Provenance preflight does not match the persisted Intervention"
        )
    return TrialProvenanceRecord(
        provenance_id=build_trial_provenance_id(
            attempt_id=attempt_id,
            observation_id=observation_id,
            intervention_id=intervention.intervention_id,
            proposal_digest=preflight.proposal_digest,
            intervention_digest=preflight.intervention_digest,
            source_digest=preflight.source_digest,
            config_digest=preflight.config_digest,
            environment_digest=preflight.environment_digest,
            dataset_digest=preflight.dataset_digest,
            contract_digest=preflight.contract_digest,
            evaluator_digest=preflight.evaluator_digest,
            attempt_spec_digest=preflight.attempt_spec_digest,
            evidence_digest=evidence_digest,
            execution_envelope_ref=execution_envelope_ref,
        ),
        attempt_id=attempt_id,
        observation_id=observation_id,
        intervention_id=intervention.intervention_id,
        proposal_digest=preflight.proposal_digest,
        intervention_digest=preflight.intervention_digest,
        source_digest=preflight.source_digest,
        config_digest=preflight.config_digest,
        environment_digest=preflight.environment_digest,
        dataset_digest=preflight.dataset_digest,
        contract_digest=preflight.contract_digest,
        evaluator_digest=preflight.evaluator_digest,
        attempt_spec_digest=preflight.attempt_spec_digest,
        evidence_digest=evidence_digest,
        execution_envelope_ref=execution_envelope_ref,
        created_at=created_at,
    )
