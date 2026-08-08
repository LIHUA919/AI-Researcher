# Verified Experimentation

This context names the durable records and decisions used to test whether
verified experience improves later Experiment Attempts and to resume that work
safely. The governing designs are
[`docs/design/experience-driven-research-loop.md`](docs/design/experience-driven-research-loop.md),
[`docs/design/durable-research-runtime.md`](docs/design/durable-research-runtime.md),
[`docs/design/verified-research-memory.md`](docs/design/verified-research-memory.md),
and
[`docs/design/context-aware-tool-use.md`](docs/design/context-aware-tool-use.md).

## Language

**Hypothesis**:
A falsifiable proposed change with an expected metric effect and stated applicability conditions.
_Avoid_: Idea, suggestion

**Experiment Attempt**:
One execution of a Hypothesis bound to an exact Research Run spec and Research
Context Snapshot generation, with fixed dataset, source, Intervention, seed,
allocation, environment/execution configuration, and Evaluation Contract.
_Avoid_: Retry, run

**Intervention**:
The schema-valid, executable configuration deliberately varied for one Experiment Attempt.
_Avoid_: Tweak, prompt change, arbitrary config

**Intervention Catalog**:
The versioned allowlist of mutable knobs, permitted values, protected settings, and no-op policy for one decision point.
_Avoid_: Config file, parameter dump

**Decision Point**:
A typed moment in a pinned workflow where one bounded Recall Context may inform
one governed decision artifact. Initial values are ideation, experiment design,
intervention, diagnosis, and writing; evaluation is not a memory-consuming
Decision Point.
_Avoid_: Stage prompt, arbitrary hook, whole Research Run

**Evaluation Task ID**:
The identity of one concrete benchmark or product task instance used for pair
lineage, split isolation, and contamination checks.
_Avoid_: Task family, reusable memory scope

**Task Scope ID**:
A content-addressed, preregistered public taxonomy node used for v1 exact-match
memory applicability across different Evaluation Task IDs. It excludes seed and
evaluator-private attributes.
_Avoid_: Evaluation Task ID, embedding similarity, inferred private label

**Memory Scope**:
The normalized applicability boundary for one experiential record: namespace,
public Task Scope ID, domain, dataset, tested source/model/tool versions,
Evaluation Contract, budget, environment, and other policy-defined conditions.
It is broader than Task Scope ID and never includes evaluator-private labels.
_Avoid_: Task Scope ID alone, namespace alone, semantic similarity

**Decision Target**:
The normalized action, parameter family, procedure, or avoidable behavior whose
conditional effect a Knowledge Family describes at one Decision Point.
_Avoid_: Free-form claim text, metric alone, Decision Point alone

**Decision Intent**:
The preallocated immutable identity of one Decision Point occurrence, binding
Research Run, Runtime Activity, iteration/generation, arm/pair, Research Context
Snapshot, Evaluation Task ID, public Task Scope ID, sanitized actor-visible
contract view, preallocated logical decision slot/artifact kind, and allowed
action surface, plus a Runtime-admission-proof-backed Memory Governance Binding
that pins the memory profile/assignment manifest and whether recall is required
or registered as not requested.
_Avoid_: Free-form request, Decision Point type alone

**Manipulation Check**:
The recorded determination of whether an Intervention changed the intended executable configuration and was observed by the runner.
_Avoid_: Recall count, changed prompt

**Experience Gain**:
The preregistered paired causal difference in verified research outcome between
a memory treatment and its named baseline for the same task/seed and complete
resource boundary, aggregated by the frozen estimator. Retrieval or context
change alone is not Experience Gain.
_Avoid_: Recall hit rate, unpaired score difference, anecdotal improvement

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

**Experience Distillation Receipt**:
The immutable ingestion disposition proving that an Experience Record was
durably queued for comparison, deferred as ineligible, declared outside the
distillation policy, or terminally abandoned before enqueue under an exact
Runtime proof. The abandoned branch binds a frozen, non-inserted Work Item
payload digest and exact Experience/policy/profile lineage. It is not a
Knowledge promotion decision.
_Avoid_: Knowledge Candidate, Distillation Decision

