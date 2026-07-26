# ADR-0001: Verification-first experience loop

- Status: accepted
- Date: 2026-07-25

## Context

Research-agent output, judge prose, and self-reported metrics can be incomplete
or wrong. Persisting those outputs directly as reusable memory lets unsupported
claims influence later Hypotheses.

## Decision

Generated output is not Knowledge. Only an independently produced, valid
Verification Record may make an Experience Record eligible for deterministic
Knowledge promotion.

SQLite is the canonical local ledger and the filesystem stores large
artifacts. Semantic indexes are derived and rebuildable. Candidate search,
distributed execution, cross-user sharing, and model-weight updates are
deferred until a single-Hypothesis Improvement Cycle demonstrates real,
paired Experience Gain.

## Consequences

- Runtime completion may require persisted verification.
- Failed and negative Experiment Attempts remain immutable evidence.
- Recall Context items always carry citations and source Experience IDs.
- Evaluation isolation and provenance are release requirements.
- Synthetic gain fixtures prove plumbing only, not self-improvement.
