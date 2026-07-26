from datetime import datetime, timezone
import hashlib
from pathlib import Path

import pytest

from research_agent.inno.experience import (
    ArtifactRef,
    CommandVerifier,
    ContainerVerifier,
    Observation,
    load_evaluation_contract,
)


ROOT = Path(__file__).resolve().parents[2]
EVALUATOR_DIR = ROOT / "benchmark" / "evaluators" / "scientist_bench"
NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)

IMMISCIBLE_SOLUTION = """
import itertools
import struct


def _half(value):
    return struct.unpack("e", struct.pack("e", value))[0]


def assign_noise(images, noises, use_fp16=False):
    cast = _half if use_fp16 else float
    def cost(permutation):
        return sum(
            sum(
                (cast(x) - cast(y)) ** 2
                for x, y in zip(images[row], noises[column])
            )
            for row, column in enumerate(permutation)
        )
    return list(min(itertools.permutations(range(len(noises))), key=cost))
""".strip()

FSQ_SOLUTION = """
import math


def quantize(values, levels, eps=1e-3):
    result = []
    for value, level in zip(values, levels):
        half_l = (level - 1) * (1 - eps) / 2
        offset = 0.0 if level % 2 else 0.5
        shift = math.tan(offset / half_l)
        bounded = math.tanh(value + shift) * half_l - offset
        result.append(round(bounded) / (level // 2))
    return result


def codes_to_index(codes, levels):
    result = 0
    basis = 1
    for code, level in zip(codes, levels):
        half_width = level // 2
        result += round(code * half_width + half_width) * basis
        basis *= level
    return result


def index_to_codes(index, levels):
    result = []
    basis = 1
    for level in levels:
        half_width = level // 2
        digit = (index // basis) % level
        result.append((digit - half_width) / half_width)
        basis *= level
    return result
""".strip()

EXPHORMER_SOLUTION = """
import random


def build_interaction_graph(
    num_nodes,
    local_edges,
    expander_degree,
    num_global_nodes,
    seed,
):
    edges = set()
    for source, target in local_edges:
        edges.add((source, target, "local"))
        edges.add((target, source, "local"))

    order = list(range(num_nodes))
    random.Random(seed).shuffle(order)
    for offset in range(1, expander_degree // 2 + 1):
        for index, source in enumerate(order):
            target = order[(index + offset) % num_nodes]
            edges.add((source, target, "expander"))
            edges.add((target, source, "expander"))
    if expander_degree % 2:
        for index in range(num_nodes // 2):
            source = order[index]
            target = order[index + num_nodes // 2]
            edges.add((source, target, "expander"))
            edges.add((target, source, "expander"))

    for global_node in range(num_nodes, num_nodes + num_global_nodes):
        for node in range(num_nodes):
            edges.add((node, global_node, "global"))
            edges.add((global_node, node, "global"))
    return [list(edge) for edge in sorted(edges)]
""".strip()


def _artifact(path: Path) -> ArtifactRef:
    content = path.read_bytes()
    return ArtifactRef(
        path=str(path),
        sha256=hashlib.sha256(content).hexdigest(),
        media_type="text/plain",
        size_bytes=len(content),
    )


def _observation(attempt_dir: Path, solution: str) -> Observation:
    solution_path = attempt_dir / "solution.py"
    solution_path.write_text(solution + "\n", encoding="utf-8")
    log_path = attempt_dir / "run.log"
    log_path.write_text("candidate generated\n", encoding="utf-8")
    return Observation(
        observation_id=hashlib.sha256(solution.encode()).hexdigest(),
        attempt_id="attempt-1",
        exit_code=0,
        metrics={},
        artifact_refs=[_artifact(solution_path), _artifact(log_path)],
        started_at=NOW,
        completed_at=NOW,
        environment_fingerprint="python=3.11",
    )


@pytest.mark.parametrize(
    ("task_name", "solution"),
    [
        ("immiscible_diffusion_task1", IMMISCIBLE_SOLUTION),
        ("fsq_task1", FSQ_SOLUTION),
        ("exphormer_task1", EXPHORMER_SOLUTION),
    ],
)
def test_reference_candidates_satisfy_scientist_bench_contract(
    tmp_path,
    task_name,
    solution,
):
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    contract = load_evaluation_contract(
        EVALUATOR_DIR / task_name / "contract.yaml"
    )

    verification = CommandVerifier(contract_dir=EVALUATOR_DIR).verify(
        contract,
        _observation(attempt_dir, solution),
    )

    assert verification.valid is True, verification.violations
    assert verification.passed is True
    assert verification.verified_metrics["implementation_score"] == pytest.approx(1)
    assert verification.public_feedback == []


def test_fsq_contract_returns_bounded_category_feedback(tmp_path):
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    contract = load_evaluation_contract(
        EVALUATOR_DIR / "fsq_task1" / "contract.yaml"
    )
    incomplete = """
def quantize(values, levels, eps=1e-3):
    return [round(value) for value in values]

def codes_to_index(codes, levels):
    return 0

def index_to_codes(index, levels):
    return [0.0] * len(levels)
""".strip()

    verification = CommandVerifier(contract_dir=EVALUATOR_DIR).verify(
        contract,
        _observation(attempt_dir, incomplete),
    )

    assert verification.valid is True
    assert verification.passed is False
    assert verification.verified_metrics["implementation_score"] < 0.9
    assert 0 < len(verification.public_feedback) <= 6
    assert all("expected" not in item.lower() for item in verification.public_feedback)


@pytest.mark.skipif(
    __import__("os").getenv("RUN_DOCKER_TESTS") != "1",
    reason="requires an explicitly enabled Docker daemon",
)
def test_candidate_cannot_read_root_only_evaluator_snapshot(tmp_path):
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    contract = load_evaluation_contract(
        EVALUATOR_DIR / "immiscible_diffusion_task1" / "contract.yaml"
    )
    probing_solution = """
from pathlib import Path

def assign_noise(images, noises, use_fp16=False):
    Path("/evaluator/evaluate.py").read_text()
    return list(range(len(noises)))
""".strip()

    verification = ContainerVerifier(contract_dir=EVALUATOR_DIR).verify(
        contract,
        _observation(attempt_dir, probing_solution),
    )

    assert verification.valid is True, verification.violations
    assert verification.passed is False
    assert any(
        "candidate execution failed" in item.lower()
        for item in verification.public_feedback
    )