**Distillation Work Item**:
The immutable outbox fact atomically paired with a queued Experience
Distillation Receipt. It gives Runtime a stable, restart-safe identity for later
comparative distillation; it pins a content-addressed Campaign Admission Profile
and records the deterministic Runtime Artifact reference owned by
`DISTILLATION_WORK_ITEM:<work_item_id>`. That `ACTIVE` reference is the profile
bytes' explicit GC root across source-Run termination. The Work Item ID remains
the sole `DriveRun` admission key and canonical Run/initial-command identity
input for a memory campaign. Claim leases, artifact handoff state, byte GC, and
retries remain Runtime state.
_Avoid_: In-memory job, Distillation Decision, Runtime Activity lease

**Distillation Campaign Manifest**:
The Runtime Artifact Store-owned, content-addressed specification for one
`MEMORY_DISTILLATION` Research Run, pinning its Work Items, policies, workflow,
configuration, budget, and retention from the Work Item's Admission Profile.
V1 deliberately contains exactly one Work Item; same Work Item key/different
manifest is an identity conflict rather than a second Run.
_Avoid_: Source scientific Run, mutable queue batch

**Distillation Work Assignment**:
The append-only Experiment Ledger binding from one Work Item to an exact
Distillation Campaign Manifest, non-terminal campaign Research Run, and owned
Runtime Activity before execution. The Activity remains non-claimable
`AWAITING_ASSIGNMENT` until Runtime independently read-backs the assignment proof
and activates it by CAS.
_Avoid_: Lease, claim, source Run continuation

**Distillation Commit Authorization**:
The Runtime-owned, fenced permission for one exact proposal and commit attempt.
It is pending arbitration until the Ledger atomically succeeds or returns a
no-commit conflict; an executor cannot mint or use it directly.
_Avoid_: Worker lease, proof that lifecycle CAS must succeed

**Distillation Commit Plan**:
The deterministic, content-addressed expansion of one Distillation Proposal
before Runtime authorization. It pins every proposed Batch, Report,
Disposition, Knowledge/lifecycle write, source-reachability set, expected
lifecycle and retention frontiers, and canonical output digest that the one
authorized Ledger transaction may commit. It is not itself a durable semantic
result.
_Avoid_: Mutable transaction builder, Distillation Report, authorization

**Distillation Work Completion**:
The immutable terminal reconciliation from one Distillation Work Item to its
Runtime Activity and an authorized, canonical Batch/Report/Work-Disposition
commit, typed dead letter, or typed cancellation. Successful Completion is
atomic with all semantic writes.
_Avoid_: Mutable queue status, worker heartbeat

**Distillation Work Disposition**:
The exactly-one successful-batch account for a Work Item: either covered by a
real Candidate/Decision, or a typed no-candidate result such as no comparator or
not comparable.
_Avoid_: Dead letter, fabricated rejected candidate

**Distillation Commit Conflict**:
The journaled, closed-union proof that one authorized attempt found either a
stale lifecycle head or a newly revoked reachable retention target before
semantic writes and committed no Batch/Knowledge/Completion. Runtime retires
that attempt and may re-propose only from the newly read-back lifecycle and
retention state. If both predicates hold, retention revocation deterministically
wins and the lifecycle-head arm is canonical null.
_Avoid_: Distillation failure, contested scientific evidence

**Knowledge Candidate**:
An immutable, untrusted proposed abstraction drafted from one or more verified
Experience Records under a pinned Distillation Policy. It is never directly
recallable and an LLM cannot promote it.
_Avoid_: Knowledge, reflection accepted as fact

**Knowledge Family**:
The stable identity of one conditional claim across record versions and scope
variants. A separate scope-variant identity binds the Family to one normalized
applicability scope and owns its lifecycle head.
_Avoid_: Similar wording, vector cluster

**Knowledge Record**:
A versioned, immutable conditional action-effect rule backed by comparable,
independently verified Experience Records. It states applicability, Decision
Point, governed action or avoidance, observed effect and uncertainty,
guardrails, supporting evidence, and counterevidence.
_Avoid_: Reflection, summary

**Procedure Record**:
A versioned, immutable workflow with a typed trigger, preconditions, ordered
actions, success and early-stop criteria, failure modes, compatible tools and
runtime versions, and verified Experience citations.
_Avoid_: Transcript, prompt recipe, unverified skill

**Knowledge Lifecycle Event**:
An append-only transition whose deterministic fold derives whether a Knowledge
or Procedure Record is provisional, active, contested, superseded, or
retracted. Record payloads are never edited in place.
_Avoid_: Row update, deletion, confidence overwrite

**Evidence Card**:
A bounded read model for one Decision Point containing applicability, action
implication, effect and uncertainty, support and counterevidence citations,
lifecycle disposition, and retrieval reason. Its text is untrusted data and
does not grant tool or policy authority.
_Avoid_: Prompt instruction, raw transcript, search snippet

