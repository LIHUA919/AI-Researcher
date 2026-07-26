# ADR-0003: Causally paired Scientist-Bench trials

- Status: accepted
- Date: 2026-07-26

## Context

A memory-off/closed-loop score difference is not evidence of Experience Gain
unless the comparison controls model requests, evaluator ownership, execution
budget, task inputs, and artifact provenance. Provider nondeterminism can make
the first candidates differ even when prompts appear equivalent. Selecting the
last attempt can also hide a valid earlier implementation, while accepting a
model-reported score lets the candidate grade itself.

Scientist-Bench tasks additionally contain private evaluator logic that must
not be readable by candidate code. Read-only host bind mounts are insufficient
for that boundary on every Docker Desktop configuration.

## Decision

The `ScientistBenchTrialAdapter` is the deep Module for one verified trial. Its
public Interfaces are a code-only `SolutionGenerator`, a versioned task
Evaluation Contract, and an independent `Verifier`.

The Adapter:

- accepts candidate source and rationale but never a candidate-authored score;
- places the private evaluator in a Docker named volume populated by a trusted
  container, runs evaluation without networking, and executes candidate code
  under an unprivileged UID;
- gives memory-off and closed-loop modes the same model, seed, task, dataset,
  code revision, evaluator, cache policy, and fixed attempt budget;
- content-addresses the complete provider request and reuses the byte-identical
  first response across paired modes;
- counterbalances mode execution order across seeds;
- selects the best valid evaluator-owned primary metric within the fixed
  budget, while retaining every attempt and Verification Record;
- records task, interface, dataset, evaluator, container, generator, manifest,
  comparison, recall-snapshot, attempt, and verification identifiers or
  digests;
- refuses strict paired reports when required provenance is absent or the two
  modes do not share one comparison digest.

The initial task Adapters cover CPU functional conformance for:

- Immiscible Diffusion batch noise assignment;
- Finite Scalar Quantization bounding, normalization, and mixed-radix indexes;
- Exphormer typed local, regular-expander, and global-node graph construction.

These Adapters do not run paper-scale training and cannot support claims about
FID, model quality, downstream accuracy, throughput, scalability, or the
scientific state of the art.

## Consequences

- Provider request caching is part of the causal design, not a performance
  optimization.
- Closed-loop follow-up requests may differ because verified feedback is the
  treatment being measured; the paired first request may not.
- A valid trial score always traces to an isolated evaluator result.
- Invalid and timed-out follow-up attempts remain visible even when an earlier
  valid attempt is selected.
- The published V5 run meets the Phase 3 aggregate exit criteria on this
  three-task subset: positive gain on FSQ and Exphormer, lower mean
  repeated-failure rate, and unchanged valid rate.
- Immiscible Diffusion is a retained counterexample with negative gain, so the
  result is evidence for task-dependent functional improvement rather than
  universal self-improvement.
- Candidate search remains a separate Phase 4 treatment and must not be folded
  into the memory-gain claim.
