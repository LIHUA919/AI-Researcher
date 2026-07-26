# Inno-Bench: Benchmarking System-Level AI-Researcher with Expert-Level Ground Truth

Run the offline paired Experience Gain fixture with:

```bash
python -m benchmark.run_experience_benchmark
```

It writes `benchmark/results/deterministic_experience_gain.json`. The fixture
validates pairing, reporting, cost, variance, and failure-rate calculations; it
is explicitly synthetic and is not evidence of Scientist-Bench improvement.

Real comparisons should load a task with `load_scientist_bench_task`, use the
same model, seeds, budget, evaluator, dataset, and code revision for both
`off` and `closed-loop` modes, and retain all referenced trial artifacts.

## Behavioral loop checks

The deterministic behavioral benchmark exercises the real ledger, evaluator,
Knowledge Gate, cited Recall Context, restart path, and two-iteration loop:

```bash
python -m benchmark.run_local_experience_benchmark \
  --output-root .ai_researcher/benchmarks/local-experience-gain
```

The optional model smoke benchmark replaces only the deterministic selection
policy with a real OpenAI-compatible model:

```bash
python -m benchmark.run_model_experience_smoke \
  --model YOUR_MODEL \
  --base-url https://your-provider.example/v1 \
  --api-key-env YOUR_PROVIDER_API_KEY \
  --output-root .ai_researcher/benchmarks/model-experience-smoke
```

Use a fresh output root for each independent benchmark execution. The generated
report contains paired trial results and artifact references in addition to
summary means, variance, validity, repeated failures, token use, and wall time.

These are controlled behavioral checks. Neither should be reported as
Scientist-Bench evidence.

## Verified Scientist-Bench subset

The first executable subset contains three task1 Evaluation Contract Adapters:

- Immiscible Diffusion global batch noise assignment;
- Finite Scalar Quantization bounds, normalization, and mixed-radix indexes;
- Exphormer typed local, regular-expander, and global-node graph construction.

Run a task with a fresh output root:

```bash
python -m benchmark.run_scientist_bench_experience \
  --tasks fsq_task1 \
  --model Qwen3-Coder-30B-A3B-Instruct \
  --base-url https://your-provider.example/v1 \
  --api-key-env YOUR_PROVIDER_API_KEY \
  --iterations 2 \
  --output-root .ai_researcher/benchmarks/fsq-task1
```

The runner uses isolated evaluator-owned scoring, exact first-request pairing,
counterbalanced mode order, a fixed attempt budget, and strict provenance
checks. Export raw run roots with
`benchmark/export_scientist_bench_evidence.py`; the exporter refuses to
overwrite existing evidence.

The checked-in
[Phase 3 V5 evidence](results/scientist_bench_phase3_v5/README.md) reports
positive gain on FSQ and Exphormer, negative gain on Immiscible Diffusion,
lower aggregate repeated-failure rate, and unchanged valid rate. Its claim is
limited to CPU functional conformance. It is not evidence of paper-scale
training, FID, model quality, downstream accuracy, or state-of-the-art
performance.
