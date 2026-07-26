# Scientist-Bench executable contracts

This directory is one evaluator Module with three task Adapters:

- `immiscible_diffusion_task1`: verifies batch-wise globally optimal L2
  image/noise assignment and optional fp16 assignment inputs.
- `fsq_task1`: verifies the official finite scalar quantization bounding,
  normalization, and mixed-radix index semantics.
- `exphormer_task1`: verifies the local, regular-expander, and global-node
  components of a sparse typed interaction graph.

The evaluator runs in the repository's pinned, networkless container. Candidate
code is invoked in a separate process with resource limits and, in the
container, a non-root uid. The evaluator snapshot is readable only by root, so
candidate code cannot inspect the cases or reference implementation.

These are CPU functional-conformance contracts. They do not train a model and
do not support claims about FID, codebook utilization, or training speed.
