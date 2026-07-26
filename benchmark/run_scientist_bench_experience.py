from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from research_agent.inno.evals import (
    ExperienceBenchmarkRunner,
    OpenAICompatibleSolutionGenerator,
    ScientistBenchTrialAdapter,
    load_scientist_bench_task,
    save_experience_gain_report,
)


ROOT = Path(__file__).resolve().parents[1]
EVALUATOR_ROOT = ROOT / "benchmark" / "evaluators" / "scientist_bench"
TASKS: dict[str, dict[str, Any]] = {
    "immiscible_diffusion_task1": {
        "source": ROOT
        / "benchmark"
        / "final"
        / "diffu_flow"
        / "immiscible_diffusion.json",
        "contract": EVALUATOR_ROOT
        / "immiscible_diffusion_task1"
        / "contract.yaml",
        "interface": EVALUATOR_ROOT
        / "immiscible_diffusion_task1"
        / "interface.md",
        "domain": "diffusion-noise-assignment",
        "source_url": "https://arxiv.org/abs/2406.12303",
        "claim_scope": (
            "Scientist-Bench task1 CPU implementation conformance for globally "
            "optimal batch noise assignment and fp16 assignment inputs; no "
            "diffusion training, FID, image-quality, or speed claim."
        ),
    },
    "fsq_task1": {
        "source": ROOT / "benchmark" / "final" / "vq" / "fsq.json",
        "contract": EVALUATOR_ROOT / "fsq_task1" / "contract.yaml",
        "interface": EVALUATOR_ROOT / "fsq_task1" / "interface.md",
        "domain": "finite-scalar-quantization",
        "source_url": "https://arxiv.org/abs/2309.15505",
        "claim_scope": (
            "Scientist-Bench task1 CPU implementation conformance for FSQ "
            "bounding, normalization, and mixed-radix indexing; no autograd, "
            "VAE training, codebook-utilization, FID, or quality claim."
        ),
    },
    "exphormer_task1": {
        "source": ROOT / "benchmark" / "final" / "gnn" / "exphormer.json",
        "contract": EVALUATOR_ROOT / "exphormer_task1" / "contract.yaml",
        "interface": EVALUATOR_ROOT / "exphormer_task1" / "interface.md",
        "domain": "sparse-graph-transformer",
        "source_url": "https://arxiv.org/abs/2303.06147",
        "claim_scope": (
            "Scientist-Bench task1 CPU implementation conformance for typed "
            "local, regular-expander, and global-node interaction graph "
            "construction; no graph-transformer training, accuracy, throughput, "
            "or scalability claim."
        ),
    },
}


def _source_revision_digest() -> str:
    roots = [
        ROOT / "research_agent" / "inno" / "evals",
        ROOT / "research_agent" / "inno" / "experience",
        EVALUATOR_ROOT,
        Path(__file__).resolve(),
    ]
    files: set[Path] = set()
    for root in roots:
        if root.is_file():
            files.add(root)
        else:
            files.update(
                candidate
                for candidate in root.rglob("*")
                if candidate.is_file()
                and "__pycache__" not in candidate.parts
                and candidate.suffix not in {".pyc", ".pyo"}
            )
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def run_task(
    task_name: str,
    output_root: Path,
    *,
    generator: OpenAICompatibleSolutionGenerator,
    seeds: list[int],
    iterations: int,
):
    definition = TASKS[task_name]
    task = load_scientist_bench_task(
        definition["source"],
        task_level="task1",
        primary_metric="implementation_score",
    )
    contract_payload = __import__("yaml").safe_load(
        Path(definition["contract"]).read_text(encoding="utf-8")
    )
    evaluator_version = (
        f"{contract_payload['contract_id']}@{contract_payload['version']}"
    )
    dataset_digest = hashlib.sha256(
        (
            task.metadata["source_digest"]
            + hashlib.sha256(
                (EVALUATOR_ROOT / "evaluate.py").read_bytes()
            ).hexdigest()
            + task_name
        ).encode()
    ).hexdigest()
    trial = ScientistBenchTrialAdapter(
        output_root,
        task=task,
        evaluator_root=EVALUATOR_ROOT,
        contract_path=definition["contract"],
        interface_path=definition["interface"],
        generator=generator,
        domain=definition["domain"],
    )
    return ExperienceBenchmarkRunner(
        trial,
        require_verified_trials=True,
    ).run(
        task,
        seeds=seeds,
        model=generator.model,
        budget={
            "iterations": iterations,
            "generation_tokens": 5000,
            "recall_items": 6,
            "recall_tokens": 2500,
        },
        evaluator_version=evaluator_version,
        dataset_digest=dataset_digest,
        code_revision=_source_revision_digest(),
        metadata={
            "synthetic": False,
            "benchmark_subset": "Scientist-Bench task1",
            "source_url": definition["source_url"],
            "claim_scope": definition["claim_scope"],
            "score_authority": "independent containerized VerificationRecord",
            "pairing": "same model, seed, budget, evaluator, and source revision",
            "execution_order": "counterbalanced by pair index",
            "candidate_cache": (
                "identical first-attempt model requests are reused across modes"
            ),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tasks",
        default=",".join(TASKS),
        help=f"comma-separated subset of: {', '.join(TASKS)}",
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--seeds", default="101,202,303")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument(
        "--output-root",
        default=".ai_researcher/benchmarks/scientist-bench-phase3",
    )
    args = parser.parse_args()
    selected = [item for item in args.tasks.split(",") if item]
    unsupported = sorted(set(selected) - TASKS.keys())
    if unsupported:
        parser.error(f"unsupported tasks: {', '.join(unsupported)}")
    seeds = [int(item) for item in args.seeds.split(",") if item]
    api_key = os.getenv(args.api_key_env)
    if not api_key:
        parser.error(f"environment variable {args.api_key_env!r} is not set")
    output_root = Path(args.output_root)
    reports_root = output_root / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)
    existing = [
        reports_root / f"{task_name}.json"
        for task_name in selected
        if (reports_root / f"{task_name}.json").exists()
    ]
    if existing:
        parser.error(
            "refusing to overwrite existing reports: "
            + ", ".join(str(path) for path in existing)
        )
    generator = OpenAICompatibleSolutionGenerator(
        model=args.model,
        base_url=args.base_url,
        api_key=api_key,
    )
    report_paths: list[str] = []
    for task_name in selected:
        report = run_task(
            task_name,
            output_root,
            generator=generator,
            seeds=seeds,
            iterations=args.iterations,
        )
        report_paths.append(
            save_experience_gain_report(
                report,
                reports_root / f"{task_name}.json",
            )
        )
    summary_path = reports_root / "run_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "tasks": selected,
                "seeds": seeds,
                "iterations": args.iterations,
                "model": args.model,
                "generator_configuration_digest": (
                    generator.configuration_digest
                ),
                "source_revision_digest": _source_revision_digest(),
                "generator_cache_hits": generator.cache_hits,
                "generator_cache_misses": generator.cache_misses,
                "reports": report_paths,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