**Recall Context**:
A content-addressed, immutable set of Evidence Cards selected for one Decision
Intent under one Recall Input Snapshot. Cards may be backed by Knowledge or
Procedure dispositions allowed by the pinned profile, or exact members of an
Evidence Snapshot; confirmatory/production profiles are active-only, while
provisional/contested access is explicit development-only. Raw ledger history is
never injected.
_Avoid_: Chat history, full memory

**Recall Decision Outcome**:
The immutable terminal account for every Decision Intent, including blocked,
not-requested control, empty, degraded, actor-failed, rejected, no-op,
completed, and cancelled decisions. It records every returned card's
disposition and binds adopted Intervention
citations to the effective executed configuration.
_Avoid_: Citation list, successful decisions only, model self-report

**Knowledge Snapshot**:
A content-addressed, read-only set of eligible Knowledge and Procedure record
versions plus trusted lifecycle position, namespace, and snapshot-selection
policy. Retrieval and index identities are excluded. Unrelated raw Experience
growth does not change it.
_Avoid_: Research Context Snapshot, Recall Context, whole-ledger digest

**Evidence Snapshot**:
A content-addressed membership list of canonical verified Experience bundles
captured at one typed namespace Evidence frontier and one Run/arm/pair
visibility scope inside a single read transaction.
_Avoid_: Timestamp cutoff, query result without members

**Retention Erasure Intent**:
The first durable fact of one authorized privacy or legal erasure incident. In
one Ledger transaction it binds the target/object generation, exact affected
index set, required lifecycle retraction when applicable, and the retention
deny-set frontier before any external deletion or invalidation occurs.
_Avoid_: External deletion receipt, tombstone, best-effort cleanup request

**Memory Retention Tombstone**:
An immutable denial marker that excludes one retracted record from snapshots
and indexes after authorized privacy/legal erasure. The canonical audit
envelope, IDs, digests, foreign-key identity, and commit journal remain. It
binds the retraction prerequisite, resolvable erasure receipt, and affected
index-invalidation acknowledgements; publication waits for reconciliation.
_Avoid_: Deleting ledger history, lifecycle retraction alone

**Recall Input Snapshot**:
The content-addressed composition of exact Knowledge and optional Evidence
Snapshots, Retrieval Policy, renderer/tokenizer, and derived-index build
receipts that one Decision Intent may query.
_Avoid_: Knowledge Snapshot, mutable “latest” alias

**Reference Card**:
A cited read model over a paper, codebase, dataset, or tool document, carrying
source identity, version, content digest, chunk/offset provenance, and Adapter
identity. It is external reference evidence, not proof that an internal
Experiment succeeded.
_Avoid_: Knowledge Record, consolidated fact

**Reference Context**:
A bounded, content-addressed set of Reference Cards supplied to Research Context
preparation or one permitted Decision Intent. It remains epistemically separate
from experiential Recall Context.
_Avoid_: Recall Context, Knowledge Snapshot, uncited search dump

**Memory Shared Identity Manifest**:
The immutable, content-addressed source/policy/model/corpus/schema/task-taxonomy
identity shared by sequential memory-evaluation stages in one release lineage.
_Avoid_: Stage campaign, mutable benchmark config

**Memory Stage Manifest**:
The immutable, content-addressed specification of one offline, ideation, A/A,
Pilot, or confirmatory campaign, including task/seed, arms, budgets, endpoints,
thresholds, and analysis identity. It references the shared identity but not a
future release root.
_Avoid_: Memory Acceptance Manifest, result report

**Memory Acceptance Manifest**:
The immutable, content-addressed release assembly root normally created after
all stages required by one requested claim ceiling have terminal closure
receipts; an audit-only invalid root may instead bind an exact open/invalid
admission set and supports no claim. It binds one shared identity, both typed
lineage-assembly and global-hidden-exposure Registry frontiers with their prefix
digests and signed authority checkpoints, exact admissions/closures and stage
refs/digests, claim kind/baseline, and typed optional status. L5 is frozen
only after Runtime release evidence exists and supersedes rather than mutates a
lower-level root.
_Avoid_: Single campaign config, mutable benchmark config, result report

**Scientific Claim Plan**:
The pre-hidden, immutable statistical decision contract for one release
lineage. It freezes the requested claim and baseline, primary and secondary
endpoints, estimands, family weights, margins, multiplicity, A/A rules,
resource boundary, transfer/robustness claims, sample-size rule, trusted
registry identities, and hidden-reserve selection commitment before any
selected hidden stage is exposed.
_Avoid_: Pilot-tuned threshold, analysis notebook, Memory Acceptance Manifest

