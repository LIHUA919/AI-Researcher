from __future__ import annotations

import json
from pathlib import Path
import sys


def main(attempt_dir: str) -> int:
    root = Path(attempt_dir)
    metrics = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
    result = {
        "metrics": {"score": float(metrics["score"])},
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
