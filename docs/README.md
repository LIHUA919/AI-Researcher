# Project documentation

This directory is the canonical home for maintained project documentation.
The repository-wide canonical domain language is maintained in
[`../CONTEXT.md`](../CONTEXT.md).

## Sections

- [`design/`](design/README.md) — architecture, system design, invariants, and
  long-lived technical decisions.
- [`implementation/`](implementation/README.md) — implementation plans,
  code-level specifications, rollout notes, and validation protocols.

## Maintenance rules

1. Put durable design documents in `docs/design/` and implementation-facing
   documents in `docs/implementation/`; do not add planning documents to
   feature or benchmark source directories.
2. Use lowercase kebab-case filenames.
3. Start each non-index document with its status, scope, owner, and last-updated
   date. Directory `README.md` index files are exempt.
4. Link a design document to its implementation documents and link each
   implementation document back to the governing design.
5. Update the relevant directory index when adding, replacing, or retiring a
   document.
6. Keep experiment output and generated reports out of `docs/`; documentation
   may link to evidence stored under `benchmark/`.
