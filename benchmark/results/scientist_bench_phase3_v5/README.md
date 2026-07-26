# Scientist-Bench Phase 3 V5 evidence

This directory is the durable, sanitized evidence bundle for the first
causally paired Scientist-Bench subset run. It measures whether verified recall
improves CPU functional implementation conformance under a fixed two-attempt
budget.

## Result

| Task | Memory-off mean | Closed-loop mean | Experience Gain | Paired deltas |
| --- | ---: | ---: | ---: | --- |
| Immiscible Diffusion task1 | 0.9000 | 0.7667 | -0.1333 | 0.0000, 0.0000, -0.4000 |
| FSQ task1 | 0.3424 | 0.5030 | +0.1606 | +0.3273, 0.0000, +0.1545 |
| Exphormer task1 | 0.5833 | 0.6500 | +0.0667 | +0.2000, 0.0000, 0.0000 |

Across the three tasks, mean repeated-failure rate fell from 0.2222 to 0.1111
and evaluator-valid rate remained 100% in both modes. Two tasks had positive
gain, satisfying the Phase 3 aggregate exit criteria. Immiscible Diffusion is
an important negative counterexample: verified feedback can still make a later
candidate worse.

## Experimental controls

- Model: `Qwen3-Coder-30B-A3B-Instruct`
- Seeds: `101`, `202`, `303`
- Budget: two generated candidates per mode and seed
- Pairing: the complete first provider request is content-addressed, and the
  byte-identical response is reused across memory-off and closed-loop modes
- Order: pair execution order is counterbalanced
- Score: evaluator-owned only; model output cannot set it
- Selection: best valid primary metric within the fixed budget
- Isolation: pinned Docker image, no network, private evaluator in a read-only
  named volume, candidate subprocess under an unprivileged UID
- Provenance: each report retains task, source, generator, comparison,
  manifest, recall, attempt, verification, and artifact identifiers or digests

The three task runs share source revision digest
`53cb0350f981a7bec800d361c26eaadbb86601f6a1808aa3e1d31bfaaba7dcf4`
and generator configuration digest
`40107209d66baf9c6a20eca40dc9cac1a606e9a7fbe0a279eeef752b14b688f9`.

## Evidence map

- Aggregate machine-readable result: [`summary.json`](summary.json)
- Immiscible Diffusion:
  [`report`](immiscible_diffusion_task1/experience_gain.json),
  [`artifact index`](immiscible_diffusion_task1/artifact_index.json)
- FSQ:
  [`report`](fsq_task1/experience_gain.json),
  [`artifact index`](fsq_task1/artifact_index.json)
- Exphormer:
  [`report`](exphormer_task1/experience_gain.json),
  [`artifact index`](exphormer_task1/artifact_index.json)

Each artifact index contains SHA-256 and byte size for the copied candidate,
run-log, trial-manifest, verification, recall, and knowledge evidence. Absolute
local paths and provider credentials are excluded from this bundle.

## Claim boundary

These results establish only CPU functional conformance on three
Scientist-Bench task1 Adapters. They do **not** establish diffusion training or
FID gains, VAE or codebook quality, graph-transformer accuracy or scalability,
paper reproduction, general scientific capability, or state-of-the-art
performance. Some Exphormer follow-up candidates timed out; the reports retain
those invalid trajectories while selecting the best earlier valid result.

Task semantics are based on the
[Immiscible Diffusion paper](https://arxiv.org/abs/2406.12303) and
[reference repository](https://github.com/yhli123/Immiscible-Diffusion),
the [FSQ paper](https://arxiv.org/abs/2309.15505) and
[Google Research implementation](https://github.com/google-research/google-research/tree/master/fsq),
and the [Exphormer paper](https://arxiv.org/abs/2303.06147) and
[reference repository](https://github.com/hamed1375/Exphormer).