**Pilot Gate Receipt**:
The independently validated, signed terminal `pass|fail|invalid` account for
confirmatory prerequisites and L2 audit assembly. It binds the exact offline
and all applicable selected hidden ideation, A/A, and Pilot admissions/
closures plus pre-root L0-L2 prerequisite assessments under the frozen
Scientific Claim Plan, explicitly excluding the final root-derived CA003 row.
Only `pass` authorizes confirmatory selection.
_Avoid_: Pilot report, operator approval, confirmatory result

**Acceptance Validation Receipt**:
The Validation Authority-signed final account over the pre-validation artifact
closure, Memory Acceptance Manifest, reports, Registry and Exposure frontiers,
code/environment identity, highest supported claim, and terminal
pass/fail/invalid status. Publication and an L5 claim require a valid signature,
`final_status=pass`, and an exact claim match.
_Avoid_: Self-signed report, process exit code, unsigned summary

**Stage Campaign Admission Receipt**:
The append-only proof that one Memory Stage Manifest was registered before any
hidden-corpus visibility, arm allocation, or query. A release-lineage/stage slot
has one logical admission; retry returns the original registry position.
_Avoid_: Manifest timestamp, selected successful shard

**Stage Campaign Closure Receipt**:
The append-only terminal account for an admitted evaluation campaign, including
completed, failed, invalid, insufficient-power, or aborted status and an exact
shard/failure ref+digest.
_Avoid_: Silent missing stage, mutable status file

**Research Run**:
The durable top-level execution of one canonical request under a `run_kind`
tagged spec, pinned content-addressed workflow/continuation and model/tool
configuration, and an initial Budget Envelope plus audited amendments. A
`SCIENTIFIC` Run additionally binds an Evaluation Contract and may own Research
Context Snapshots, Hypotheses, and Experiment Attempts; a
`MEMORY_DISTILLATION` Run instead binds a Distillation Campaign Manifest and may
own none of those scientific records.
_Avoid_: Experiment Attempt, trial, process, chat session

**Research Context Snapshot**:
An immutable, content-addressed bundle of task inputs, references, method review,
source and dataset identities, tool/model configuration, and the sanitized
actor-visible Decision Contract View needed by multiple Experiment Attempts. The
Research Run spec separately binds the full Evaluation Contract for verification.
The Snapshot never contains the full/private Evaluation Contract digest,
attempt-specific Recall Context, private evaluator data, treatment metadata, or
mutable workspace state.
_Avoid_: Shared cache, copied prompt, previous attempt directory

**Runtime Activity**:
One durably identified semantic stage of fallible work. It owns zero or more
external Effects such as LLM calls, tool calls, workspace materialization,
experiment execution, verification, or experience commit, plus zero or more
checkpoints. Physical execution may be at-least-once; its durable result is
committed once under stable identities.
_Avoid_: Arbitrary function call, retry, stage callback

**Effect**:
One stable logical external operation owned by a Runtime Activity, bound to a
canonical request, Adapter/version, operation identity, and reconciliation
policy. It may require multiple Physical Invocations, but selects at most one
valid receipt for downstream commit.
_Avoid_: Physical Invocation, infrastructure retry, Experiment Attempt

**Physical Invocation**:
One concrete dispatch authorization/attempt for an Effect, with its own durable
identity, worker epoch, worst-case reservation, receipt or ambiguity, and cost
settlement. Repeating an Effect creates a new Physical Invocation rather than
overwriting the previous history.
_Avoid_: Effect, Experiment Attempt, untracked SDK retry

**Durable Transition**:
The atomic append of runtime events and update of the derived Research Run state
after a Runtime Activity result, budget change, operator command, validated
watchdog deadline, or validated integrity-incident quarantine. A transition
is accepted only for the expected event sequence. Worker-authored transitions
also require the current fencing token; operator commands use their authenticated
command identity, non-cancel mutations use optimistic run version, and monotonic
Cancel may revoke the current non-terminal state even from a stale observed
version. Control commands may revoke the worker lease. A private watchdog may do
the same only through an authenticated durable-timer claim plus exact Activity
generation, progress deadline/cursor, and event-sequence CAS. A private integrity
quarantine may do so only under an active matching incident epoch/scope plus
per-Run event-sequence CAS.
_Avoid_: JSON overwrite, heartbeat update, log line

