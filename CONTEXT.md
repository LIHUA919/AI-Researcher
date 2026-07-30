# Verified Experimentation

This context names the durable records and decisions used to test whether verified experience improves later research attempts. The detailed governing design remains `docs/design/experience-driven-research-loop.md`.

## Language

**Hypothesis**:
A falsifiable proposed change with an expected metric effect and stated applicability conditions.
_Avoid_: Idea, suggestion

**Experiment Attempt**:
One execution of a Hypothesis under a fixed dataset, source, Intervention, seed, budget, environment, and Evaluation Contract.
_Avoid_: Retry, run

**Intervention**:
The schema-valid, executable configuration deliberately varied for one Experiment Attempt.
_Avoid_: Tweak, prompt change, arbitrary config

**Intervention Catalog**:
The versioned allowlist of mutable knobs, permitted values, protected settings, and no-op policy for one decision point.
_Avoid_: Config file, parameter dump

**Manipulation Check**:
The recorded determination of whether an Intervention changed the intended executable configuration and was observed by the runner.
_Avoid_: Recall count, changed prompt

**Trial Provenance**:
The immutable identity of the source, Intervention, execution configuration, dataset plan, environment, Evaluation Contract, and resulting evidence for an Experiment Attempt.
_Avoid_: Code revision, metadata

**Observation**:
The untrusted raw result, artifacts, metrics, timing, and exit status produced by an Experiment Attempt.
_Avoid_: Result, finding

**Evaluation Contract**:
The task-specific, versioned rules that define required evidence, evaluator identity, metrics, validity, and success.
_Avoid_: Test config, prompt rubric

**Verification Record**:
The immutable result of applying an Evaluation Contract to an Observation.
_Avoid_: Judge response, score

**Experience Record**:
The immutable combination of a Hypothesis, Experiment Attempt, Observation, Verification Record, and analysis.
_Avoid_: Memory

**Knowledge Record**:
A reusable abstraction backed by one or more verified Experience Records.
_Avoid_: Reflection, summary

**Recall Context**:
A bounded, cited snapshot of Knowledge Records selected for one decision.
_Avoid_: Chat history, full memory

## Relationships

- A **Hypothesis** has one or more **Experiment Attempts**.
- Each **Experiment Attempt** executes exactly one **Intervention**.
- An **Intervention Catalog** governs every valid **Intervention** at its decision point.
- A **Manipulation Check** compares an **Intervention** with the preceding executable configuration.
- **Trial Provenance** identifies the complete execution conditions of one **Experiment Attempt**.
- An **Experiment Attempt** produces one **Observation**.
- An **Evaluation Contract** produces one **Verification Record** for an **Observation**.
- An **Experience Record** combines the preceding records without changing them.
- A **Knowledge Record** cites one or more verified **Experience Records**.
- A **Recall Context** supplies selected **Knowledge Records** to a later Intervention decision.

## Example dialogue

> **Developer:** “Treatment recalled two Knowledge Records. Does that pass the Manipulation Check?”
>
> **Domain expert:** “No. The Experiment Attempt must execute a different schema-valid Intervention, and its Trial Provenance must show that the runner observed the same configuration digest.”

## Flagged ambiguities

- “run” previously meant both a top-level Research Run and a single training execution. Use **Experiment Attempt** for the latter.
- “code revision” previously mixed generated artifacts with source identity. Use **Trial Provenance** and its separate source and evidence digests.
- “memory gain” previously conflated retrieval with behavior change. Use **Manipulation Check** for behavior change and reserve Experience Gain for verified outcome differences.
