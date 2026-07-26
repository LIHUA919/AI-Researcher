# ADR-0002: Dependency profiles

- Status: accepted
- Date: 2026-07-25

## Context

The previous default installation pulled browser automation, document
conversion, speech, video, vector search, UI, and large machine-learning
packages even when a caller only needed the core runtime or ledger. This made
the package Interface expensive and made clean-environment verification harder.

## Decision

The default installation contains only the core agent and experience-loop
runtime. Research, browser, document, media, UI, development, and full
capabilities are explicit optional dependency profiles. `uv.lock` is the
canonical resolved development dependency set.

## Consequences

- Core imports and CLI smoke tests must work with default dependencies.
- Feature-specific modules may require the matching optional profile.
- CI installs locked dependencies rather than resolving an unconstrained
  environment on every run.
- Full local research setup uses the `full` and `dev` profiles.