**Run Lease**:
Time-bounded authority for one worker to advance a Research Run or Runtime
Activity. Each acquisition increments a fencing token so a stale worker cannot
commit after another worker takes over.
_Avoid_: PID file, heartbeat file, best-effort lock

**Continuation Decision**:
The deterministic next Runtime Activity, wait condition, or terminal disposition
derived from the durable Research Run snapshot plus its pinned workflow and
continuation-policy digests.
_Avoid_: Implicit control flow, resume callback

**Budget Envelope**:
The durable caps, reservations, and settled usage for attempts, LLM calls,
tokens, wall time, GPU time, and parallelism within a Research Run.
_Avoid_: Iteration count, advisory token estimate

**Capability Catalog**:
An immutable, content-addressed snapshot of normalized tool descriptions and execution bindings that one Research Run may consider under pinned policy.
_Avoid_: Tool list, mutable registry snapshot

**Tool Interaction**:
A durably identified decision sequence inside one Runtime Activity that alternates model and tool Effects until it commits a direct result, clarification wait, stage-control proposal, or typed failure.
_Avoid_: Agent turn, tool loop

**Tool Decision Record**:
The immutable candidate, filtering, exposure, proposal, and directive evidence produced by one step of a Tool Interaction.
_Avoid_: Router output, selection log

**ToolFeedback**:
The bounded, untrusted, model-facing projection of a committed tool-preparation
rejection or committed tool Effect evidence and artifact references.
_Avoid_: Tool Observation, raw tool result

## Relationships

- A **Hypothesis** has one or more **Experiment Attempts**.
- Each **Experiment Attempt** executes exactly one **Intervention**.
- An **Intervention Catalog** governs every valid **Intervention** at its decision point.
- A **Manipulation Check** compares an **Intervention** with the preceding executable configuration.
- **Trial Provenance** identifies the complete execution conditions of one **Experiment Attempt**.
- An **Experiment Attempt** produces one **Observation**.
- An **Evaluation Contract** produces one **Verification Record** for an **Observation**.
- An **Experience Record** combines the preceding records without changing them.
- An **Experience Distillation Receipt** closes ingestion for an Experience
  without requiring immediate comparative promotion.
- A queued **Experience Distillation Receipt** atomically owns one
  **Distillation Work Item**; a **Distillation Work Assignment** binds it to a
  **Distillation Campaign Manifest** and campaign Runtime Activity; a later
  **Distillation Commit Plan** is authorized by Runtime and one Ledger
  transaction atomically binds **Distillation Work Completion**, Batch, Report,
  and one **Distillation Work Disposition**; a stale lifecycle head or revoked
  reachable retention target instead yields a zero-semantic-write
  **Distillation Commit Conflict**.
- Deferred distillation never dispatches from the already-terminal source Run.
  An immutable campaign manifest admits a separate non-terminal Research Run of
  kind `MEMORY_DISTILLATION`; each Work Item is append-only assigned to an
  Activity owned by that campaign Run before execution.
- A **Knowledge Candidate** cites eligible verified **Experience Records** but
  cannot be recalled.
- A **Knowledge Family** groups immutable versions of the same conditional
  action-effect claim; a separate scope variant owns one applicability-specific
  lifecycle head.
- A **Knowledge Record** cites comparable verified **Experience Records**; a
  **Procedure Record** cites verified trajectories.
- **Knowledge Lifecycle Events** derive which Knowledge and Procedure versions
  are eligible for a **Knowledge Snapshot**.
- A **Retention Erasure Intent** enters the deny set and, when applicable,
  retracts its target before external erasure begins; its reconciled **Memory
  Retention Tombstone** closes the incident while preserving the audit envelope.
- A **Recall Input Snapshot** composes one **Knowledge Snapshot**, an optional
  arm-local **Evidence Snapshot**, retrieval policies, and index receipts.
- A **Decision Intent** requests one bounded **Recall Context** of **Evidence
  Cards** from that Recall Input Snapshot.
- A **Recall Decision Outcome** closes every Decision Intent and binds each
  supplied card's disposition to the resulting decision and, when applicable,
  its executed **Trial Provenance**.
- A registered no-memory/control Intent closes with source status
  `not_requested`, no Recall Context, and zero card dispositions; it is distinct
  from a blocked recall attempt and remains in the denominator. Registration is
  proven by the immutable Memory Governance Binding already persisted in the
  Intent; an Outcome caller cannot assert it ad hoc.
