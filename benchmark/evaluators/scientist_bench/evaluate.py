from __future__ import annotations

import itertools
import json
import math
import os
from pathlib import Path
import random
import resource
import struct
import subprocess
import sys
import tempfile
from typing import Any, Callable


_CANDIDATE_RUNNER = r"""
import importlib.util
import json
from pathlib import Path
import sys

solution_path = Path(sys.argv[1])
function_name = sys.argv[2]
spec = importlib.util.spec_from_file_location("candidate_solution", solution_path)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load candidate")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
function = getattr(module, function_name)
payload = json.load(sys.stdin)
result = function(**payload)
json.dump({"result": result}, sys.stdout, allow_nan=False)
"""


def _demote_and_limit() -> None:
    memory_bytes = 256 * 1024 * 1024
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    if os.geteuid() == 0:
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)


def _call_candidate(
    attempt_dir: Path,
    function_name: str,
    payload: dict[str, Any],
) -> tuple[Any | None, str | None]:
    runner_path = Path(tempfile.gettempdir()) / "scientist_bench_candidate.py"
    runner_path.write_text(_CANDIDATE_RUNNER, encoding="utf-8")
    runner_path.chmod(0o644)
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                str(runner_path),
                str(attempt_dir / "solution.py"),
                function_name,
            ],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=attempt_dir,
            preexec_fn=_demote_and_limit,
        )
    except subprocess.TimeoutExpired:
        return None, "candidate_timeout"
    except OSError as exc:
        return None, f"candidate_start_error:{type(exc).__name__}"
    if completed.returncode != 0:
        stderr = completed.stderr
        if "ModuleNotFoundError" in stderr or "No module named" in stderr:
            return None, "candidate_missing_dependency"
        if "SyntaxError" in stderr:
            return None, "candidate_syntax_error"
        if "NameError" in stderr:
            return None, "candidate_name_error"
        if "TypeError" in stderr:
            return None, "candidate_type_or_signature_error"
        if "PermissionError" in stderr:
            return None, "candidate_sandbox_access_denied"
        return None, f"candidate_exit_code:{completed.returncode}"
    if len(completed.stdout) > 1024 * 1024:
        return None, "candidate_output_too_large"
    try:
        envelope = json.loads(completed.stdout)
        return envelope["result"], None
    except (json.JSONDecodeError, KeyError, TypeError):
        return None, "candidate_output_not_json"


def _fp16(value: float) -> float:
    return struct.unpack("e", struct.pack("e", value))[0]


def _assignment_cost(
    images: list[list[float]],
    noises: list[list[float]],
    assignment: tuple[int, ...] | list[int],
    *,
    use_fp16: bool,
) -> float:
    cast: Callable[[float], float] = _fp16 if use_fp16 else float
    return sum(
        sum(
            (cast(image_value) - cast(noise_value)) ** 2
            for image_value, noise_value in zip(
                images[row],
                noises[noise_index],
                strict=True,
            )
        )
        for row, noise_index in enumerate(assignment)
    )


def _optimal_assignment_cost(
    images: list[list[float]],
    noises: list[list[float]],
    *,
    use_fp16: bool,
) -> float:
    return min(
        _assignment_cost(
            images,
            noises,
            permutation,
            use_fp16=use_fp16,
        )
        for permutation in itertools.permutations(range(len(noises)))
    )


