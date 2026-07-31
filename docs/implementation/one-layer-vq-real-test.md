# One-layer VQ real-test protocol

This protocol separates infrastructure smoke evidence from an Experience Gain
claim. The checked contract at
`benchmark/evaluators/one_layer_vq_smoke/contract.yaml` has a zero utilization
baseline, so passing it means only that a real two-epoch CIFAR-10 run emitted
valid raw evidence and used at least one code. It is not evidence that SimVQ or
the experience loop improved a scientific metric.

## 1. Preflight

Run from the repository root and require every command to succeed:

```bash
docker info
docker run --rm --gpus all "$BASE_IMAGES" nvidia-smi
test -n "$COMPLETION_MODEL"
test -n "$CHEEP_MODEL"
test -n "$OPENAI_API_KEY" || test -n "$ANTHROPIC_API_KEY"
.venv/bin/python -m pip check
```

The Docker image must be able to download the actual CIFAR-10 dataset, or the
official archive must be mounted into the run workspace. The bundled
`cifar10-32x32.npz` file is only FID reference statistics.

## 2. Local real-data method smoke

The local runner does not require an LLM credential or Docker GPU passthrough.
It trains the same compact encoder/decoder with either a vanilla trainable
codebook or a SimVQ-style frozen basis plus one trainable linear projection.
The following example uses Apple MPS; use `cuda` on a CUDA host:

```bash
.venv/bin/python benchmark/real_smoke/one_layer_vq/train.py \
  --output-dir benchmark/results/one_layer_vq_real_smoke/example \
  --data-dir benchmark/data/huggingface \
  --data-source huggingface \
  --device mps \
  --variant simvq \
  --seed 101 \
  --epochs 2 \
  --train-samples 8192 \
  --test-samples 1024 \
  --batch-size 128 \
  --codebook-size 128 \
  --latent-dim 16

.venv/bin/python \
  benchmark/evaluators/one_layer_vq_smoke/evaluate.py \
  benchmark/results/one_layer_vq_real_smoke/example
```

The evaluator verifies that the first 1024 raw originals match the canonical
CIFAR-10 test prefix before computing metrics. The runner records its source
SHA-256 and refuses to overwrite existing evidence by default.

The checked preliminary three-seed report is
`benchmark/results/one_layer_vq_real_smoke/paired_report.json`. Under its exact
8192-sample/two-epoch budget, mean utilization was 5.208% for both variants;
the SimVQ-style variant therefore showed no utilization gain. This is useful
negative smoke evidence, not a paper reproduction.

## 3. Agent evidence smoke and calibration

Run at least three calibration seeds in `record` mode with isolated cache,
workspace, container, and ledger paths. Example for seed 101:

```bash
cd research_agent
python run_infer_plan.py \
  --instance_path ../benchmark/final/vq/one_layer_vq.json \
  --container_name vq-calibration \
  --task_level task1 \
  --model "$COMPLETION_MODEL" \
  --workplace_name workplace \
  --cache_path ../benchmark/runs/vq-calibration/seed-101/cache \
  --port 12401 \
  --max_iter_times 0 \
  --seed 101 \
  --category vq \
  --experience-mode record \
  --experience-store ../benchmark/runs/vq-calibration/seed-101/experience.sqlite3 \
  --evaluation-contract ../benchmark/evaluators/one_layer_vq_smoke/contract.yaml \
  --cache-policy disabled
```

Inspect each Verification Record and immutable `attempt_evidence` snapshot.
Reject invalid runs; do not impute them. Before looking at paired evaluation
seeds, freeze a new versioned contract with:

- `baseline` set from the independent calibration distribution of
  `codebook_utilization`;
- `validity.metric_bounds.reconstruction_mse.maximum` and/or
  `validity.metric_bounds.reconstruction_psnr_db.minimum` set to predeclared
  reconstruction-quality tolerances;
- the exact model, code revision, codebook size, dataset digest, two-epoch
  budget, and evaluator digest recorded with the calibration report.

Do not copy ImageNet-128 paper numbers into this CIFAR-10 contract.

## 4. Paired no-recall versus recall runs

Use at least five fresh seeds. Both arms use `closed-loop` and the same
three-attempt cap. The control arm sets `--recall-item-budget 0`, which preserves
the same retry/evaluation machinery but withholds recalled Knowledge Records.
The treatment arm sets the budget to 8. Give every arm and seed separate cache
and ledger paths.

Control-arm additions:

```text
--experience-mode closed-loop
--max-loop-iterations 3
--recall-item-budget 0
--recall-token-budget 0
```

Treatment-arm additions:

```text
--experience-mode closed-loop
--max-loop-iterations 3
--recall-item-budget 8
--recall-token-budget 3000
```

Keep every other argument identical within a seed pair, including the frozen
calibrated contract. Alternate arm order across seeds. Report all scores,
paired deltas, validity rate, repeated-failure rate, attempts used, wall time,
token use, and GPU hours. The existing deterministic benchmark is only an
infrastructure fixture and must not be mixed into this report.

The frozen second-round launcher automates that exact comparison with seeds
401, 502, 603, 704, and 805:

```bash
.venv/bin/python benchmark/run_one_layer_vq_closed_loop_v2.py
```

It first makes a one-token credential probe, refuses to overwrite an existing
run directory, alternates arm order, and writes progress after every trial.
The final report is emitted only after all ten trials finish. Its
`experience_gain` remains null unless every seed pair has valid raw-evidence
verification.

## 5. Claim boundary

A real smoke run is complete when the external evaluator validates raw CIFAR-10
indices and reconstructions. An Experience Gain claim additionally requires a
frozen calibrated contract, fresh paired seeds, no cross-arm/cross-seed memory,
and actual resource-use accounting. Equal caps alone are not proof of equal
compute.
