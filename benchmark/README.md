# Inno-Bench: Benchmarking System-Level AI-Researcher with Expert-Level Ground Truth

Run the offline paired Experience Gain fixture with:

```bash
python benchmark/run_experience_benchmark.py
```

It writes `benchmark/results/deterministic_experience_gain.json`. The fixture
validates pairing, reporting, cost, variance, and failure-rate calculations; it
is explicitly synthetic and is not evidence of Scientist-Bench improvement.

Real comparisons should load a task with `load_scientist_bench_task`, use the
same model, seeds, budget, evaluator, dataset, and code revision for both
`off` and `closed-loop` modes, and retain all referenced trial artifacts.
