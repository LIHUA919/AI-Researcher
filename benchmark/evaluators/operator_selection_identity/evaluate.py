from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


HIDDEN_INPUTS = (-5, -2, -1, 0, 1, 3, 8)


def main(attempt_dir: str) -> int:
    root = Path(attempt_dir)
    solution_path = root / "solution.py"
    spec = importlib.util.spec_from_file_location("candidate_solution", solution_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load candidate solution")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    correct = sum(
        module.transform(value) == value
        for value in HIDDEN_INPUTS
    )
    result = {
        "metrics": {"score": correct / len(HIDDEN_INPUTS)},
        "repetitions": 1,
        "failed_repetitions": 0,
    }
    (root / "verification_result.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
