# Implementation documents

Implementation documents translate governing designs into executable plans,
code-level contracts, rollout steps, and validation protocols.

| Document | Status | Purpose |
| --- | --- | --- |
| [Durable Research Runtime implementation plan](durable-research-runtime-plan.md) | Ready for implementation | Phased delivery, fault injection, efficiency, and scientific acceptance for Long-Task Runtime + Stage Continuation |
| [Context-Aware Tool Use implementation plan](context-aware-tool-use-plan.md) | Ready for implementation | Per-turn tool decisions, governed Effects, evaluation, rollout, and legacy deletion |
| [Verified Research Memory implementation plan](verified-research-memory-plan.md) | Ready after Phase 0 freeze | Schema, Interfaces, migration, code map, PR slices, rollout, and rollback for governed research memory |
| [Memory effectiveness evaluation protocol](memory-effectiveness-evaluation.md) | Proposed acceptance contract | Normative writer, retrieval, utilization, causal, robustness, efficiency, and claim gates |
| [Experience Gain: next-round plan](experience-gain-next-round-plan.md) | Historical strategy; Phase B active | V2 audit and response-surface calibration rationale; Phase C–E contracts are superseded by Verified Research Memory docs |
| [Experience Gain V3 Phase A specification](experience-gain-v3-phase-a-spec.md) | Implemented (`f585de4`) | Shipped code-level Phase A contract; not evidence of scientific gain |
| [One-layer VQ real-test protocol](one-layer-vq-real-test.md) | Historical V2 protocol | Real-data calibration and five-seed mechanism evidence; not the current confirmatory acceptance contract |

The governing architectures are documented in
[`../design/experience-driven-research-loop.md`](../design/experience-driven-research-loop.md),
[`../design/durable-research-runtime.md`](../design/durable-research-runtime.md),
[`../design/verified-research-memory.md`](../design/verified-research-memory.md),
and
[`../design/context-aware-tool-use.md`](../design/context-aware-tool-use.md).
