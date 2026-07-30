from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = REPO_ROOT / "research_agent"
INSTANCE_PATH = REPO_ROOT / "benchmark/final/vq/one_layer_vq.json"
CONTRACT_PATH = (
    REPO_ROOT
    / "benchmark/evaluators/one_layer_vq_smoke/contract.closed_loop_v2.yaml"
)
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT / "benchmark/runs/one_layer_vq_closed_loop_v2"
)
DEFAULT_SEEDS = (401, 502, 603, 704, 805)
PRIMARY_METRIC = "codebook_utilization"
RUNTIME_ARTIFACT_DIRS = {
    "logs",
    "paper_db",
    "terminal_tmp",
    "workplace_paper",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def arm_order(seed_index: int) -> tuple[str, str]:
    return ("control", "treatment") if seed_index % 2 == 0 else (
        "treatment",
        "control",
    )


def resolved_cache_path(cache_base: Path, model: str) -> Path:
    return Path(f"{cache_base}_one_layer_vq_{model.replace('/', '__')}")


def _is_revision_source(path: Path) -> bool:
    if "__pycache__" in path.parts:
        return False
    if path.suffix not in {".py", ".json", ".yaml", ".yml", ".md", ".toml"}:
        return False
    try:
        relative = path.relative_to(AGENT_ROOT)
    except ValueError:
        return True
    if not relative.parts:
        return True
    top_level = relative.parts[0]
    return (
        top_level not in RUNTIME_ARTIFACT_DIRS
        and not top_level.startswith("cache")
    )


def source_revision() -> str:
    digest = hashlib.sha256()
    roots = (
        REPO_ROOT / "research_agent",
        REPO_ROOT / "benchmark/evaluators/one_layer_vq_smoke",
        REPO_ROOT / "benchmark/run_one_layer_vq_closed_loop_v2.py",
        REPO_ROOT / "benchmark/real_smoke/one_layer_vq/train.py",
        (
            REPO_ROOT
            / "benchmark/process/dataset_candidate/vq/run_training_testing.py"
        ),
        INSTANCE_PATH,
    )
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        else:
            files.extend(
                path
                for path in root.rglob("*")
                if path.is_file()
                and _is_revision_source(path)
            )
    for path in sorted(set(files)):
        digest.update(str(path.relative_to(REPO_ROOT)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_trial_command(
    *,
    python: Path,
    model: str,
    output_root: Path,
    seed: int,
    arm: str,
    port: int,
) -> tuple[list[str], Path, Path]:
    if arm not in {"control", "treatment"}:
        raise ValueError(f"unknown arm: {arm}")
    trial_root = output_root / f"seed-{seed}" / arm
    cache_base = trial_root / "cache"
    store = trial_root / "experience.sqlite3"
    item_budget, token_budget = (
        (0, 0) if arm == "control" else (8, 3000)
    )
    command = [
        str(python),
        "run_infer_plan.py",
        "--instance_path",
        str(INSTANCE_PATH),
        "--container_name",
        f"vq-v2-{seed}-{arm}",
        "--task_level",
        "task1",
        "--model",
        model,
        "--workplace_name",
        "workplace",
        "--cache_path",
        str(cache_base),
        "--port",
        str(port),
        "--max_iter_times",
        "0",
        "--seed",
        str(seed),
        "--category",
        "vq",
        "--experience-mode",
        "closed-loop",
        "--experience-store",
        str(store),
        "--evaluation-contract",
        str(CONTRACT_PATH),
        "--max-loop-iterations",
        "3",
        "--recall-item-budget",
        str(item_budget),
        "--recall-token-budget",
        str(token_budget),
        "--cache-policy",
        "disabled",
    ]
    return command, resolved_cache_path(cache_base, model), store


def _load_environment() -> None:
    from dotenv import load_dotenv

    load_dotenv(AGENT_ROOT / ".env", override=False)


def _redacted_error(error: Exception) -> str:
    message = str(error)
    for name, value in os.environ.items():
        if ("KEY" in name or "TOKEN" in name or "SECRET" in name) and len(value) >= 8:
            message = message.replace(value, "[REDACTED]")
    return message


def trial_environment() -> dict[str, str]:
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        [
            str(REPO_ROOT),
            *([existing_pythonpath] if existing_pythonpath else []),
        ]
    )
    if sys.platform == "darwin":
        environment.setdefault("PLAYWRIGHT_BROWSER_CHANNEL", "chrome")
    # The retrieval model is bundled in the local Hugging Face cache.  Force
    # offline resolution so every arm starts deterministically instead of
    # waiting on Hub metadata requests that are unrelated to the experiment.
    environment.setdefault("HF_HUB_OFFLINE", "1")
    environment.setdefault("TRANSFORMERS_OFFLINE", "1")
    return environment


def credential_probe(model: str) -> None:
    from litellm import completion

    completion(
        model=model,
        messages=[{"role": "user", "content": "Reply with OK."}],
        max_tokens=1,
        base_url=os.getenv("API_BASE_URL") or None,
        timeout=30,
    )


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def collect_trial(
    *,
    seed: int,
    arm: str,
    cache_path: Path,
    store_path: Path,
    wall_seconds: float,
    return_code: int,
) -> dict[str, Any]:
    from research_agent.inno.experience import ExperienceQuery
    from research_agent.inno.experience.ledger import SQLiteExperimentLedger

    trace_path = cache_path / "evals/trace.json"
    usage: dict[str, Any] = {}
    if trace_path.is_file():
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        usage = (trace.get("metadata") or {}).get("llm_usage") or {}

    experiences = []
    if store_path.is_file():
        experiences = SQLiteExperimentLedger(store_path).query(
            ExperienceQuery(task_id="one_layer_vq", limit=1000)
        )
        experiences.sort(key=lambda item: (item.created_at, item.experience_id))

    final = experiences[-1] if experiences else None
    verification = final.verification if final is not None else None
    metrics = verification.verified_metrics if verification is not None else {}
    score = metrics.get(PRIMARY_METRIC)
    valid = bool(
        return_code == 0
        and verification is not None
        and verification.valid
        and score is not None
    )
    artifacts = (
        [ref.path for ref in verification.evidence_refs]
        if verification is not None
        else []
    )
    failure_signature = None
    if not valid:
        if verification is not None and verification.violations:
            failure_signature = "|".join(sorted(verification.violations))
        elif return_code != 0:
            failure_signature = f"process_exit_{return_code}"
        else:
            failure_signature = "missing_valid_verification"
    return {
        "seed": seed,
        "arm": arm,
        "score": score,
        "valid": valid,
        "attempts_used": len(experiences),
        "tokens": int(usage.get("total_tokens", 0) or 0),
        "llm_usage": usage,
        "wall_seconds": round(wall_seconds, 6),
        "gpu_hours": 0.0,
        "failure_signature": failure_signature,
        "artifact_refs": artifacts,
        "cache_path": str(cache_path),
        "experience_store": str(store_path),
        "return_code": return_code,
    }


def summarize_trials(
    trials: list[dict[str, Any]],
    *,
    seeds: list[int],
    model: str,
    revision: str,
) -> dict[str, Any]:
    indexed = {(item["seed"], item["arm"]): item for item in trials}

    def arm_summary(arm: str) -> dict[str, Any]:
        selected = [indexed[(seed, arm)] for seed in seeds]
        scores = [
            float(item["score"])
            for item in selected
            if item["valid"] and item["score"] is not None
        ]
        failures = [
            item["failure_signature"]
            for item in selected
            if item["failure_signature"] is not None
        ]
        return {
            "arm": arm,
            "scores": [item["score"] for item in selected],
            "mean_valid_score": (
                round(sum(scores) / len(scores), 12) if scores else None
            ),
            "valid_rate": round(
                sum(bool(item["valid"]) for item in selected) / len(selected),
                12,
            ),
            "repeated_failure_rate": round(
                (len(failures) - len(set(failures))) / len(selected),
                12,
            ),
            "total_attempts": sum(item["attempts_used"] for item in selected),
            "total_tokens": sum(item["tokens"] for item in selected),
            "total_wall_seconds": round(
                sum(item["wall_seconds"] for item in selected),
                6,
            ),
            "total_gpu_hours": round(
                sum(item["gpu_hours"] for item in selected),
                6,
            ),
        }

    paired_deltas: list[float | None] = []
    for seed in seeds:
        control = indexed[(seed, "control")]
        treatment = indexed[(seed, "treatment")]
        if (
            control["valid"]
            and treatment["valid"]
            and control["score"] is not None
            and treatment["score"] is not None
        ):
            paired_deltas.append(
                round(float(treatment["score"]) - float(control["score"]), 12)
            )
        else:
            paired_deltas.append(None)
    complete = len(trials) == len(seeds) * 2
    all_valid = complete and all(item["valid"] for item in trials)
    numeric_deltas = [item for item in paired_deltas if item is not None]
    return {
        "schema_version": "1",
        "task_id": "one_layer_vq:task1",
        "contract": "one-layer-vq-cifar10-closed-loop@2",
        "primary_metric": PRIMARY_METRIC,
        "direction": "maximize",
        "seeds": seeds,
        "model": model,
        "code_revision": revision,
        "budget": {
            "max_loop_iterations": 3,
            "train_samples_per_attempt": 8192,
            "epochs_per_attempt": 2,
            "test_samples_per_attempt": 1024,
            "codebook_size": 128,
            "latent_dim": 16,
        },
        "control": arm_summary("control"),
        "treatment": arm_summary("treatment"),
        "paired_deltas": paired_deltas,
        "experience_gain": (
            round(sum(numeric_deltas) / len(numeric_deltas), 12)
            if all_valid
            else None
        ),
        "claim_valid": all_valid,
        "claim_boundary": (
            "Experience Gain is reported only when all five paired trials have "
            "valid raw-evidence verification."
        ),
        "trials": trials,
        "generated_at": utc_now(),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--model")
    parser.add_argument("--skip-credential-probe", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if len(args.seeds) != len(set(args.seeds)) or not args.seeds:
        raise SystemExit("seeds must be non-empty and unique")
    _load_environment()
    model = args.model or os.getenv("COMPLETION_MODEL")
    if not model:
        raise SystemExit("COMPLETION_MODEL is not configured")

    output_root = args.output_root.resolve()
    state_path = output_root / "run_manifest.json"
    if output_root.exists() and any(output_root.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty output root: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    revision = source_revision()
    manifest: dict[str, Any] = {
        "schema_version": "1",
        "status": "preflight",
        "started_at": utc_now(),
        "seeds": args.seeds,
        "arm_order": {
            str(seed): list(arm_order(index))
            for index, seed in enumerate(args.seeds)
        },
        "model": model,
        "contract_path": str(CONTRACT_PATH),
        "contract_sha256": hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
        "code_revision": revision,
        "trials": [],
    }
    _atomic_json(state_path, manifest)

    if not args.skip_credential_probe:
        try:
            credential_probe(model)
        except Exception as exc:
            manifest["status"] = "credential_probe_failed"
            manifest["error"] = _redacted_error(exc)
            manifest["completed_at"] = utc_now()
            _atomic_json(state_path, manifest)
            print(f"Credential probe failed: {manifest['error']}", file=sys.stderr)
            return 2

    # Keep the virtualenv entrypoint intact. Resolving the symlink can select the
    # base interpreter and silently drop the environment's installed packages.
    python = Path(sys.executable)
    environment = trial_environment()
    manifest["status"] = "running"
    _atomic_json(state_path, manifest)
    for seed_index, seed in enumerate(args.seeds):
        for arm_index, arm in enumerate(arm_order(seed_index)):
            port = 13000 + seed_index * 2 + arm_index
            command, cache_path, store_path = build_trial_command(
                python=python,
                model=model,
                output_root=output_root,
                seed=seed,
                arm=arm,
                port=port,
            )
            trial_root = output_root / f"seed-{seed}" / arm
            trial_root.mkdir(parents=True, exist_ok=True)
            log_path = trial_root / "runner.log"
            started = time.perf_counter()
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.run(
                    command,
                    cwd=AGENT_ROOT,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            wall_seconds = time.perf_counter() - started
            trial = collect_trial(
                seed=seed,
                arm=arm,
                cache_path=cache_path,
                store_path=store_path,
                wall_seconds=wall_seconds,
                return_code=process.returncode,
            )
            trial["runner_log"] = str(log_path)
            manifest["trials"].append(trial)
            _atomic_json(state_path, manifest)
            if process.returncode != 0:
                manifest["status"] = "trial_failed"
                manifest["completed_at"] = utc_now()
                _atomic_json(state_path, manifest)
                return process.returncode or 1

    report = summarize_trials(
        manifest["trials"],
        seeds=args.seeds,
        model=model,
        revision=revision,
    )
    report_path = output_root / "paired_report.json"
    _atomic_json(report_path, report)
    manifest["status"] = "completed"
    manifest["completed_at"] = utc_now()
    manifest["paired_report"] = str(report_path)
    _atomic_json(state_path, manifest)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
