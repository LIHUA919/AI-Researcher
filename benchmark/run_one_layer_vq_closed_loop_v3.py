from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

from research_agent.security import redact_sensitive_environment_values


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = REPO_ROOT / "research_agent"
INSTANCE_PATH = REPO_ROOT / "benchmark/final/vq/one_layer_vq.json"
CONTRACT_PATH = (
    REPO_ROOT
    / "benchmark/evaluators/one_layer_vq_smoke/contract.closed_loop_v3.yaml"
)
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT / "benchmark/runs/one_layer_vq_closed_loop_v3"
)
DEFAULT_DRY_RUN_ROOT = (
    REPO_ROOT / "benchmark/runs/one_layer_vq_closed_loop_v3_dry_runs"
)
DEFAULT_SEEDS = (401, 502, 603, 704, 805)
DEFAULT_TRIAL_TIMEOUT_SECONDS = 3600.0
PRIMARY_METRIC = "codebook_utilization"
PAIR_PROVENANCE_FIELDS = (
    "source_digest",
    "dataset_digest",
    "environment_digest",
    "contract_digest",
    "evaluator_digest",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _raw_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _open_ledger(path: Path):
    from research_agent.inno.experience.ledger import (
        SQLiteExperimentLedger,
    )

    return SQLiteExperimentLedger(path)


def _load_environment() -> None:
    from dotenv import load_dotenv

    load_dotenv(AGENT_ROOT / ".env", override=False)


def _redacted_error(error: Exception) -> str:
    return _redacted_text(str(error))


def _redacted_text(message: str) -> str:
    return redact_sensitive_environment_values(
        message,
        os.environ,
        replacement_template="[REDACTED]",
    )


def _sanitize_log_file(path: Path) -> None:
    if not path.is_file():
        return
    content = path.read_text(encoding="utf-8", errors="replace")
    sanitized = _redacted_text(content)
    if sanitized == content:
        return
    temporary = path.with_suffix(path.suffix + ".redacted")
    temporary.write_text(sanitized, encoding="utf-8")
    temporary.replace(path)


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
    environment.setdefault("HF_HUB_OFFLINE", "1")
    environment.setdefault("TRANSFORMERS_OFFLINE", "1")
    return environment


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
    else:
        process.kill()
    process.wait(timeout=5)


def _run_trial_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    log,
    timeout_seconds: float,
) -> int:
    options: dict[str, Any] = {}
    if os.name == "posix":
        options["start_new_session"] = True
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
        **options,
    )
    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        raise


def _cleanup_trial_container(container_name: str) -> None:
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def credential_probe(model: str) -> None:
    from litellm import completion

    completion(
        model=model,
        messages=[{"role": "user", "content": "Reply with OK."}],
        max_tokens=1,
        base_url=os.getenv("API_BASE_URL") or None,
        timeout=30,
    )