def _immiscible_cases() -> list[dict[str, Any]]:
    rng = random.Random(807_2024)
    cases: list[dict[str, Any]] = [
        {
            "images": [[0.0], [2.0], [4.0]],
            "noises": [[3.9], [0.1], [2.2]],
            "use_fp16": False,
            "category": "basic",
        },
        {
            "images": [[0.0, 2.0], [1.0, -1.0], [3.0, 0.5], [-2.0, 1.0]],
            "noises": [[0.9, -0.8], [-1.8, 1.1], [3.2, 0.4], [0.2, 1.7]],
            "use_fp16": False,
            "category": "multidimensional",
        },
        {
            "images": [[0.0], [0.0], [2.0], [3.0]],
            "noises": [[0.0], [1.0], [2.0], [3.0]],
            "use_fp16": False,
            "category": "ties",
        },
        {
            "images": [[0.33331], [0.33351], [1.0001], [-0.9999]],
            "noises": [[0.33349], [-1.0001], [0.33329], [0.9998]],
            "use_fp16": True,
            "category": "fp16",
        },
    ]
    for size, dimensions, use_fp16 in ((6, 3, False), (7, 2, True)):
        cases.append(
            {
                "images": [
                    [rng.uniform(-3, 3) for _ in range(dimensions)]
                    for _ in range(size)
                ],
                "noises": [
                    [rng.uniform(-3, 3) for _ in range(dimensions)]
                    for _ in range(size)
                ],
                "use_fp16": use_fp16,
                "category": "fp16" if use_fp16 else "global_optimum",
            }
        )
    return cases


def _evaluate_immiscible(attempt_dir: Path) -> dict[str, Any]:
    cases = _immiscible_cases()
    valid_outputs = 0
    optimal_outputs = 0
    fp16_total = 0
    fp16_optimal = 0
    failed_categories: set[str] = set()
    execution_errors: set[str] = set()
    for case in cases:
        if case["use_fp16"]:
            fp16_total += 1
        result, error = _call_candidate(
            attempt_dir,
            "assign_noise",
            {
                "images": case["images"],
                "noises": case["noises"],
                "use_fp16": case["use_fp16"],
            },
        )
        if error is not None:
            execution_errors.add(error)
            failed_categories.add(case["category"])
            continue
        size = len(case["images"])
        structurally_valid = (
            isinstance(result, list)
            and all(isinstance(item, int) and not isinstance(item, bool) for item in result)
            and sorted(result) == list(range(size))
        )
        if not structurally_valid:
            failed_categories.add(case["category"])
            continue
        valid_outputs += 1
        actual = _assignment_cost(
            case["images"],
            case["noises"],
            result,
            use_fp16=case["use_fp16"],
        )
        expected = _optimal_assignment_cost(
            case["images"],
            case["noises"],
            use_fp16=case["use_fp16"],
        )
        optimal = math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
        if optimal:
            optimal_outputs += 1
        else:
            failed_categories.add(case["category"])
        if case["use_fp16"]:
            fp16_optimal += int(optimal)

    total = len(cases)
    permutation_rate = valid_outputs / total
    optimal_rate = optimal_outputs / total
    fp16_rate = fp16_optimal / fp16_total
    score = 0.75 * optimal_rate + 0.15 * permutation_rate + 0.1 * fp16_rate
    feedback: list[str] = []
    if permutation_rate < 1:
        feedback.append("Some outputs were not complete one-to-one permutations.")
    if optimal_rate < 1:
        feedback.append(
            "Some assignments did not achieve the global minimum total squared L2 cost."
        )
    if fp16_rate < 1:
        feedback.append("The fp16-before-cost assignment behavior was not fully correct.")
    if execution_errors:
        feedback.append(
            "Candidate execution failed in one or more cases: "
            + ", ".join(sorted(execution_errors))
        )
    if failed_categories:
        feedback.append(
            "Failing behavior categories: " + ", ".join(sorted(failed_categories))
        )
    return {
        "metrics": {
            "implementation_score": score,
            "optimal_assignment_rate": optimal_rate,
            "permutation_validity_rate": permutation_rate,
            "fp16_assignment_rate": fp16_rate,
        },
        "repetitions": total,
        "failed_repetitions": 0,
        "public_feedback": feedback,
    }


