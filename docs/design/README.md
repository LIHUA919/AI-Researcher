# Design documents

Design documents use the canonical domain language in
[`../../CONTEXT.md`](../../CONTEXT.md) and define architecture, invariants,
interfaces, and major technical decisions.

| Document | Status | Purpose |
| --- | --- | --- |
| [Experience-Driven Research Loop](experience-driven-research-loop.md) | Proposed | Governing design for turning verified Research Runs into reusable experience |
| [Durable Research Runtime and Stage Continuation](durable-research-runtime.md) | Proposed | Governing design for recoverable long tasks and Research-Run-scoped continuation |
| [Verified Research Memory](verified-research-memory.md) | Proposed | Governing memory data-plane design for evidence distillation, lifecycle, decision-point recall, use trace, and Knowledge Snapshot |
| [Context-Aware Tool Use and Governed Tool Effects](context-aware-tool-use.md) | Proposed | Governing design for deciding when and how to expose and execute tools |

Implementation plans and code-level specifications live in
[`../implementation/`](../implementation/README.md).