def source_revision() -> str:
    """Digest the V3 orchestration and all externally attested source files."""

    roots = (
        REPO_ROOT / "research_agent/runtime",
        REPO_ROOT / "research_agent/inno/experience",
        REPO_ROOT / "research_agent/run_infer_plan.py",
        REPO_ROOT / "benchmark/evaluators/one_layer_vq_smoke",
        REPO_ROOT / "benchmark/real_smoke/one_layer_vq/train.py",
        (
            REPO_ROOT
            / "benchmark/process/dataset_candidate/vq/run_training_testing.py"
        ),
        REPO_ROOT / "benchmark/process/dataset_candidate/vq/attempt_spec.py",
        Path(__file__).resolve(),
        INSTANCE_PATH,
    )
    files: set[Path] = set()
    for root in roots:
        if root.is_file():
            files.add(root)
            continue
        files.update(
            path
            for path in root.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix in {".py", ".json", ".yaml", ".yml"}
        )
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(REPO_ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class _ExecutionMustNotRun:
    def execute(self, plan: Any) -> Any:
        raise AssertionError("dry-run must not start an Experiment Attempt")


def _validate_cifar_archive() -> dict[str, Any]:
    from research_agent.inno.environment.utils import (
        CIFAR10_ARCHIVE_MD5,
        CIFAR10_ARCHIVE_SHA256,
    )

    archive = (
        REPO_ROOT
        / "benchmark/process/dataset_candidate/vq/cifar-10-python.tar.gz"
    )
    if not archive.is_file():
        raise RuntimeError(f"missing official CIFAR-10 archive: {archive}")
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    actual_md5 = md5.hexdigest()
    actual_sha256 = sha256.hexdigest()
    if (
        actual_md5 != CIFAR10_ARCHIVE_MD5
        or actual_sha256 != CIFAR10_ARCHIVE_SHA256
    ):
        raise RuntimeError(
            "CIFAR-10 archive does not match its official MD5/SHA-256 identity"
        )
    return {
        "archive_path": str(archive),
        "archive_md5": actual_md5,
        "archive_sha256": actual_sha256,
        "archive_identity_valid": True,
    }


def _fixed_dry_run_proposal(policy: Any):
    from research_agent.inno.experience import InterventionProposal

    knob = sorted(policy.knobs)[0]
    default = float(policy.defaults[knob])
    candidates = [
        float(value)
        for value in policy.knobs[knob].allowed_values
        if float(value) != default
    ]
    target = candidates[0] if candidates else default
    return InterventionProposal(
        domain="vq",
        schema_id="vq.intervention/v1",
        decision_point=policy.decision_point,
        knob=knob,
        target=target,
        cited_knowledge_ids=[],
        expected_primary_metric_direction="unchanged",
        guardrail_risks=[],
        rationale="Deterministic dry-run planner proposal; baseline never invokes it.",
    )


def prepare_dry_run(
    *,
    output_root: Path,
    seeds: list[int],
) -> dict[str, Any]:
    """Prepare all baseline envelopes without LLM, training, or trial records."""

    from benchmark.process.dataset_candidate.vq.attempt_spec import (
        load_attempt_spec_from_environment,
    )
    from research_agent.inno.agents.inno_agent.intervention_agent import (
        FixedInterventionPlanner,
    )
    from research_agent.inno.experience import (
        ExperienceQuery,
        Hypothesis,
        SQLiteExperimentLedger,
        load_evaluation_contract,
        semantic_digest,
    )
    from research_agent.runtime import (
        AdaptiveExperimentBuildConfig,
        AdaptiveExperimentRequest,
        build_adaptive_experiment_runner,
    )

    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("seeds must be non-empty and unique")
    output_root = output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(
            f"refusing to overwrite non-empty output root: {output_root}"
        )
    output_root.mkdir(parents=True, exist_ok=True)

    contract = load_evaluation_contract(CONTRACT_PATH)
    if contract.schema_version != 2 or contract.adaptive_experiment is None:
        raise RuntimeError("V3 dry-run requires a schema-2 adaptive contract")
    policy = contract.adaptive_experiment
    dataset = _validate_cifar_archive()
    dry_trials: list[dict[str, Any]] = []
    order_by_seed = {
        str(seed): list(arm_order(index))
        for index, seed in enumerate(seeds)
    }
    for seed_index, seed in enumerate(seeds):
        for arm in arm_order(seed_index):
            trial_root = output_root / f"seed-{seed}" / arm
            project_dir = trial_root / "project"
            evidence_dir = (
                trial_root / "attempts/iteration-001/raw-evidence"
            )
            store_path = trial_root / "experience.sqlite3"
            ledger = SQLiteExperimentLedger(store_path)
            planner = FixedInterventionPlanner(
                _fixed_dry_run_proposal(policy)
            )
            runner = build_adaptive_experiment_runner(
                AdaptiveExperimentBuildConfig(
                    project_dir=project_dir,
                    contract_path=CONTRACT_PATH,
                    ledger=ledger,
                ),
                planner=planner,
                executor=_ExecutionMustNotRun(),
            )
            hypothesis_payload = {
                "task_id": contract.task_id,
                "statement": (
                    "Establish the frozen VQ catalog baseline before any "
                    "adaptive intervention."
                ),
                "mechanism": (
                    "The baseline binds source, dataset, environment, "
                    "contract, evaluator, and effective configuration."
                ),
                "expected_metric": contract.primary_metric.name,
                "metric_direction": contract.primary_metric.direction,
                "conditions": ["dry-run"],
            }
            hypothesis = Hypothesis(
                hypothesis_id=semantic_digest(
                    "ai-researcher/dry-run-hypothesis/v1",
                    {
                        "task_id": contract.task_id,
                        "statement": hypothesis_payload["statement"],
                    },
                ),
                **hypothesis_payload,
            )
            prepared = asyncio.run(
                runner.prepare_baseline(
                    AdaptiveExperimentRequest(
                        run_id="one_layer_vq",
                        iteration_number=1,
                        hypothesis=hypothesis,
                        seed=seed,
                        attempt_cache_path=evidence_dir.parent,
                        evidence_dir=evidence_dir,
                        recall_context=None,
                        previous=None,
                    )
                )
            )
            loaded = load_attempt_spec_from_environment(
                {
                    "AI_RESEARCHER_ATTEMPT_SPEC": str(
                        Path(prepared.attempt_spec_ref.path).resolve()
                    ),
                    "AI_RESEARCHER_ATTEMPT_SPEC_SHA256": (
                        prepared.attempt_spec_ref.sha256
                    ),
                }
            )
            if loaded.sha256 != prepared.attempt_spec_ref.sha256:
                raise RuntimeError("strict Attempt Spec loader digest mismatch")
            evidence_names = {
                path.name for path in evidence_dir.iterdir()
            }
            if evidence_names != {"attempt_spec.json"}:
                raise RuntimeError(
                    "dry-run created post-execution evidence unexpectedly"
                )
            if planner.invocation_count != 0:
                raise RuntimeError("baseline unexpectedly invoked the planner")
            if ledger.query(
                ExperienceQuery(task_id=contract.task_id, limit=1)
            ):
                raise RuntimeError("dry-run persisted a fake Experience")
            if ledger.list_promotion_decisions() or ledger.list_knowledge():
                raise RuntimeError(
                    "dry-run persisted fake verification-derived records"
                )
            persisted = ledger.list_interventions("one_layer_vq")
            if persisted != [prepared.intervention]:
                raise RuntimeError(
                    "dry-run baseline Intervention was not persisted exactly"
                )
            dry_trials.append(
                {
                    "seed": seed,
                    "arm": arm,
                    "planner": "FixedInterventionPlanner",
                    "planner_invocation_count": planner.invocation_count,
                    "execution_started": False,
                    "manipulation_status": (
                        prepared.preflight.manipulation_status
                    ),
                    "intervention": prepared.intervention.model_dump(
                        mode="json"
                    ),
                    "preflight": prepared.preflight.model_dump(mode="json"),
                    "attempt_spec_path": prepared.attempt_spec_ref.path,
                    "attempt_spec_sha256": (
                        prepared.attempt_spec_ref.sha256
                    ),
                    "experience_store": str(store_path),
                    "restored_sources": sorted(policy.source_files),
                }
            )

    report = {
        "schema_version": "1",
        "status": "dry_run_completed",
        "generated_at": utc_now(),
        "seeds": list(seeds),
        "arm_order": order_by_seed,
        "contract": {
            "path": str(CONTRACT_PATH),
            "schema_version": contract.schema_version,
            "id": contract.contract_id,
            "version": contract.version,
            "task_id": contract.task_id,
            "expected_source_digest": policy.expected_source_digest,
        },
        "dataset": dataset,
        "trials": dry_trials,
        "assurances": {
            "llm_called": False,
            "training_started": False,
            "gpu_work_started": False,
            "observation_written": False,
            "verification_written": False,
        },
    }
    _atomic_json(output_root / "dry_run_report.json", report)
    return report


def arm_order(seed_index: int) -> tuple[str, str]:
    """Counterbalance which arm pays first-position costs across seeds."""

    if seed_index < 0:
        raise ValueError("seed_index must be non-negative")
    return (
        ("control", "treatment")
        if seed_index % 2 == 0
        else ("treatment", "control")
    )


def _resolved_cache_path(cache_base: Path, model: str) -> Path:
    return Path(f"{cache_base}_one_layer_vq_{model.replace('/', '__')}")


def build_trial_command(
    *,
    python: Path,
    model: str,
    output_root: Path,
    seed: int,
    arm: str,
    port: int,
    trial_timeout_seconds: float = DEFAULT_TRIAL_TIMEOUT_SECONDS,
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
        f"vq-v3-{seed}-{arm}",
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
        "--adaptive-execution-timeout-seconds",
        str(trial_timeout_seconds),
    ]
    return command, _resolved_cache_path(cache_base, model), store


def _artifact_paths(observation: Any) -> dict[str, Path]:
    return {
        Path(ref.path).name: Path(ref.path)
        for ref in observation.artifact_refs
    }


def _manifest_matches(
    *,
    observation: Any,
    provenance: Any,
    intervention: Any,
) -> bool:
    """Cross-check the persisted sidecars against the immutable envelopes."""

    try:
        paths = _artifact_paths(observation)
        spec_path = paths["attempt_spec.json"]
        manifest_path = paths["evaluation_manifest.json"]
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("attempt_spec_sha256") != _raw_sha256(
            spec_path.read_bytes()
        ):
            return False

        expected = {
            field: getattr(provenance, field)
            for field in (
                "intervention_digest",
                "config_digest",
                *PAIR_PROVENANCE_FIELDS,
            )
        }
        spec_provenance = spec.get("provenance")
        manifest_provenance = manifest.get("provenance")
        if not isinstance(spec_provenance, dict) or not isinstance(
            manifest_provenance,
            dict,
        ):
            return False
        if any(
            spec_provenance.get(field) != value
            for field, value in expected.items()
            if field != "evaluator_digest"
            or "evaluator_digest" in spec_provenance
        ):
            return False
        manifest_expected = {
            **expected,
            "proposal_digest": provenance.proposal_digest,
            "manipulation_status": intervention.manipulation_status,
        }
        if any(
            manifest_provenance.get(field) != value
            for field, value in manifest_expected.items()
            if field != "contract_digest"
        ):
            return False
        if (
            (manifest.get("contract") or {}).get("digest")
            != provenance.contract_digest
        ):
            return False
        proposal = spec.get("proposal")
        if isinstance(proposal, dict) and (
            proposal.get("digest") != provenance.proposal_digest
        ):
            return False
        return True
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return False


def _provenance_payload(provenance: Any) -> dict[str, Any] | None:
    if provenance is None:
        return None
    return {
        "provenance_id": getattr(provenance, "provenance_id", None),
        "intervention_id": provenance.intervention_id,
        "proposal_digest": provenance.proposal_digest,
        "intervention_digest": provenance.intervention_digest,
        "config_digest": provenance.config_digest,
        "source_digest": provenance.source_digest,
        "dataset_digest": provenance.dataset_digest,
        "environment_digest": provenance.environment_digest,
        "contract_digest": provenance.contract_digest,
        "evaluator_digest": provenance.evaluator_digest,
        "attempt_spec_digest": getattr(
            provenance,
            "attempt_spec_digest",
            None,
        ),
        "evidence_digest": getattr(provenance, "evidence_digest", None),
    }


def collect_trial(
    *,
    seed: int,
    arm: str,
    cache_path: Path,
    store_path: Path,
    wall_seconds: float,
    return_code: int,
) -> dict[str, Any]:
    """Collect one arm exclusively from typed Ledger records and sidecars."""

    if arm not in {"control", "treatment"}:
        raise ValueError(f"unknown arm: {arm}")
    from research_agent.inno.experience import ExperienceQuery

    trace_path = cache_path / "evals/trace.json"
    usage: dict[str, Any] = {}
    if trace_path.is_file():
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        usage = (trace.get("metadata") or {}).get("llm_usage") or {}

    experiences: list[Any] = []
    interventions: list[Any] = []
    recall_contexts: list[Any] = []
    ledger = None
    if store_path.is_file():
        ledger = _open_ledger(store_path)
        experiences = ledger.query(
            ExperienceQuery(
                task_id="one_layer_vq:task1",
                limit=1000,
            )
        )
        experiences.sort(
            key=lambda item: item.attempt.iteration_id,
            reverse=True,
        )
        run_id = (
            experiences[0].attempt.run_id
            if experiences
            else "one_layer_vq"
        )
        interventions = sorted(
            ledger.list_interventions(run_id),
            key=lambda item: item.iteration_id,
        )
        recall_contexts = ledger.list_recall_contexts()

    intervention_by_id = {
        record.intervention_id: record for record in interventions
    }
    attempt_rows: list[dict[str, Any]] = []
    immediate_feedback: list[dict[str, Any]] = []
    for experience in reversed(experiences):
        verification = experience.verification
        provenance = (
            ledger.find_trial_provenance(
                experience.observation.observation_id
            )
            if ledger is not None
            else None
        )
        intervention = (
            intervention_by_id.get(provenance.intervention_id)
            if provenance is not None
            else None
        )
        manifest_match = bool(
            provenance is not None
            and intervention is not None
            and _manifest_matches(
                observation=experience.observation,
                provenance=provenance,
                intervention=intervention,
            )
        )
        attempt_rows.append(
            {
                "attempt_id": experience.attempt.attempt_id,
                "observation_id": experience.observation.observation_id,
                "verification_id": (
                    verification.verification_id
                    if verification is not None
                    else None
                ),
                "intervention_id": (
                    intervention.intervention_id
                    if intervention is not None
                    else None
                ),
                "manipulation_status": (
                    intervention.manipulation_status
                    if intervention is not None
                    else None
                ),
                "valid": bool(
                    verification is not None and verification.valid
                ),
                "manifest_match": manifest_match,
                "provenance": _provenance_payload(provenance),
            }
        )
        if (
            verification is not None
            and provenance is not None
            and intervention is not None
            and intervention.config_digest is not None
            and intervention.resolved_config is not None
        ):
            immediate_feedback.append(
                {
                    "attempt_id": experience.attempt.attempt_id,
                    "intervention_id": intervention.intervention_id,
                    "config_digest": intervention.config_digest,
                    "effective_config": intervention.resolved_config,
                    "verified_metrics": (
                        verification.verified_metrics
                        if verification.valid
                        else {}
                    ),
                    "outcome": verification.outcome,
                    "guardrail_violations": list(
                        verification.violations
                    ),
                }
            )

    final = experiences[0] if experiences else None
    verification = final.verification if final is not None else None
    final_provenance = (
        ledger.find_trial_provenance(final.observation.observation_id)
        if ledger is not None and final is not None
        else None
    )
    bound_intervention = (
        intervention_by_id.get(final_provenance.intervention_id)
        if final_provenance is not None
        else None
    )
    latest_intervention = interventions[-1] if interventions else None
    bound_manifest_match = bool(
        final is not None
        and final_provenance is not None
        and bound_intervention is not None
        and _manifest_matches(
            observation=final.observation,
            provenance=final_provenance,
            intervention=bound_intervention,
        )
    )
    manifest_match = bool(
        bound_manifest_match
        and latest_intervention is not None
        and final_provenance is not None
        and latest_intervention.intervention_id
        == final_provenance.intervention_id
    )
    metrics = (
        verification.verified_metrics
        if verification is not None
        else {}
    )
    score = metrics.get(PRIMARY_METRIC)
    valid = bool(
        return_code == 0
        and verification is not None
        and verification.valid
        and score is not None
        and final_provenance is not None
        and manifest_match
        and latest_intervention is not None
        and latest_intervention.intervention_id
        == final_provenance.intervention_id
        and latest_intervention.manipulation_status
        in {"baseline", "changed"}
    )
    failure_signature = None
    if not valid:
        if return_code != 0:
            failure_signature = f"process_exit_{return_code}"
        elif verification is not None and verification.violations:
            failure_signature = "|".join(
                sorted(verification.violations)
            )
        elif final_provenance is None:
            failure_signature = "missing_trial_provenance"
        elif (
            latest_intervention is not None
            and latest_intervention.manipulation_status
            in {"no_effect", "rejected"}
        ):
            failure_signature = (
                f"manipulation_{latest_intervention.manipulation_status}"
            )
        elif not manifest_match:
            failure_signature = "manifest_provenance_mismatch"
        else:
            failure_signature = "missing_valid_verification"

    recalled_ids = sorted(
        {
            item.knowledge_id
            for context in recall_contexts
            for item in context.items
        }
    )
    recalled_citations = sorted(
        {
            item.citation_id
            for context in recall_contexts
            for item in context.items
        }
    )
    citation_to_action = [
        {
            "knowledge_id": knowledge_id,
            "intervention_id": intervention.intervention_id,
            "knob": intervention.proposal.knob,
            "target": intervention.proposal.target,
        }
        for intervention in interventions
        for knowledge_id in intervention.proposal.cited_knowledge_ids
    ]
    intervention_rows = [
        {
            "intervention_id": intervention.intervention_id,
            "iteration_id": intervention.iteration_id,
            "proposal_digest": intervention.proposal_digest,
            "intervention_digest": intervention.intervention_digest,
            "config_digest": intervention.config_digest,
            "manipulation_status": intervention.manipulation_status,
            "knob": intervention.proposal.knob,
            "target": intervention.proposal.target,
            "cited_knowledge_ids": list(
                intervention.proposal.cited_knowledge_ids
            ),
        }
        for intervention in interventions
    ]
    provenance_payload = _provenance_payload(final_provenance)
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
        "artifact_refs": (
            [ref.path for ref in verification.evidence_refs]
            if verification is not None
            else []
        ),
        "cache_path": str(cache_path),
        "experience_store": str(store_path),
        "return_code": return_code,
        "manipulation_status": (
            latest_intervention.manipulation_status
            if latest_intervention is not None
            else "rejected"
        ),
        "manifest_match": manifest_match,
        "recall": {
            "context_count": len(recall_contexts),
            "item_count": sum(
                len(context.items) for context in recall_contexts
            ),
            "knowledge_ids": recalled_ids,
            "citation_ids": recalled_citations,
        },
        "citation_to_action": citation_to_action,
        "interventions": intervention_rows,
        "no_op_count": sum(
            intervention.manipulation_status in {"no_effect", "rejected"}
            for intervention in interventions
        ),
        "immediate_feedback": immediate_feedback,
        "attempts": attempt_rows,
        "provenance": provenance_payload,
        **{
            field: (
                provenance_payload[field]
                if provenance_payload is not None
                else None
            )
            for field in PAIR_PROVENANCE_FIELDS
        },
    }