def _fsq_quantize(values: list[float], levels: list[int], eps: float) -> list[float]:
    output: list[float] = []
    for value, level in zip(values, levels, strict=True):
        half_l = (level - 1) * (1 - eps) / 2
        offset = 0.0 if level % 2 == 1 else 0.5
        shift = math.tan(offset / half_l)
        bounded = math.tanh(value + shift) * half_l - offset
        quantized = round(bounded)
        output.append(quantized / (level // 2))
    return output


def _fsq_index_to_codes(index: int, levels: list[int]) -> list[float]:
    codes: list[float] = []
    basis = 1
    for level in levels:
        digit = (index // basis) % level
        half_width = level // 2
        codes.append((digit - half_width) / half_width)
        basis *= level
    return codes


def _fsq_codes_to_index(codes: list[float], levels: list[int]) -> int:
    index = 0
    basis = 1
    for code, level in zip(codes, levels, strict=True):
        half_width = level // 2
        index += round(code * half_width + half_width) * basis
        basis *= level
    return index


def _float_list_close(actual: Any, expected: list[float]) -> bool:
    return (
        isinstance(actual, list)
        and len(actual) == len(expected)
        and all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and math.isclose(float(value), target, rel_tol=1e-9, abs_tol=1e-9)
            for value, target in zip(actual, expected, strict=True)
        )
    )


def _evaluate_fsq(attempt_dir: Path) -> dict[str, Any]:
    quantize_cases = [
        ([0.25, 0.6, -7.0], [3, 5, 4], 1e-3, "mixed_levels"),
        ([0.0, 0.0, 0.0], [4, 6, 8], 1e-3, "even_offset"),
        ([-10.0, 10.0, 0.49], [5, 5, 5], 1e-3, "saturation"),
        ([1.2, -0.8, 2.7], [7, 4, 3], 1e-2, "custom_epsilon"),
        ([-0.1, 0.1], [6, 5], 1e-3, "rounding"),
        ([50.0, -50.0], [8, 9], 1e-3, "saturation"),
    ]
    quantize_passes = 0
    failed_categories: set[str] = set()
    execution_errors: set[str] = set()
    for values, levels, eps, category in quantize_cases:
        result, error = _call_candidate(
            attempt_dir,
            "quantize",
            {"values": values, "levels": levels, "eps": eps},
        )
        expected = _fsq_quantize(values, levels, eps)
        if error is None and _float_list_close(result, expected):
            quantize_passes += 1
        else:
            failed_categories.add(category)
            if error:
                execution_errors.add(error)

    index_cases = [
        ([3, 5, 4], [0, 1, 17, 59]),
        ([4, 4], [0, 5, 15]),
        ([5, 6, 7], [0, 31, 94, 209]),
    ]
    encode_passes = 0
    decode_passes = 0
    index_total = 0
    for levels, indexes in index_cases:
        for index in indexes:
            expected_codes = _fsq_index_to_codes(index, levels)
            decoded, decode_error = _call_candidate(
                attempt_dir,
                "index_to_codes",
                {"index": index, "levels": levels},
            )
            encoded, encode_error = _call_candidate(
                attempt_dir,
                "codes_to_index",
                {"codes": expected_codes, "levels": levels},
            )
            index_total += 1
            decode_ok = decode_error is None and _float_list_close(
                decoded, expected_codes
            )
            encode_ok = (
                encode_error is None
                and isinstance(encoded, int)
                and not isinstance(encoded, bool)
                and encoded == _fsq_codes_to_index(expected_codes, levels)
            )
            decode_passes += int(decode_ok)
            encode_passes += int(encode_ok)
            if not decode_ok or not encode_ok:
                failed_categories.add("mixed_radix_indexing")
            for error in (decode_error, encode_error):
                if error:
                    execution_errors.add(error)

    quantize_rate = quantize_passes / len(quantize_cases)
    encode_rate = encode_passes / index_total
    decode_rate = decode_passes / index_total
    score = 0.6 * quantize_rate + 0.2 * encode_rate + 0.2 * decode_rate
    feedback: list[str] = []
    if quantize_rate < 1:
        feedback.append(
            "Bounding, rounding, or normalization was incorrect for some level sets."
        )
    if encode_rate < 1 or decode_rate < 1:
        feedback.append(
            "The mixed-radix code/index mapping was not a complete round trip."
        )
    if execution_errors:
        feedback.append(
            "Candidate execution failed in one or more cases: "
            + ", ".join(sorted(execution_errors))
        )
    if failed_categories:
        feedback.append(
            "Failing behavior categories: " + ", ".join(sorted(failed_categories))
        )
    return {
        "metrics": {
            "implementation_score": score,
            "quantization_rate": quantize_rate,
            "index_encoding_rate": encode_rate,
            "index_decoding_rate": decode_rate,
        },
        "repetitions": len(quantize_cases),
        "failed_repetitions": 0,
        "public_feedback": feedback,
    }


def _edge_set(value: Any) -> set[tuple[int, int, str]] | None:
    if not isinstance(value, list):
        return None
    edges: set[tuple[int, int, str]] = set()
    for edge in value:
        if (
            not isinstance(edge, list)
            or len(edge) != 3
            or not isinstance(edge[0], int)
            or isinstance(edge[0], bool)
            or not isinstance(edge[1], int)
            or isinstance(edge[1], bool)
            or edge[2] not in {"local", "expander", "global"}
        ):
            return None
        edges.add((edge[0], edge[1], edge[2]))
    if len(edges) != len(value):
        return None
    return edges


def _exphormer_case_score(
    edges: set[tuple[int, int, str]] | None,
    *,
    num_nodes: int,
    local_edges: list[list[int]],
    expander_degree: int,
    num_global_nodes: int,
) -> dict[str, bool]:
    if edges is None:
        return {
            "structure": False,
            "local": False,
            "expander": False,
            "global": False,
        }
    total_nodes = num_nodes + num_global_nodes
    structure = all(
        0 <= source < total_nodes
        and 0 <= target < total_nodes
        and source != target
        for source, target, _ in edges
    )
    expected_local = {
        directed
        for source, target in local_edges
        for directed in (
            (source, target, "local"),
            (target, source, "local"),
        )
    }
    actual_local = {edge for edge in edges if edge[2] == "local"}
    local_ok = actual_local == expected_local

    expander = {edge for edge in edges if edge[2] == "expander"}
    expander_pairs = {(source, target) for source, target, _ in expander}
    expander_ok = (
        all(source < num_nodes and target < num_nodes for source, target in expander_pairs)
        and len(expander_pairs) == num_nodes * expander_degree
        and all(
            sum(source == node for source, _ in expander_pairs) == expander_degree
            for node in range(num_nodes)
        )
        and all((target, source) in expander_pairs for source, target in expander_pairs)
    )

    global_ids = range(num_nodes, total_nodes)
    expected_global = {
        directed
        for global_node in global_ids
        for node in range(num_nodes)
        for directed in (
            (node, global_node, "global"),
            (global_node, node, "global"),
        )
    }
    actual_global = {edge for edge in edges if edge[2] == "global"}
    global_ok = actual_global == expected_global
    expected_count = (
        len(expected_local)
        + num_nodes * expander_degree
        + 2 * num_nodes * num_global_nodes
    )
    structure = structure and len(edges) == expected_count
    return {
        "structure": structure,
        "local": local_ok,
        "expander": expander_ok,
        "global": global_ok,
    }


def _evaluate_exphormer(attempt_dir: Path) -> dict[str, Any]:
    cases = [
        (8, [[0, 1], [1, 2], [4, 7]], 2, 1, 11),
        (10, [[0, 9], [2, 3], [3, 7], [5, 6]], 4, 2, 29),
        (12, [[0, 1], [6, 7]], 3, 1, 47),
        (14, [[1, 8], [2, 9], [3, 10]], 6, 0, 71),
        (16, [], 5, 3, 97),
        (20, [[0, 19], [4, 5], [11, 12]], 8, 2, 131),
    ]
    category_passes = {
        "structure": 0,
        "local": 0,
        "expander": 0,
        "global": 0,
        "determinism": 0,
    }
    execution_errors: set[str] = set()
    seed_sensitive = False
    for case_index, (
        num_nodes,
        local_edges,
        expander_degree,
        num_global_nodes,
        seed,
    ) in enumerate(cases):
        payload = {
            "num_nodes": num_nodes,
            "local_edges": local_edges,
            "expander_degree": expander_degree,
            "num_global_nodes": num_global_nodes,
            "seed": seed,
        }
        first, first_error = _call_candidate(
            attempt_dir,
            "build_interaction_graph",
            payload,
        )
        repeated, repeated_error = _call_candidate(
            attempt_dir,
            "build_interaction_graph",
            payload,
        )
        first_edges = _edge_set(first)
        repeated_edges = _edge_set(repeated)
        checks = _exphormer_case_score(
            first_edges,
            num_nodes=num_nodes,
            local_edges=local_edges,
            expander_degree=expander_degree,
            num_global_nodes=num_global_nodes,
        )
        for category, passed in checks.items():
            category_passes[category] += int(passed)
        deterministic = (
            first_error is None
            and repeated_error is None
            and first_edges is not None
            and first_edges == repeated_edges
        )
        category_passes["determinism"] += int(deterministic)
        for error in (first_error, repeated_error):
            if error:
                execution_errors.add(error)
        if case_index == 1 and first_edges is not None:
            changed, changed_error = _call_candidate(
                attempt_dir,
                "build_interaction_graph",
                {**payload, "seed": seed + 1},
            )
            changed_edges = _edge_set(changed)
            first_expander = {
                edge for edge in first_edges if edge[2] == "expander"
            }
            changed_expander = (
                {edge for edge in changed_edges if edge[2] == "expander"}
                if changed_edges is not None
                else set()
            )
            seed_sensitive = (
                changed_error is None
                and bool(first_expander)
                and first_expander != changed_expander
            )
            if changed_error:
                execution_errors.add(changed_error)

    total = len(cases)
    rates = {
        category: passes / total
        for category, passes in category_passes.items()
    }
    score = (
        0.1 * rates["structure"]
        + 0.2 * rates["local"]
        + 0.3 * rates["expander"]
        + 0.2 * rates["global"]
        + 0.15 * rates["determinism"]
        + 0.05 * int(seed_sensitive)
    )
    feedback: list[str] = []
    if rates["structure"] < 1:
        feedback.append(
            "Some outputs had invalid, duplicate, self-loop, or non-linear typed edges."
        )
    if rates["local"] < 1:
        feedback.append("Local input edges were not preserved in both directions.")
    if rates["expander"] < 1:
        feedback.append(
            "The original-node expander component was not simple, symmetric, and d-regular."
        )
    if rates["global"] < 1:
        feedback.append(
            "Global nodes were not connected bidirectionally to exactly all original nodes."
        )
    if rates["determinism"] < 1 or not seed_sensitive:
        feedback.append(
            "Seed behavior was not both deterministic and sensitive to a changed seed."
        )
    if execution_errors:
        feedback.append(
            "Candidate execution failed in one or more cases: "
            + ", ".join(sorted(execution_errors))
        )
    return {
        "metrics": {
            "implementation_score": score,
            "structure_rate": rates["structure"],
            "local_edge_rate": rates["local"],
            "regular_expander_rate": rates["expander"],
            "global_edge_rate": rates["global"],
            "determinism_rate": rates["determinism"],
            "seed_sensitivity": float(seed_sensitive),
        },
        "repetitions": total,
        "failed_repetitions": 0,
        "public_feedback": feedback,
    }


def main(task_name: str, attempt_dir_value: str) -> int:
    attempt_dir = Path(attempt_dir_value)
    evaluators = {
        "immiscible_diffusion_task1": _evaluate_immiscible,
        "fsq_task1": _evaluate_fsq,
        "exphormer_task1": _evaluate_exphormer,
    }
    try:
        result = evaluators[task_name](attempt_dir)
    except Exception as exc:
        result = {
            "metrics": {},
            "repetitions": 0,
            "failed_repetitions": 1,
            "public_feedback": [f"Evaluator failure: {type(exc).__name__}"],
        }
    (attempt_dir / "verification_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
