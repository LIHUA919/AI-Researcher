from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any


LEDGER_TABLES = (
    "verification_records",
    "knowledge_records",
    "recall_contexts",
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rewrite_paths(value: Any, *, raw_root: Path, published_root: Path) -> Any:
    if isinstance(value, dict):
        return {
            key: _rewrite_paths(
                item,
                raw_root=raw_root,
                published_root=published_root,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _rewrite_paths(
                item,
                raw_root=raw_root,
                published_root=published_root,
            )
            for item in value
        ]
    if isinstance(value, str):
        candidate = Path(value)
        if candidate.is_absolute():
            try:
                relative = candidate.relative_to(raw_root)
            except ValueError:
                try:
                    return candidate.relative_to(REPOSITORY_ROOT).as_posix()
                except ValueError:
                    return value
            return (published_root / "evidence" / relative).as_posix()
    return value


def _export_ledger(
    ledger_path: Path,
    destination: Path,
    *,
    raw_root: Path,
    published_root: Path,
) -> None:
    payload: dict[str, list[dict[str, Any]]] = {}
    with sqlite3.connect(ledger_path) as connection:
        for table in LEDGER_TABLES:
            rows = connection.execute(
                f"SELECT payload_json FROM {table} ORDER BY record_id"  # noqa: S608
            )
            payload[table] = [
                _rewrite_paths(
                    json.loads(row[0]),
                    raw_root=raw_root,
                    published_root=published_root,
                )
                for row in rows
            ]
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def export_run(raw_root: Path, published_root: Path) -> dict[str, Any]:
    raw_root = raw_root.resolve()
    reports = sorted(
        path
        for path in (raw_root / "reports").glob("*.json")
        if path.name != "run_summary.json"
    )
    if len(reports) != 1:
        raise ValueError(f"expected exactly one task report in {raw_root}")
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    task_slug = report["task"]["task_id"].replace(":", "_")
    task_root = published_root / task_slug
    evidence_root = task_root / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=False)

    artifact_index: list[dict[str, Any]] = []
    for attempt_file in sorted(raw_root.rglob("attempt-*/*")):
        if not attempt_file.is_file():
            continue
        relative = attempt_file.relative_to(raw_root)
        destination = evidence_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(attempt_file, destination)
        artifact_index.append(
            {
                "path": destination.relative_to(published_root).as_posix(),
                "sha256": _sha256(destination),
                "size_bytes": destination.stat().st_size,
            }
        )

    for ledger_path in sorted(raw_root.rglob("experience.sqlite3")):
        relative_parent = ledger_path.parent.relative_to(raw_root)
        destination = evidence_root / relative_parent / "ledger_evidence.json"
        _export_ledger(
            ledger_path,
            destination,
            raw_root=raw_root,
            published_root=task_root,
        )
        artifact_index.append(
            {
                "path": destination.relative_to(published_root).as_posix(),
                "sha256": _sha256(destination),
                "size_bytes": destination.stat().st_size,
            }
        )

    sanitized = _rewrite_paths(
        report,
        raw_root=raw_root,
        published_root=task_root,
    )
    report_path = task_root / "experience_gain.json"
    report_path.write_text(
        json.dumps(sanitized, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    index_path = task_root / "artifact_index.json"
    index_path.write_text(
        json.dumps(artifact_index, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    run_summary = json.loads(
        (raw_root / "reports" / "run_summary.json").read_text(encoding="utf-8")
    )
    return {
        "task_id": report["task"]["task_id"],
        "experience_gain": report["experience_gain"],
        "paired_deltas": report["paired_deltas"],
        "baseline": report["baseline"],
        "closed_loop": report["closed_loop"],
        "source_revision_digest": run_summary["source_revision_digest"],
        "generator_configuration_digest": run_summary[
            "generator_configuration_digest"
        ],
        "generator_cache_hits": run_summary["generator_cache_hits"],
        "generator_cache_misses": run_summary["generator_cache_misses"],
        "report": report_path.relative_to(published_root).as_posix(),
        "artifact_index": index_path.relative_to(published_root).as_posix(),
        "artifact_count": len(artifact_index),
        "claim_scope": report["metadata"]["claim_scope"],
        "source_url": report["metadata"]["source_url"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", action="append", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    output_root = Path(args.output_root)
    if output_root.exists():
        parser.error(f"refusing to overwrite existing output: {output_root}")
    output_root.mkdir(parents=True)
    tasks = [
        export_run(Path(raw_root), output_root)
        for raw_root in args.run_root
    ]
    revisions = {task["source_revision_digest"] for task in tasks}
    generator_digests = {
        task["generator_configuration_digest"] for task in tasks
    }
    if len(revisions) != 1 or len(generator_digests) != 1:
        raise ValueError("published runs do not share one frozen configuration")
    positive_tasks = [
        task["task_id"] for task in tasks if task["experience_gain"] > 0
    ]
    baseline_failure_rate = sum(
        task["baseline"]["repeated_failure_rate"] for task in tasks
    ) / len(tasks)
    closed_failure_rate = sum(
        task["closed_loop"]["repeated_failure_rate"] for task in tasks
    ) / len(tasks)
    summary = {
        "schema_version": "1",
        "benchmark": "Scientist-Bench task1 executable subset",
        "model": "Qwen3-Coder-30B-A3B-Instruct",
        "seeds": [101, 202, 303],
        "iterations_per_mode": 2,
        "source_revision_digest": next(iter(revisions)),
        "generator_configuration_digest": next(iter(generator_digests)),
        "positive_task_count": len(positive_tasks),
        "positive_tasks": positive_tasks,
        "mean_repeated_failure_rate": {
            "off": baseline_failure_rate,
            "closed_loop": closed_failure_rate,
        },
        "valid_rate_not_reduced": all(
            task["closed_loop"]["valid_rate"] >= task["baseline"]["valid_rate"]
            for task in tasks
        ),
        "phase_3_exit_criteria": {
            "positive_gain_on_multiple_tasks": len(positive_tasks) > 1,
            "repeated_failures_not_increased": (
                closed_failure_rate <= baseline_failure_rate
            ),
            "invalid_results_not_increased": all(
                task["closed_loop"]["valid_rate"]
                >= task["baseline"]["valid_rate"]
                for task in tasks
            ),
            "reproducible_trial_ids_and_digests": True,
        },
        "tasks": tasks,
        "claim_boundary": (
            "These results measure CPU functional implementation conformance "
            "on three Scientist-Bench task1 adapters. They do not establish "
            "paper-level training speed, FID, model quality, accuracy, or "
            "scientific state of the art."
        ),
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(output_root / "summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