def summarize_trials(
    trials: list[dict],
    *,
    seeds: list[int],
    model: str,
    revision: str,
) -> dict:
    indexed = {(trial["seed"], trial["arm"]): trial for trial in trials}
    paired_deltas: list[float | None] = []
    paired_provenance_match: list[bool] = []
    paired_feedback_structure_match: list[bool] = []

    def feedback_shapes(trial: dict | None) -> list[tuple[str, ...]]:
        if trial is None:
            return []
        return [
            tuple(sorted(feedback))
            for feedback in trial.get("immediate_feedback", [])
            if isinstance(feedback, dict)
        ]

    for seed in seeds:
        control = indexed.get((seed, "control"))
        treatment = indexed.get((seed, "treatment"))
        comparable = bool(
            control
            and treatment
            and control.get("manifest_match")
            and treatment.get("manifest_match")
            and all(
                control.get(field)
                and control.get(field) == treatment.get(field)
                for field in PAIR_PROVENANCE_FIELDS
            )
        )
        paired_provenance_match.append(comparable)
        paired_feedback_structure_match.append(
            bool(control and treatment)
            and feedback_shapes(control) == feedback_shapes(treatment)
        )
        if (
            comparable
            and control.get("valid")
            and treatment.get("valid")
            and control.get("score") is not None
            and treatment.get("score") is not None
        ):
            paired_deltas.append(
                round(
                    float(treatment["score"]) - float(control["score"]),
                    12,
                )
            )
        else:
            paired_deltas.append(None)
    complete = len(trials) == len(seeds) * 2
    all_valid = complete and all(bool(trial.get("valid")) for trial in trials)
    no_op_count = sum(
        trial.get("manipulation_status") in {"no_effect", "rejected"}
        for trial in trials
    )
    manipulation_valid = bool(
        complete
        and all(
            trial.get("manipulation_status") in {"baseline", "changed"}
            for trial in trials
        )
        and all(
            indexed.get((seed, "treatment"), {}).get(
                "manipulation_status"
            )
            == "changed"
            for seed in seeds
        )
    )
    semantic_memory_valid = bool(
        complete
        and all(
            (
                (control := indexed.get((seed, "control"))) is not None
                and (
                    treatment := indexed.get((seed, "treatment"))
                )
                is not None
                and int(
                    (control.get("recall") or {}).get("item_count", 0)
                    or 0
                )
                == 0
                and not control.get("citation_to_action")
                and int(
                    (treatment.get("recall") or {}).get(
                        "item_count",
                        0,
                    )
                    or 0
                )
                > 0
                and bool(treatment.get("citation_to_action"))
                and {
                    action.get("knowledge_id")
                    for action in treatment.get("citation_to_action", [])
                    if isinstance(action, dict)
                }
                <= set(
                    (treatment.get("recall") or {}).get(
                        "knowledge_ids",
                        [],
                    )
                )
                and {
                    action.get("intervention_id")
                    for action in treatment.get("citation_to_action", [])
                    if isinstance(action, dict)
                }
                <= {
                    intervention.get("intervention_id")
                    for intervention in treatment.get("interventions", [])
                    if (
                        isinstance(intervention, dict)
                        and intervention.get("manipulation_status")
                        == "changed"
                    )
                }
            )
            for seed in seeds
        )
    )
    phase_a_chain_valid = (
        all_valid
        and all(paired_provenance_match)
        and all(paired_feedback_structure_match)
        and all(delta is not None for delta in paired_deltas)
        and manipulation_valid
        and semantic_memory_valid
    )
    claim_valid = False
    numeric_deltas = [
        float(delta) for delta in paired_deltas if delta is not None
    ]
    recall_items = sum(
        int((trial.get("recall") or {}).get("item_count", 0) or 0)
        for trial in trials
    )
    recalled_knowledge_ids = sorted(
        {
            str(knowledge_id)
            for trial in trials
            for knowledge_id in (
                (trial.get("recall") or {}).get("knowledge_ids", [])
            )
        }
    )
    citation_to_action = [
        action
        for trial in trials
        for action in trial.get("citation_to_action", [])
        if isinstance(action, dict)
    ]
    intervention_digests = sorted(
        {
            intervention["intervention_digest"]
            for trial in trials
            for intervention in trial.get("interventions", [])
            if (
                isinstance(intervention, dict)
                and intervention.get("manipulation_status") == "changed"
                and intervention.get("intervention_digest")
            )
        }
    )
    intervention_rows = [
        intervention
        for trial in trials
        for intervention in trial.get("interventions", [])
        if isinstance(intervention, dict)
    ]
    intervention_no_op_count = sum(
        intervention.get("manipulation_status")
        in {"no_effect", "rejected"}
        for intervention in intervention_rows
    )
    manifest_matches = [
        bool(trial.get("manifest_match")) for trial in trials
    ]

    def arm_summary(arm: str) -> dict[str, Any]:
        selected = [
            indexed.get((seed, arm))
            for seed in seeds
        ]
        present = [trial for trial in selected if trial is not None]
        scores = [
            float(trial["score"])
            for trial in present
            if trial.get("valid") and trial.get("score") is not None
        ]
        return {
            "arm": arm,
            "scores": [
                trial.get("score") if trial is not None else None
                for trial in selected
            ],
            "mean_valid_score": (
                round(sum(scores) / len(scores), 12)
                if scores
                else None
            ),
            "valid_rate": (
                round(
                    sum(bool(trial.get("valid")) for trial in present)
                    / len(seeds),
                    12,
                )
                if seeds
                else 0.0
            ),
            "manifest_match_rate": (
                round(
                    sum(
                        bool(trial.get("manifest_match"))
                        for trial in present
                    )
                    / len(seeds),
                    12,
                )
                if seeds
                else 0.0
            ),
            "recall_item_count": sum(
                int(
                    (trial.get("recall") or {}).get(
                        "item_count",
                        0,
                    )
                    or 0
                )
                for trial in present
            ),
            "citation_to_action_count": sum(
                len(trial.get("citation_to_action", []))
                for trial in present
            ),
        }

    return {
        "schema_version": "1",
        "task_id": "one_layer_vq:task1",
        "contract": "one-layer-vq-cifar10-adaptive@3-phase-a",
        "primary_metric": PRIMARY_METRIC,
        "direction": "maximize",
        "seeds": list(seeds),
        "model": model,
        "code_revision": revision,
        "control": arm_summary("control"),
        "treatment": arm_summary("treatment"),
        "paired_deltas": paired_deltas,
        "paired_provenance_match": paired_provenance_match,
        "paired_feedback_structure_match": paired_feedback_structure_match,
        "manipulation_valid": manipulation_valid,
        "semantic_memory_valid": semantic_memory_valid,
        "phase_a_chain_valid": phase_a_chain_valid,
        "no_op_rate": (
            round(no_op_count / len(trials), 12) if trials else 0.0
        ),
        "recall": {
            "item_count": recall_items,
            "knowledge_ids": recalled_knowledge_ids,
        },
        "citation_to_action": citation_to_action,
        "distinct_intervention_count": len(intervention_digests),
        "distinct_intervention_digests": intervention_digests,
        "intervention_no_op_rate": (
            round(
                intervention_no_op_count / len(intervention_rows),
                12,
            )
            if intervention_rows
            else 0.0
        ),
        "manifest_match_rate": (
            round(sum(manifest_matches) / len(manifest_matches), 12)
            if manifest_matches
            else 0.0
        ),
        "phase_a_diagnostic_mean_paired_delta": (
            round(sum(numeric_deltas) / len(numeric_deltas), 12)
            if phase_a_chain_valid
            else None
        ),
        "experience_gain": None,
        "claim_valid": claim_valid,
        "trials": trials,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the paired closed-loop VQ Phase A harness or its "
            "preflight-only gate."
        )
    )
    parser.add_argument("--output-root", type=Path)
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=list(DEFAULT_SEEDS),
    )
    parser.add_argument("--model")
    parser.add_argument("--skip-credential-probe", action="store_true")
    parser.add_argument(
        "--trial-timeout-seconds",
        type=float,
        default=DEFAULT_TRIAL_TIMEOUT_SECONDS,
        help=(
            "Maximum wall-clock seconds for one arm before it is recorded "
            "as a failed timeout."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _unique_dry_run_root() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return DEFAULT_DRY_RUN_ROOT / f"dry-run-{stamp}-{os.getpid()}"


def _write_partial_report(
    *,
    output_root: Path,
    trials: list[dict[str, Any]],
    seeds: list[int],
    model: str,
    revision: str,
) -> Path:
    report = summarize_trials(
        trials,
        seeds=seeds,
        model=model,
        revision=revision,
    )
    report["generated_at"] = utc_now()
    report["arm_order"] = {
        str(seed): list(arm_order(index))
        for index, seed in enumerate(seeds)
    }
    report["claim_boundary"] = (
        "Phase A reports provenance and a diagnostic paired delta only. It "
        "never reports Experience Gain; a scientific claim requires the "
        "frozen development-memory and confirmatory design from later phases."
    )
    report_path = output_root / "paired_report.json"
    _atomic_json(report_path, report)
    return report_path


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    seeds = list(args.seeds)
    if not seeds or len(seeds) != len(set(seeds)):
        raise SystemExit("seeds must be non-empty and unique")
    if any(seed < 0 or seed >= 2**63 for seed in seeds):
        raise SystemExit("seeds must be in the range [0, 2**63)")
    if (
        not math.isfinite(args.trial_timeout_seconds)
        or args.trial_timeout_seconds <= 0
    ):
        raise SystemExit("trial timeout must be finite and positive")

    if args.dry_run:
        output_root = (
            args.output_root.resolve()
            if args.output_root is not None
            else _unique_dry_run_root()
        )
        try:
            prepare_dry_run(output_root=output_root, seeds=seeds)
        except Exception as exc:
            print(
                f"V3 dry-run failed: {_redacted_error(exc)}",
                file=sys.stderr,
            )
            return 2
        report_path = output_root / "dry_run_report.json"
        print(report_path)
        return 0

    _load_environment()
    model = args.model or os.getenv("COMPLETION_MODEL")
    if not model:
        raise SystemExit("COMPLETION_MODEL is not configured")
    output_root = (
        args.output_root.resolve()
        if args.output_root is not None
        else DEFAULT_OUTPUT_ROOT.resolve()
    )
    if output_root.exists() and any(output_root.iterdir()):
        raise SystemExit(
            f"refusing to overwrite non-empty output root: {output_root}"
        )
    output_root.mkdir(parents=True, exist_ok=True)
    state_path = output_root / "run_manifest.json"
    revision = source_revision()
    manifest: dict[str, Any] = {
        "schema_version": "1",
        "status": "preflight",
        "started_at": utc_now(),
        "seeds": seeds,
        "arm_order": {
            str(seed): list(arm_order(index))
            for index, seed in enumerate(seeds)
        },
        "model": model,
        "contract_path": str(CONTRACT_PATH),
        "contract_sha256": _raw_sha256(CONTRACT_PATH.read_bytes()),
        "code_revision": revision,
        "cache_policy": "disabled",
        "trial_timeout_seconds": args.trial_timeout_seconds,
        "scientific_arm_difference": "semantic_memory_only",
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
            print(
                f"Credential probe failed: {manifest['error']}",
                file=sys.stderr,
            )
            return 2

    python = Path(sys.executable)
    environment = trial_environment()
    manifest["status"] = "running"
    _atomic_json(state_path, manifest)
    failed_code = 0
    for seed_index, seed in enumerate(seeds):
        for arm_index, arm in enumerate(arm_order(seed_index)):
            port = 13000 + seed_index * 2 + arm_index
            command, cache_path, store_path = build_trial_command(
                python=python,
                model=model,
                output_root=output_root,
                seed=seed,
                arm=arm,
                port=port,
                trial_timeout_seconds=args.trial_timeout_seconds,
            )
            trial_root = output_root / f"seed-{seed}" / arm
            trial_root.mkdir(parents=True, exist_ok=True)
            log_path = trial_root / "runner.log"
            started = time.perf_counter()
            timed_out = False
            termination_kind = "process_exit"
            with log_path.open("w", encoding="utf-8") as log:
                try:
                    return_code = _run_trial_process(
                        command,
                        cwd=AGENT_ROOT,
                        environment=environment,
                        log=log,
                        timeout_seconds=args.trial_timeout_seconds,
                    )
                except subprocess.TimeoutExpired as exc:
                    timed_out = True
                    termination_kind = "timeout"
                    return_code = 124
                    _cleanup_trial_container(
                        f"vq-v3-{seed}-{arm}"
                    )
                    log.write(
                        "\nHarness timeout: "
                        + _redacted_error(exc)
                        + "\n"
                    )
                except Exception as exc:
                    termination_kind = "runner_error"
                    return_code = 1
                    log.write(
                        "\nHarness runner error: "
                        + _redacted_error(exc)
                        + "\n"
                    )
            wall_seconds = time.perf_counter() - started
            _sanitize_log_file(log_path)
            trial = collect_trial(
                seed=seed,
                arm=arm,
                cache_path=cache_path,
                store_path=store_path,
                wall_seconds=wall_seconds,
                return_code=return_code,
            )
            trial["runner_log"] = str(log_path)
            trial["timed_out"] = timed_out
            trial["termination"] = {
                "kind": termination_kind,
                "return_code": return_code,
                "timeout_seconds": (
                    args.trial_timeout_seconds if timed_out else None
                ),
            }
            if timed_out:
                trial["failure_signature"] = "trial_timeout"
            manifest["trials"].append(trial)
            _atomic_json(state_path, manifest)
            if return_code != 0:
                failed_code = return_code or 1
                break
        if failed_code:
            break

    report_path = _write_partial_report(
        output_root=output_root,
        trials=manifest["trials"],
        seeds=seeds,
        model=model,
        revision=revision,
    )
    manifest["status"] = "trial_failed" if failed_code else "completed"
    manifest["completed_at"] = utc_now()
    manifest["paired_report"] = str(report_path)
    _atomic_json(state_path, manifest)
    print(report_path)
    return failed_code


if __name__ == "__main__":
    raise SystemExit(main())