- A recall-required Intent cancelled or failed after preallocation but before a
  Recall Context closes with typed `cancelled_before_recall` or
  `failed_before_recall` source status, a Runtime closure proof, null Context,
  and zero card dispositions; it is not mislabeled as `not_requested`.
- A **Reference Card** may inform Research Context or a permitted Decision Point
  but does not become experimental Knowledge without verified distillation.
- A **Memory Shared Identity Manifest** anchors sequential **Memory Stage
  Manifests** under a pre-hidden **Scientific Claim Plan**; each executed stage
  has an Admission Receipt and normally a Closure Receipt, while an unclosed
  admission can only enter an audit-only invalid root. A pass **Pilot Gate
  Receipt** authorizes use of
  the deterministic hidden confirmatory reserve, a ceiling-specific **Memory
  Acceptance Manifest** binds the exact stage refs/digests, and an **Acceptance
  Validation Receipt** is the signed terminal authority for publication and the
  highest supported memory claim.
- A `SCIENTIFIC` **Research Run** owns zero or more completed, immutable
  **Research Context Snapshots**; cancellation/failure during preparation may
  leave none, and a new completed generation supersedes rather than mutates an
  older one. A `MEMORY_DISTILLATION` Run owns no Research Context Snapshot.
- A **Runtime Activity** belongs to one Research Run and optionally one
  **Experiment Attempt**.
- A **Decision Intent** belongs to exactly one Runtime Activity; its **Recall
  Decision Outcome** is owned through that Intent and may optionally reference
  an Experiment Attempt, but neither requires an Attempt to exist.
- Every external **Effect** belongs to one Runtime Activity, and every physical
  invocation belongs to one Effect. A simple Activity may own one Effect, but an
  invocation is never a second scheduling or retry owner.
- A **Durable Transition** commits the outcome of a Runtime Activity, command,
  validated watchdog preemption, or validated incident quarantine and advances
  the Research Run event sequence.
- A **Run Lease** authorizes worker-authored Durable Transitions; a stale fencing
  token never authorizes a commit. Authenticated operator commands use
  optimistic versioning except for monotonic Cancel, and may revoke the lease.
  A private watchdog may revoke it only through an unexpired durable-timer claim
  plus exact Activity generation/progress/deadline/event-sequence CAS.
  A private incident sweeper may revoke it only for a matching active incident
  epoch/scope and per-Run event-sequence CAS.
- A **Continuation Decision** schedules the next Runtime Activity from committed
  state only.
- A **Budget Envelope** admits non-effect Activity work and allocates a distinct
  reservation before each Physical Invocation, settling it only after a receipt
  or reconciled disposition is committed.
- A **Research Context Snapshot** binds one **Capability Catalog** and the pinned
  tool-selection, execution, provider-protocol, and Adapter configuration used by
  its Research Run.
- A **Tool Interaction** belongs to exactly one **Runtime Activity** and produces
  one or more **Tool Decision Records**.
- A **Tool Decision Record** may prepare a model or tool **Effect**, but only the
  Runtime may authorize a **Physical Invocation**.
- When a **Recall Context** informs a tool-decision step under a typed **Decision
  Intent**, its **Tool Decision Record** binds the Recall Input/Context identity
  and resulting decision digest, including exact capability/argument identity
  for execution; the corresponding **Recall Decision Outcome** owns each
  Evidence Card disposition.
  Recall never grants tool authority.
- A committed tool Effect receipt may be projected as **ToolFeedback**; that
  feedback may later be cited by an Experiment Attempt's **Observation**, but it
  is not itself an Observation.

## Example dialogue

> **Developer:** “Treatment recalled two Knowledge Records. Does that pass the Manipulation Check?”
>
> **Domain expert:** “No. The Experiment Attempt must execute a different schema-valid Intervention, and its Trial Provenance must show that the runner observed the same configuration digest.”

## Flagged ambiguities

- “run” previously meant both a top-level Research Run and a single training execution. Use **Experiment Attempt** for the latter.
- “code revision” previously mixed generated artifacts with source identity. Use **Trial Provenance** and its separate source and evidence digests.
- “memory gain” previously conflated retrieval with behavior change. Use **Manipulation Check** for behavior change and reserve Experience Gain for verified outcome differences.
- “tool observation” previously risked conflating model-facing **ToolFeedback**
  with an Experiment Attempt's scientific **Observation**. Use the former only
  for bounded Effect feedback and the latter only for attempt-level raw evidence.
