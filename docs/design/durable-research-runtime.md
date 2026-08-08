# Durable Research Runtime and Stage Continuation

**Status:** Proposed

**Audience:** maintainers implementing long-running, recoverable research work

**Scope:** durable execution, recovery, continuation, budget control, and
Research-Run-scoped work reuse for both provided-idea and reference-ideation flows

**Owner:** AI-Researcher maintainers

**Last updated:** 2026-07-31

**Implementation plan:**
[Durable Research Runtime implementation plan](../implementation/durable-research-runtime-plan.md)

**Related governing designs:**
[Experience-Driven Research Loop](experience-driven-research-loop.md) and
[Verified Research Memory](verified-research-memory.md)

**Tool-use governing design:**
[Context-Aware Tool Use and Governed Tool Effects](context-aware-tool-use.md)

**Authority:** [`CONTEXT.md`](../../CONTEXT.md) owns domain identity. The
experience design owns scientific Attempt/Observation/Verification/Experience
semantics; the memory design owns Decision Intent, Recall Decision Outcome, and
Experience Distillation Receipt semantics; the tool-use design owns capability
eligibility, exposure, proposal, and authorization contracts. This document and
Long-Task Runtime exclusively execute and durably commit final authorization,
Effect, Physical Invocation, budget, retry, reconciliation, and terminal-state
transitions.

## 1. Decision

AI-Researcher will implement two Runtime-owned deep Modules behind three
programmatic Interface entrypoints:

```python
class LongTaskRuntime:
    def apply(self, command: RuntimeCommand) -> CommandReceipt: ...
    def inspect(self, query: RunQuery) -> ResearchRunSnapshot: ...


class StageContinuation:
    def plan(self, request: ContinuationRequest) -> ContinuationPlan: ...
```

Application code uses only `LongTaskRuntime.apply()` and
`LongTaskRuntime.inspect()`. `StageContinuation.plan()` is the single internal
Seam between durable orchestration and workflow policy. It is a pure,
deterministic function over committed state.

Agent Runtime Activities additionally use the internal pure
`ToolInteraction.advance()` Seam defined by the tool-use governing design. It
computes model/tool/commit/wait directives from committed state but never
creates or executes an Effect. Long-Task Runtime remains the only Effect,
Physical Invocation, budget, retry, reconciliation, and commit authority.

Automatic recovery also exposes one operational Interface,
`python -m research_agent.runtime.launcher --root ...`, to a process supervisor.
It is not an application lifecycle API: its flags, exit codes, readiness,
signals, and drain behavior are specified in section 13.1, while journal,
lease, and coordinator helpers remain private Implementation details.

The first Implementation will be local-first:

- SQLite is the authoritative event journal and state projection store;
- content-addressed filesystem artifacts hold large immutable payloads;
- current in-process, local subprocess, and Docker execution remain behind
  Runtime Activity Adapters;
- the existing `AdaptiveExperimentRunner` remains the attempt-scoped execution
  Module;
- existing JSON status files become compatibility projections, never a second
  source of truth;
- Temporal, LangGraph, Redis, Kubernetes, Postgres, and general OS-process
  checkpointing are not v1 dependencies.

This design promises **at-least-once physical execution and logically-once
durable commits**. It does not promise universal physical exactly-once effects.

## 2. What “1 + 2 implemented” means

The two requested capabilities are inseparable at the recovery Seam:

1. **Long-Task Runtime Module** owns durable identity, commands, events, leases,
   fencing, effect receipts, budgets, retries, cancellation, recovery, and
   completion semantics.
2. **Stage Continuation Module** decides which committed work can be reused,
   which work is invalidated, and the one next Runtime Activity for the pinned
   workflow and continuation-policy digests.

They are implemented only when a Research Run can be interrupted at every
semantic Activity seam, resumed by another worker without inventing or losing
scientific records, and can reuse one immutable Research Context Snapshot across
multiple Experiment Attempts.

Merely restarting a Python process, skipping files that already exist, or
calling the same flow again does not satisfy this definition.

## 3. Current-state evidence

The repository has useful primitives, but it does not yet have this capability.

| Current Implementation | Observed behavior | Consequence |
| --- | --- | --- |
| `runtime/master.py` | fixed linear stage order; artifact scanning, status, heartbeat, failure reporting, and hooks share one class | broad Interface with low Depth and weak state Locality |
| `inno_common.py` | appends stage JSONL and overwrites the whole `stage_state.json` | no transaction, compare-and-swap, lease, or fencing |
| `runtime/heartbeat.py` | overwrites independent heartbeat and status JSON; corrupt JSON becomes `{}` | status projections can disagree and corruption can fail open |
| `runtime/research_pipeline.py` | callers manually call `complete_stage`, `progress`, and `finalize`; verification defaults to optional | callers know ordering and a run may complete without a durable Verification Record |
| `runtime/supervisor.py` | stale heartbeat restarts the whole child process | no stage cursor, effect reconciliation, process-group cancellation, or stale-worker fencing |
| `runtime/improvement_cycle.py` | each iteration starts another complete attempt flow | no durable attempt cursor or run-wide budget |
| `run_infer_plan.py` / `run_infer_idea.py` | each Experiment Attempt creates a new `InnoFlow` and attempt cache | `prepare`, `survey`, and planning work are repeated and cannot be safely shared |
| `runtime/experience_adapter.py` | final runtime status, attempt cache, and experience ledger are committed through different paths | a crash can leave multiple notions of “complete” |

The Supervisor is currently wired mainly through the soak path, while normal
CLI and web execution bypass it. A live background heartbeat can also hide a
stalled long operation because worker authority and scientific progress are not
separate signals.

Current runtime tests are predominantly happy-path tests with hand-authored
artifacts and fake processes. They do not demonstrate recovery after a real
kill, concurrent takeover, ambiguous external effects, budget settlement,
process-tree cancellation, or cross-attempt continuation.

## 4. Intended effect and claim limits

### 4.1 What the two Modules should improve

| Dimension | Long-Task Runtime | Stage Continuation | Combined release claim |
| --- | --- | --- | --- |
| infrastructure faults | recover committed work and reject stale writes | restart at the next semantic Activity | measured recovery and no false completion |
| cost and latency | adds small bookkeeping overhead | removes repeated run-scoped Agent work | lower calls, tokens, and serial wall time |
| scientific validity | requires durable verification and provenance | preserves scope and invalidation rules | no successful run without valid evidence |
| model reasoning | no direct improvement | no direct improvement when decisions are held fixed | noninferiority, not “smarter AI” |
| long-horizon capacity | permits hours/days of operational execution | keeps a durable semantic cursor | longer operational duration, not automatically a longer cognitive horizon |

The release must not equate uptime with research intelligence. LongDS reports
large degradation from early to late subtasks and finds that simply adding more
steps does not necessarily help. METR likewise reports no statistically
significant time-horizon improvement from same-model specialized scaffolds in
its tested setting. Those results support a conservative claim: Runtime and
Continuation remove infrastructure and repetition losses; scientific gains
must be measured separately.

### 4.2 Cost model from the repository baseline

The previous VQ experiment measured, per unit it labeled `trial` (treated here
as one distinct Research Run):

- 133.5 LLM calls;
- 1,289,839 tokens;
- 44.28 minutes of serial wall time;
- three Experiment Attempts;
- about 9,662 tokens and 19.82 non-training seconds per call.

The following scenarios are planning estimates, not acceptance results. They
hold the observed average token/time per call constant and separate the
one-time Research Context Snapshot from attempt work.

| Scenario | Snapshot calls | Calls per actual Attempt | Calls, first Research Run | Estimated tokens | Estimated minutes | Run throughput | Speedup vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| conservative | 45 | 7 | 66 | 638k | 21.98 | 2.73/hour | 2.0x |
| target | 24 | 6 | 42 | 406k | 14.06 | 4.27/hour | 3.1x |
| aggressive | 12 | 5 | 27 | 261k | 9.10 | 6.59/hour | 4.9x |

For a campaign of ten distinct Research Runs that share an identical snapshot
scope through explicit import events, the same scenarios
estimate 5.1x, 6.4x, and 8.0x serial speedups respectively. The governing hard
gate therefore targets at least 80% call reduction over a ten-Run campaign,
not an unsupported “one order of magnitude” claim.

The release also has an unamortized first-Run ceiling of 66 calls, 650k tokens,
and 23 minutes. Campaign amortization cannot hide a one-off Research Run that is
slower or more expensive than the legacy baseline.

At the hard campaign ceilings, `1 - 255 / 1,335` is an 80.90% call reduction,
`1 - 2.5M / 12.89839M` is an 80.62% token reduction, and `442.8 / 90` is at least a
4.92x serial-wall speedup. Ten Runs in 90 minutes equal 6.67 Runs/hour, so the
separate 6.5/hour gate is a consistency check rather than a looser substitute.

The old combination of “5–7 calls per Attempt,” exactly three Attempts, and
“at least 90% fewer calls per Research Run” is arithmetically inconsistent. A
90% reduction permits at most 13.35 calls per Run, while three Attempts already
need at least 15 calls before snapshot work. The 90% target remains a stretch
gate only if either:

- attempt work reaches at most four calls per Attempt and snapshot cost is
  sufficiently amortized; or
- early stopping reduces the campaign average to at most 2.4 Attempts at five calls
  each, with about 1.2 amortized snapshot calls per Run.

### 4.3 Capability forecast

With model, tools, Evaluation Contract, and Experiment Attempts held fixed, the
expected direct capability change from these two Modules is approximately zero;
the acceptance target is a paired noninferiority margin of 2 percentage points.

A later experiment may reinvest saved budget in more verified Experiment
Attempts. A plausible planning hypothesis is a 3–10 percentage-point absolute
gain on verifier-rich tasks, but it is explicitly **not** an implementation
claim. It can be claimed only after the cost-normalized experiment in the
implementation plan succeeds across multiple task families.

For infrastructure faults, let `f` be the fraction of otherwise viable runs
lost to recoverable faults, `r` the recovery probability, and `q` the
conditional scientific success probability. The recoverable absolute pass gain
is approximately `q × f × r`. Until `f` is instrumented, a capability percentage
cannot be honestly forecast from recovery alone.

## 5. Domain model and invariants

The canonical vocabulary is defined in [`CONTEXT.md`](../../CONTEXT.md). The
Runtime adds no alternative name for a Hypothesis, Experiment Attempt,
Observation, Verification Record, or Experience Record.

### 5.1 Identities and scopes

```text
Research Run
  ├── Research Context Snapshot generation
  ├── Runtime Activity
  │     └── Decision Intent
  │           └── Recall Decision Outcome
  └── Hypothesis
        └── Experiment Attempt
              ├── Intervention
              ├── Trial Provenance
              ├── Observation
              ├── Verification Record
              └── Experience Record
                    └── Experience Distillation Receipt
```

A Runtime Activity may optionally belong to an Experiment Attempt, but a
Decision Intent and its Recall Decision Outcome are owned through that Activity;
they may exist before an Attempt is opened and are not reparented later.

Each identity is immutable. A retry of physical execution keeps the same
Experiment Attempt and Runtime Activity identity. A changed Intervention, seed,
Attempt allocation, or other execution condition within the pinned spec creates
a new Experiment Attempt. A changed Evaluation Contract creates a new Research
Run.

### 5.2 Hard invariants

1. A `run_id` is permanently bound to one canonical `spec_digest`; the same ID
   with different content is a conflict.
2. Event sequence, snapshot version, snapshot generation, stage generation, and
   fencing token are monotonic.
3. A normal worker-authored Durable Transition requires matching lease owner and
   epoch and `store_time < lease_expires_at` at commit. An authenticated operator
   command uses optimistic run version rather than acquiring the worker lease.
   The closed private system-control union is `WatchdogPreempted |
   RunQuarantined`: watchdog authority requires an unexpired durable timer claim
   plus exact Activity generation/progress/deadline/event-sequence CAS; incident
   authority requires an active matching incident epoch/scope plus per-Run event-
   sequence CAS. Operator or system-control transitions that affect execution
   atomically revoke the lease and advance the fencing token; none can be blocked
   by a still-renewing worker.
4. An accepted Durable Transition atomically appends events and updates the
   projection at the expected event sequence.
5. Runtime Activities and external effects use stable idempotency keys that do
   not contain a retry number.
6. Artifacts are immutable, content-addressed, and bound to a scope, input
   digest, contract version, and producer identity.
7. A Research Context Snapshot contains no attempt-specific Recall Context,
   private evaluator labels, or mutable workspace state.
8. One Experiment Attempt has exactly one Hypothesis, Intervention, seed,
   Budget Envelope allocation, Evaluation Contract, and Trial Provenance.
9. One Observation belongs to exactly one Experiment Attempt.
10. A Verification Record binds the exact Observation digest, Evaluation
    Contract version, and evaluator digest.
11. A `SCIENTIFIC` Run's `COMPLETED` requires all required stages, every completion-required valid
    Verification Record and durable Experience Record, one Recall Decision
    Outcome for every Run-owned Decision Intent, and one durable Experience
    Distillation Receipt for every completion-required Experience Record. The
    Verification Record may report `passed=true` or `passed=false`; a valid
    negative result is completed scientific work, not a Runtime failure.
    The receipt may queue later comparison, defer an ineligible Experience,
    mark distillation not required, or record a proof-authorized
    `abandoned_before_enqueue` terminal recovery; completion never requires
    immediate Knowledge promotion. Every queued receipt additionally requires a read-back
    `BOUND` Campaign Admission Profile handoff and an `ACTIVE` Runtime artifact
    reference owned by `DISTILLATION_WORK_ITEM:<work_item_id>`; the reference is
    not source-Run-owned and therefore preserves bytes without keeping that Run
    open.
    A `MEMORY_DISTILLATION` Run instead validates the manifest's exact ordered
    Work Item set: every manifest slot has exactly one matching Assignment to
    the deterministic campaign Activity, no foreign item is assigned, and every
    slot has one terminal DistillationWorkCompletion. Missing assignment is not
    an empty campaign and cannot satisfy completion. It never fabricates
    scientific Verification/Experience records.
12. **All terminal states close preallocated records.** Before
    `COMPLETED | FAILED | CANCELLED`, every Run-owned preallocated Decision Intent
    has exactly one terminal Recall Decision Outcome. Cancellation/failure writes
    the corresponding `cancelled | actor_failed | blocked` outcome under memory
    policy. Every already-existing completion-required Experience Record has its
    unique Experience Distillation Receipt. A failed/cancelled Run need not
    fabricate a Verification, Experience, or Intent that never existed.
13. No terminal Research Run transition is legal while any physical invocation
    lacks a final known/not-executed disposition or an explicit audited
    worst-case-settled abandonment, any budget reservation remains open, or any
    Run-owned execution remains unreconciled—including task/thread, process
    group, or container—or a Run-scoped lease/role assignment remains held.
    Active Run-owned artifact staging/materialization claims, artifact-filesystem
    mutation actors, and active Snapshot Build Claims must also be published,
    released, revoked, exited, or reconciled.
    Shared launcher/control/executor service processes are not Run-owned and
    need not exit. Scientific completion alone
    does not satisfy this operational settlement barrier.
13. A stale worker, duplicate command, replayed receipt, corrupt artifact, or
    incomplete projection can never manufacture `COMPLETED`.

## 6. The three programmatic Interface entrypoints

### 6.1 Long-Task Runtime Module

```python
class LongTaskRuntime(Protocol):
    def apply(self, command: RuntimeCommand) -> CommandReceipt:
        """Durably accept one idempotent lifecycle or drive command."""

    def inspect(self, query: RunQuery) -> ResearchRunSnapshot:
        """Read one consistent projection plus events after a cursor."""
```

`RuntimeCommand` is a closed union in v1:

```python
RuntimeCommand = (
    DriveRun
    | PauseRun
    | ResumeRun
    | CancelRun
    | AmendBudget
    | ResolveRun
)
```

`DriveRun` is create-or-schedule. On first use it binds `run_id` to a frozen
`ResearchRunSpec`; afterward it durably asserts that an eligible, non-paused run
should be driven. `apply()` returns after command acceptance and ready-work state
are committed; it never waits on an unbounded model, tool, or training Activity.
A private control role inside the Module polls and executes bounded coordinator
quanta, while executor roles run claimed external work. `DriveRun` never
silently resumes a deliberately paused run.

The local Implementation is a client/server split hidden behind this Interface.
`apply()` and `inspect()` use an authenticated local Unix-domain socket to one
supervised control-role process; CLI/Web and executor processes never open an
authoritative SQLite write transaction. The control role validates peer
credentials and request digests, commits commands/queries, and returns receipts.
If it dies after commit but before reply, command replay returns `DUPLICATE`; if
unavailable before durable acceptance, the client returns typed
`RuntimeUnavailable`, never a guessed success. Executor roles perform external
work and submit guarded commit proposals/evidence to the control role.

Every command contains a stable `command_id`. Mutating an existing Research Run
also carries `expected_version`, except monotonic `CancelRun`: cancellation of a
non-terminal Run is accepted against the current version even if the UI's
observed version is stale, while a terminal Run returns `TERMINAL_NOOP`.
For a `MEMORY_DISTILLATION` Run whose exact manifest already has only `completed`
Work Completions, logical work is committed even if record/operational barriers
have not yet advanced the Run terminal projection. A new CancelRun returns
`TOO_LATE_COMMITTED`, does not enter `CANCELLING`, and drives/reconciles the
remaining barriers toward `COMPLETED/ALL_COMPLETED` only when no independently
authenticated non-work failure is already latched/applicable. If such failure
won before terminal CAS, Cancel is closure-assist/no-op and final mapping is
`FAILED/RUNTIME_FAILURE_AFTER_WORK`.
For a singleton `MEMORY_DISTILLATION` Activity with an unresolved
`DistillationCommitAuthorization`, CancelRun is durably accepted as
`PENDING_AFTER_ARBITRATION`: it records a cancel intent but does not revoke the
in-flight attempt or enter `CANCELLING` yet. Atomic Ledger success resolves the
intent as `TOO_LATE_COMMITTED` and completes the campaign; a proven
`NO_COMMIT_CONFLICT` retires the authorization and applies the pending cancel
before any retry. The Ledger result—not authorization timing—is the logical
commit linearization point.

The same receipt disposition applies while a Decision Intent admission
authorization or `DecisionRecallCommitAuthorization` is unresolved. Cancel/failure is latched as
pending control without revoking that append attempt; exact Intent/Context/Outcome
Ledger success or proved no-commit is reconciled before the control cause grants
a closure Outcome or proceeds past an already-committed immutable Outcome.

A permanent failure detected during either unresolved family follows the same
arbitration with a pending failure intent and no early fence revocation. For
Distillation only, Ledger success first commits the Work Completion and the
still-applicable non-work failure enters
`FAILING/RUNTIME_FAILURE_AFTER_WORK`; no-commit retires and dead-letters before
retry. For Intent/Context/Outcome append, success/no-commit first reconciles the
per-Intent phase, then grants the exact actor-failure closure Outcome when one is
still missing or preserves an already-committed immutable Outcome.
For either authorization family, pending cancel and pending ordinary closure
failure are selected by one Run-version/control-event CAS: cancel-first suppresses
only duplicate/cancellation-induced failure, while failure-first makes a later
Cancel closure-help/no-op. An independently authenticated integrity/contract/
Runtime-infrastructure failure is never discarded: it is appended as secondary
failure evidence and re-evaluated after arbitration. On Ledger success it may
turn a too-late cancel into `FAILED/RUNTIME_FAILURE_AFTER_WORK`; on no-commit it
forces the safe failure/dead-letter path before any retry.
That same transaction closes new-work admission immediately. While pending, no
new Activity claim, Effect/Invocation, Intent admission, Context grant, or normal
Outcome grant may begin; only the exact already-granted authorization and its
receipt/no-commit reconciliation are grandfathered. Every other already-in-flight
normal semantic commit and Activity-advance predicate also fails while the flag is
set; adapters may still capture late receipts/evidence, settle budget, terminate,
and reconcile, but cannot select those bytes into new semantic state. Closure authorization may be
issued only after that arbitration resolves. Preserving one fence for the active
attempt never means accepting unrelated work after durable cancellation.
Replaying the same ID and payload returns a deterministic `DUPLICATE` receipt
that preserves and references the original acceptance version/event sequence;
reusing the ID with different content is a conflict.

Command precedence is normative. After authentication/protocol validation,
control resolves an existing `command_id` first: a different payload is
`CommandIdentityConflict`, otherwise it returns the stored deterministic
`DUPLICATE`. It then validates immutable Run identity and terminal-noop
semantics before applying current incident/admission gates. Therefore an
incident created after commit but before reply cannot change a retry into
`IncidentFenced`. For a previously unseen command, monotonic `CancelRun` is the
fail-safe exception that bypasses the incident gate; another mutation of a
matching existing Run returns `IncidentFenced`, while a new-Run `DriveRun` in a
closed scope returns `AdmissionClosed`.

Operator commands do not wait for or acquire the current worker lease. An
accepted `PauseRun`, `AmendBudget`, or `ResolveRun` uses command identity plus
optimistic version; `CancelRun` uses its monotonic rule. When a command can
affect execution it atomically revokes the current lease by advancing the
fencing token. This lets an operator
preempt a stuck lease while making every late worker commit fail. `ResolveRun`
binds a `wait_id` to one typed disposition such as confirmed-effect receipt,
confirmed-not-executed, abandon, or reference to externally updated
credential/provider availability under the already-pinned behavioral
configuration. It cannot change workflow/model/tool/policy/contract digests; a
behavioral change requires a new Research Run. It also records operator identity, affected effect/request digest,
reason, and evidence reference. Command payloads never contain credentials or
other secrets.

`ResearchRunSpec` is the closed tagged union
`ScientificResearchRunSpec | MemoryDistillationResearchRunSpec`. Both arms include:

- `run_id`;
- closed `run_kind: SCIENTIFIC | MEMORY_DISTILLATION`; the pinned workflow and
  terminal contract must be valid for that kind;
- pinned, content-addressed workflow-definition reference/version/digest;
- pinned, content-addressed continuation-policy reference/version/digest;
- pinned, content-addressed Runtime/Adapter interpreter-contract bundle
  references/versions/digests required to interpret those artifacts;
- model/tool configuration digests;
- immutable input artifact references;
- Budget Envelope;
- explicit data-retention and execution policy.

The `SCIENTIFIC` arm additionally requires task identity, provided-idea or
reference-ideation request, the full Evaluation Contract for the verification
plane, and its sanitized actor-visible `DecisionContractView` ref/digest. The
`MEMORY_DISTILLATION` arm instead requires the exact campaign manifest,
Work-Item/profile, namespace, and Distillation/Lifecycle policy identities below;
it has no fabricated scientific Evaluation Contract or Decision Contract View.

It does not expose `cache_path`, current working directory, heartbeat files,
retry counters, or stage-status mutation.

A `MEMORY_DISTILLATION` Run is admitted from an immutable distillation campaign
manifest and may own zero Hypotheses/Experiment Attempts/Decision Intents. Its
v1 manifest contains exactly one Work Item and is a deterministic expansion of
that Work Item's pinned Campaign Admission Profile (workflow/continuation,
model/tool/Adapter configuration, Budget, retention, and cardinality). The public
command remains `DriveRun`; for this kind a shared canonical helper fixes
`admission_key = Work Item ID`, derives `run_id` in the
`ai-researcher/memory-distillation-run/v1` domain and initial `command_id` in its
own versioned domain from that key, and Runtime rejects caller-chosen alternatives.
The Run projection enforces `UNIQUE(run_kind, admission_key)`. Same key/
same spec returns the same Run, while same key/different manifest/profile is an
identity conflict that must reconcile the existing winner and cannot create a
second Run. Multi-item admission requires a
future Ledger-owned atomic membership reservation before Run creation. Its
workflow cannot emit `OpenExperimentAttempt`. Every manifest Work Item has one
deterministic Activity initially created as `AWAITING_ASSIGNMENT`, a non-claimable,
non-dispatchable state. A narrow Runtime getter first supplies a digest-bound
campaign/manifest/Work-Item/Activity proof that authorizes only the Experiment
Ledger Assignment append. After the Ledger appends and read-backs the
exact Assignment, Runtime re-reads a content/digest-bound assignment proof and
uses a Run-version/Activity-generation CAS to bind its ID/digest and move that
Activity to `READY`. A stale proof or concurrent cancel/terminal transition
cannot activate it. The Run completes only after exact manifest membership,
Assignment, terminal Completion, record-closure, and operational-settlement
barriers all pass. A terminal source
`SCIENTIFIC` Run never owns or dispatches those later Activities.

Run/admission/command/Activity/Assignment and manifest temporary/run-owned ref
IDs are all produced by one shared versioned pure helper and golden-vector set;
the implementation plan's canonical ID table is normative. No Store may derive
an alternative ID from deployment defaults, retry/fence, clock, or path.

The Work Item's Campaign Admission Profile bytes are protected before the
Ledger enqueue, not when this campaign Run happens to be projected. The builder
publishes the content-addressed bytes, computes the Work Item ID from its
Experience/policies/profile ref+digest, and freezes its canonical payload. One
Runtime Durable Transition first recomputes that ID/payload digest and semantic
lineage, then
creates a deterministic `ACTIVE` `runtime_artifact_ref` owned by
`DISTILLATION_WORK_ITEM:<work_item_id>` and a `PENDING` handoff. Before proof can
leave Runtime, one writer transaction CASes its enqueue attempt
`NOT_STARTED -> IN_FLIGHT`, assigns attempt ID/generation/fence, and only then lets the
narrow getter return a digest-bound `WorkItemProfileArtifactProof`. A first
queued Ledger insert accepts only that exact current, unfenced `IN_FLIGHT`
attempt triple and persists ref/attempt ID/generation/fence identity. Only after Runtime read-backs the
exact Work Item, aggregate enqueue receipt, and immutable enqueue-transaction
sidecar—and verifies its original proof/transaction digests plus the same
attempt ID/generation/fence—may it CAS the handoff
`IN_FLIGHT/PENDING -> LEDGER_PRESENT/BOUND`; recovery may make the same bind from
`RETIRED/PENDING` after old-fence drain when those exact rows prove that the old
transaction committed. Exact committed replay returns the
original receipt/proof digest even if handoff is now `BOUND`; `NOT_STARTED`,
retired, inactive, released, foreign, or mismatched proofs fail closed for a
new Ledger insert. A retired attempt is never reusable as enqueue authority;
its only commit-winning path is exact read-back of its already-committed sidecar.

Recovery treats the handoff as a saga. A pre-enqueue `PENDING` ref remains a GC
root while Runtime obtains a fixed-frontier Ledger presence/absence proof. An
exact Work Item/receipt completes the bind. For absence, Runtime must first stop
the coordinator, higher-fence retire the attempt, wait for every old-fence
Ledger transaction to finish, and only then read a later Ledger frontier from a
frozen recovery request that binds the Experience, Work Item ID/payload digest,
handoff, and exact attempt ID/generation/fence. Its three proof arms echo the
request ID/digest, lineage, and attempt triple. Exact `QUEUED_PRESENT` plus Work
Item, receipt, and enqueue sidecar
read-back advances the same attempt `RETIRED -> LEDGER_PRESENT` and binds it; this
covers an old transaction that committed while retirement/drain was in progress.
Exact `ABANDONED_PRESENT` recovers an already-committed abandoned receipt and
continues the proof-authorized release; it never binds a Work Item. Only exact
`ABSENT`, which also proves that this Experience has no Distillation Receipt,
permits `RETIRED -> PROVED_ABSENT`. Proof issuance
and absence cannot be asserted in the same race window. `PROVED_ABSENT` closes
only that immutable attempt identity's journal-backed state: the deterministic handoff and its `ACTIVE` ref
remain `PENDING`, and an ordinary retry appends a higher-generation/higher-fence
`IN_FLIGHT` attempt under the same handoff. `ORPHAN_ABSENT` release additionally
requires a durable `DistillationEnqueueObligationAbandonedProof` binding the same
Experience, Work Item ID/frozen payload digest/semantic lineage,
handoff/current `PROVED_ABSENT` attempt ID/generation/fence, that
attempt row's exact later-frontier recovery-proof pair, source Activity,
terminal control cause, and an irreversible no-future-retry disposition. The
memory Store then uses that strict proof to append/read-back the Experience's
typed `abandoned_before_enqueue` Distillation Receipt. Only after Runtime
independently reads that receipt and verifies the same Work
Item/payload-digest/proof pair may
the release CAS revalidate that the same attempt is still current and emit
`ORPHAN_ABSENT/RELEASED`; a later retry invalidates the old proof. A Ledger commit followed by
reply loss is likewise bound from read-back. Source-Run terminal state never
releases this reference. On the `BOUND` branch, release requires terminal Work
Completion plus either an independent campaign replay/audit root for the bytes
or expiry of that retention, and is an explicit `BOUND -> RELEASED` Runtime
event/read-back.

The two Runtime-owned payloads are frozen Pydantic-style records with
`extra=forbid` and canonical JSON golden vectors:

- `DistillationCampaignAdmissionProfileV1`, content domain
  `ai-researcher/distillation-campaign-admission-profile/v1`, contains exact
  workflow/continuation refs+versions+digests, interpreter-contract bundle,
  model/tool/Drafting-Adapter configuration digests, Budget Envelope,
  execution/retention policies, and `cardinality=1`;
- `DistillationCampaignManifestV1`, content domain
  `ai-researcher/distillation-campaign-manifest/v1`, contains run kind,
  namespace/scope, profile ref/digest, policy identities, and exactly one ordered
  member `{ordinal:0, work_item_id, work_item_payload_digest, experience_id}`. It
  excludes run ID, command ID, mutable state, and derived spec digest.

One shared pure implementation and golden vectors define
`profile + canonical Work Item -> manifest -> ResearchRunSpec`; the Work Item ID
separately derives admission key, Run ID, Activity ID, and initial command ID.
Memory code stores only strict profile/manifest refs and cannot reimplement these
payloads or expansion rules.

The profile artifact follows the `PENDING|BOUND|RELEASED` Work-Item handoff saga
above. The campaign manifest has a separate admission handoff: before `DriveRun`,
the projector creates an `ACTIVE` temporary manifest ref owned by the
deterministic initial command/admission attempt; Run admission atomically creates
the Run-owned ref before releasing that temporary ref. GC may collect neither
artifact during its handoff window, and reply-loss recovery reconciles by the
same owners/IDs.

If cancel/failure closure needs to assign an `AWAITING_ASSIGNMENT` slot, the same
proof/append/read-back sequence is used, but a system-control closure-bind CAS
atomically binds Assignment and moves the Activity directly to nonclaimable
`CLOSING`, never `READY`. It grants the matching closure authorization; after the
Ledger `cancelled/dead_letter` Completion is read back, Runtime moves
`CLOSING -> CANCELLED/FAILED`. Existing `READY/WAITING_RETRY` slots enter the same
`CLOSING` path after fence revocation. A terminal campaign requires every
Activity terminal state to match its Completion (`COMMITTED/completed`,
`FAILED/dead_letter`, `CANCELLED/cancelled`); Assignment/Completion alone cannot
leave a terminal Run with an awaiting or ready Activity.

The spec and its digest are immutable. `AmendBudget` appends an effective-budget
overlay; it never rewrites the initial spec, settled usage, open reservations,
or an existing Experiment Attempt allocation. Changing task inputs, workflow,
model/tool configuration, source/dataset identity, or Evaluation Contract means
creating a new Research Run.

Workflow and continuation policy are canonical data artifacts interpreted by a
pinned Runtime contract, not names resolved to “whatever is currently
deployed.” Creation writes or verifies their content-addressed bytes before
accepting the Run. Every non-terminal Run and every retained replay history is a
GC root for those artifacts and the required Adapter-contract bundle. Planning
loads by reference, verifies digest/schema/version, and fails closed as
`WAITING_INPUT` or an incompatible-version failure if bytes or interpreter are
unavailable; it never substitutes the current default. V1 never migrates an
in-flight spec in place. A workflow/policy change creates a new Research Run
with an explicit predecessor provenance link; snapshot import is allowed only
when ordinary content and reuse-governance checks pass.

`inspect()` returns only a consistent, versioned snapshot:

- Research Run status and current workflow/snapshot generation;
- current Hypothesis, Experiment Attempt, and stage;
- completed, ready, leased, and waiting Activities;
- reserved and settled budget usage;
- structured error and next retry time;
- Observation, Verification Record, Experience Record, required Recall Decision
  Outcome, and Experience Distillation Receipt IDs;
- current `last_event_seq` and events after the query cursor.

`CommandReceipt.disposition` is a closed
`ACCEPTED | DUPLICATE | TERMINAL_NOOP | PENDING_AFTER_ARBITRATION |
TOO_LATE_COMMITTED` union and includes command/payload identity,
accepted version, and event sequence. It never contains an Activity result or
implies that background work finished. `RunIdentityConflict`,
`CommandIdentityConflict`, `VersionConflict`, `InvalidTransition`,
`CommitArbitrationBusy`, `ContractViolation`, `RunNotFound`, `AdmissionClosed`, `IncidentFenced`,
`CursorAhead`, `InvalidQuery`, and `RuntimeUnavailable` are the closed v1 typed
Interface error union. `AdmissionClosed` applies when a `DriveRun` would bind a
new Research Run while its admission scope is closed. `IncidentFenced` applies
to a previously unseen non-cancel mutation for an existing Research Run covered
by an active incident; unaffected existing Runs may still be driven. `inspect`
remains available, and a previously unseen `CancelRun` is the fail-safe exception
that may still revoke work. Worker claim/commit incident
rejections are private control-protocol outcomes, not additional public errors.
Each pending control is resolved by one append-only `PendingControlResolved`
record. Its kind is
`COMMAND_CANCEL|SYSTEM_FAILURE`: the first binds original command/payload IDs,
the second binds deterministic authenticated system-failure event/ref/digest;
both bind Run ID, target authorization ID/digest, resolution event
sequence, and closed outcome `TOO_LATE_COMMITTED | CANCELLATION_APPLIED |
FAILURE_APPLIED | CLOSURE_ASSIST_NOOP`. `inspect` exposes these records and accepts
an optional command-ID filter for the command subset. Exact `apply` replay remains the deterministic
`DUPLICATE` of the original receipt; clients join the final resolution through
`inspect`, so time cannot change receipt bytes. One authorization has exactly one
`PRIMARY` arbitration owner, selected by Run/control-event CAS, but may have
audited `FOLLOWER` controls. For example, failure-first makes a later public
Cancel a follower whose own command resolution is `CLOSURE_ASSIST_NOOP`; it does
not steal primary ownership. Thus every public pending receipt remains joinable
without inventing a second primary cause.
`RuntimeUnavailable` applies to both `apply` and `inspect` when no
authenticated control handshake/response is obtained; it never implies command
acceptance. `CancelRun`
is monotonic and may revoke a non-terminal run even when the caller's observed
version is stale; all other mutations use `expected_version`.

`inspect()` reads `projection_version = v` and `last_event_seq = m` in one SQLite
read transaction; the projection records `applied_through_event_seq = m`, and
pagination returns only events with `cursor < event_seq ≤ m`, plus
`next_cursor`/`has_more`. Run version `v` and event sequence `m` are distinct and
need not increment together because one transition may append multiple events.
V1 never prunes the authoritative event journal. A cursor ahead of `m` or
invalid limit is a typed query error rather than an empty success.

### 6.2 Stage Continuation Module

```python
class StageContinuation(Protocol):
    def plan(self, request: ContinuationRequest) -> ContinuationPlan:
        """Return the deterministic next action from committed state only."""
```

The request contains the digest-verified bytes resolved from the pinned
workflow-definition and continuation-policy artifact references, their
versions/digests, the durable snapshot, and trigger reason. The
plan contains exactly one next action,
the input and scope digests it depends on, budget requirement, checkpoint
policy, and a stable `plan_digest`.

The v1 action union is:

```python
ContinuationAction = (
    OpenExperimentAttempt
    | ReuseStage
    | DispatchStage
    | VerifyObservation
    | RecordExperience
    | Wait
    | Terminal
)
```

`OpenExperimentAttempt` carries a complete immutable `AttemptSpec`: Attempt ID;
Research Run/spec digest; exact Research Context Snapshot generation,
reference, and digest; source/dataset identity digests; an existing Hypothesis
reference or complete new Hypothesis payload; the validated Intervention; seed;
Attempt allocation; Evaluation Contract reference/digest; content-addressed
decision-input/Recall Context artifact reference/digest with citations;
execution environment/code/container/model/tool configuration digests; and
Intervention Catalog version/digest. If a field is inherited from a content-
addressed Run or Snapshot artifact, the AttemptSpec still binds that artifact
and field digest explicitly. If the catalog is wholly embedded in the pinned
workflow, its digest is still copied into the AttemptSpec. For a new Hypothesis,
the Hypothesis and first Attempt commit atomically, preserving the one-or-more
Attempts cardinality. Superseding a snapshot generation never mutates an
existing Attempt; a later Attempt binds the new generation explicitly.

It performs no filesystem, database, model, network, or clock access. Given the
same canonical `ContinuationRequest`, including the pinned workflow and policy
digests, it returns byte-identical canonical output. This determinism makes the
entire continuation policy testable without starting a real research flow.

Time enters through committed input, not a hidden clock read. The Runtime emits
`TimerFired`, `DeadlineReached`, or `BudgetExpired` events from its clock before
planning. Backoff jitter is derived from stable effect identity and policy
version. Thus an unchanged `ContinuationRequest` never changes merely because
wall time passed; a new timer event creates a new committed request.

Each wait creates a durable timer identity from
`run_id / activity_id / activity_generation / progress_cursor / timer_kind /
policy_version / due_at`. Activity start atomically schedules its initial
progress-deadline timer with `ActivityStarted`; every committed semantic progress
update atomically cancels the prior timer and schedules a replacement bound to
the new cursor/deadline. There is no state in which committed RUNNING work lacks
the timer required by its pinned stall policy. A unique timer
row stores `SCHEDULED | CLAIMED | FIRED | CANCELLED` plus claim epoch/expiry.
Workers scan due timers
using store time and atomically claim them; a uniqueness constraint makes the
corresponding event logically once when several workers wake together. The
launcher-supervised control/executor service is what wakes a Run for a due timer.
An expired claim is reclaimable after worker death; a fired timer never fires
again after restart. Pause, cancellation, terminal transition, or a progress/
workflow transition that supersedes a timer durably cancels every no-longer-
applicable timer in the same transition that changes the Run state.

### 6.3 Thin caller Adapter

CLI and web code may use convenience functions such as `run_to_terminal()` and
`follow_events()`, but these are thin Adapters over `apply()` and `inspect()`.
`run_to_terminal()` submits once, verifies the configured Runtime service with
the authenticated generation-matching handshake, and follows snapshots; it
does not start or reach into `launcher.py`/`worker.py`, nor execute stage
ordering in the caller. These helpers do not become a second lifecycle
Interface.

The public runtime package must not expose store transactions, lease mutation,
heartbeat writes, checkpoint mutation, or `complete_stage/progress/finalize`
callbacks.

## 7. Durable state machine

### 7.1 Research Run state

| From | To | Cause |
| --- | --- | --- |
| `NEW` | `RUNNING` | accepted `DriveRun` |
| `RUNNING` | `WAITING_RETRY` | retryable failure with future eligibility |
| `WAITING_RETRY` | `RUNNING` | retry becomes eligible and a worker claims it |
| active state without unresolved commit arbitration | `PAUSING` | accepted `PauseRun`; revoke worker fence |
| any Run with unresolved Intent/Recall/Distillation commit authorization | unchanged | `PauseRun -> CommitArbitrationBusy`; no pause intent, state change, or fence revocation |
| `PAUSING` | `PAUSED` / `WAITING_INPUT` | checkpoint/terminate and reconcile in-flight effect |
| `PAUSED` | `RUNNING` | accepted `ResumeRun` |
| `RUNNING` | `WAITING_INPUT` | ambiguous effect or required operator decision |
| any non-terminal state without unresolved commit arbitration | `WAITING_INPUT` | active integrity incident; private `RunQuarantined` transition revokes fence |
| any Run with unresolved commit arbitration | unchanged arbitration lifecycle | incident closes new work and records a pending authenticated failure, but does not revoke the grandfathered authorization; quarantine/failure transition follows success or proved no-commit |
| `WAITING_INPUT` | `RUNNING` / `PAUSED` / `FAILING` / `CANCELLING` | accepted typed `ResolveRun` consistent with persisted wait/control intent |
| `RUNNING` | `RUNNING` | stage advances through execute, verify, and record |
| `RUNNING` | `COMPLETED` | valid evidence chain and terminal policy decision committed |
| memory campaign with exact manifest already all `completed`, before terminal barriers | unchanged terminalizing lifecycle / `COMPLETED` or `FAILED` | `CancelRun -> TOO_LATE_COMMITTED`; never enter `CANCELLING`; an already-latched independent failure still maps to `RUNTIME_FAILURE_AFTER_WORK` |
| any non-terminal state without an unresolved kind-specific commit attempt | `CANCELLING` | accepted `CancelRun`; revoke worker fence |
| any non-terminal Run with unresolved Intent admission or `DecisionRecallCommitAuthorization` | unchanged Run lifecycle; Intent remains `REGISTERING`/`*_COMMITTING` | `CancelRun -> PENDING_AFTER_ARBITRATION`; persist one pending control kind without revoking the append attempt |
| pending cancel/failure + Intent admission success | `CANCELLING` / `FAILING` | advance to `OPEN`, then grant the unique closure Outcome for the real Intent |
| pending cancel/failure + Intent admission no-commit | `CANCELLING` / `FAILING` | retire registration; no Outcome is fabricated for the absent Intent |
| pending cancel + Context success/no-commit | `CANCELLING` | reconcile Context phase, then grant closure Outcome from `CONTEXT_COMMITTED`/`OPEN` |
| pending failure + Context success/no-commit | `FAILING` | reconcile Context phase, then grant actor-failure closure Outcome from `CONTEXT_COMMITTED`/`OPEN` |
| pending cancel/failure + Outcome success | `CANCELLING` / `FAILING` | preserve immutable Outcome; continue Run record closure without replacement |
| pending cancel/failure + Outcome no-commit | `CANCELLING` / `FAILING` | retire normal authorization and grant the mutually exclusive closure Outcome |
| singleton memory campaign with Activity=`COMMITTING` and unresolved `DistillationCommitAuthorization` | unchanged Run lifecycle; Activity remains `COMMITTING` | `CancelRun -> PENDING_AFTER_ARBITRATION`; persist cancel intent without revoking attempt |
| Activity=`COMMITTING` with pending cancel + atomic Ledger success | Run `RUNNING` / `COMPLETED`; Activity `COMMITTED` | resolve cancel as `TOO_LATE_COMMITTED`; reconcile committed work |
| Activity=`COMMITTING` with pending cancel + proven `NO_COMMIT_CONFLICT` | Run `CANCELLING`; Activity closure path | retire authorization, advance fence/generation, apply pending cancel before retry |
| Activity=`COMMITTING` with pending failure + atomic Ledger success | Run `FAILING`; Activity `COMMITTED` | preserve completed Work Completion; close as `RUNTIME_FAILURE_AFTER_WORK` if failure remains |
| Activity=`COMMITTING` with pending failure + proven `NO_COMMIT_CONFLICT` | Run `FAILING`; Activity closure path | retire authorization, advance fence/generation, dead-letter before retry |
| `CANCELLING` | `CANCELLED` | record-closure and operational-settlement barriers pass |
| `CANCELLING` | `WAITING_INPUT` | non-queryable remote effect remains unresolved |
| any active state without unresolved commit arbitration | `FAILING` | permanent Runtime, contract, or integrity failure; revoke worker fence |
| `FAILING` | `FAILED` | record-closure and operational-settlement barriers pass |
| `FAILING` | `WAITING_INPUT` | required record closure or external reconciliation is unresolved |

A typed resolution preserves the wait's cause. In particular, abandoning a
`NON_RECONCILABLE` remote effect whose outcome may still exist can only produce
`FAILED` with `remote_outcome=UNKNOWN_ABANDONED`; it cannot produce
`CANCELLED`, `COMPLETED`, or a scientific outcome. A side-effect-free
`REEXECUTABLE` invocation may be abandoned only when its Adapter contract and
current fence prove that its late bytes cannot be selected or commit.

Pause is a preemptive operation at the latest durable semantic safe point, not
an instantaneous snapshot of process memory. If no Intent admission,
Decision-Recall append, or Distillation commit authorization is unresolved,
acceptance immediately revokes the old fence. A new control owner may ask a
backend with native support to emit and validate a checkpoint; otherwise it
terminates/reconciles the in-flight Activity and resumes later from the last
already committed checkpoint. The old worker is never allowed to commit a new
checkpoint after revocation. If the effect cannot be reconciled, the Run enters
`WAITING_INPUT`. A late receipt is journaled for reconciliation but cannot
commit the old fenced transition. While an authorization is unresolved,
`PauseRun` returns typed `CommitArbitrationBusy` and makes no state, pending-
control, or fence change; the caller retries after the same authorization has
resolved. Pause therefore cannot silently revoke the only proof that permits a
cross-store commit to converge.

`STALLED` is an observation with evidence and timestamp, not a terminal state.
A worker can be alive while an Activity makes no progress, or a worker can be
dead after having committed useful progress; those conditions must not share a
single heartbeat.

Every Activity contract pins `max_progress_silence` and checkpoint policy. A
durable progress-deadline timer lets an independent watchdog detect a stall even
while a background thread renews the worker lease. On expiry the watchdog
does not acquire the Run Lease. It first claims the timer, then one private
authenticated system-control transaction rechecks store time, timer identity
and claim epoch/expiry, Activity generation, unchanged progress cursor/deadline,
and expected event sequence. Only then may it commit
`ActivityStallDetected`/`TimerFired`, revoke the current worker fence, and assign
a new control epoch. A concurrent semantic-progress commit wins by transaction
order and invalidates/cancels the stale timer claim; it cannot be falsely
preempted. The new control owner isolates/terminates owned work, then moves the
same Activity to `WAITING_RETRY` or `WAITING_INPUT` according to its
checkpoint/effect policy. Potentially long Activities must use a subprocess or
container; in-process Activities must be short, have an enforced timeout, and
support cooperative cancellation. Entering any unresolved append/commit
authorization phase—Decision Intent `REGISTERING`, Decision Recall
`CONTEXT_COMMITTING|OUTCOME_COMMITTING`, or Distillation `COMMITTING`—atomically
cancels its ordinary progress timer and installs a distinct bounded
`COMMIT_RECONCILIATION_DEADLINE` bound to the authorization ID/digest. Expiry of
that deadline always records a typed `CommitReconciliationOverdue` review intent
and closes new-work admission; where warranted it also appends pending
authenticated failure evidence. It never
revokes or retires the authorization and never advances its fence. The
coordinator must first obtain Ledger success or a typed no-commit proof, then
the same Runtime reconcile transaction cancels the bound deadline and applies
pause/cancel/failure/quarantine. If only the overdue review remains, resolution
enters `WAITING_INPUT(reason=COMMIT_RECONCILIATION_OVERDUE)` so `ResolveRun` can
explicitly resume/fail; the new-work gate is never silently left closed. Timer
fire itself CASes only while the exact authorization ID/digest is still current
and status=`GRANTED`; a late claim after success/no-commit is a no-op. Thus a watchdog or integrity incident
cannot create a second writer while the first cross-store outcome is unknown.

Lifecycle status and workflow phase are separate fields. `current_stage` may be
`verify` or `record` while lifecycle remains `RUNNING`. Terminal outcome is
kind-discriminated. A completed `SCIENTIFIC` projection requires
`scientific_outcome = VALID_PASS | VALID_FAIL | EXHAUSTED_NO_PASS` and forbids a
campaign outcome. A `MEMORY_DISTILLATION` Run forbids `scientific_outcome` and
uses disjoint ordered predicates. First, `dead_letter_count>0` maps to
`FAILED/DEAD_LETTER_PRESENT` (a later independent failure remains secondary
evidence). Otherwise, all slots `completed` map to `COMPLETED/ALL_COMPLETED`,
unless an independently authenticated non-work failure wins before terminal CAS,
which yields `FAILED/RUNTIME_FAILURE_AFTER_WORK`. Otherwise,
`cancelled_count>0` maps to `CANCELLED/CANCELLED`, unless that failure wins before
terminal CAS, which yields `FAILED/RUNTIME_FAILURE_AFTER_CLOSURE`.
Failure authorization and CancelRun contend on the same Run-version/control-
event CAS: failure-first latches `FAILING`; cancel-first latches `CANCELLING`
and suppresses only duplicate or cancellation-induced closure failure. An
independently authenticated integrity, contract, or infrastructure failure may
still upgrade the Run before its terminal CAS without mutating any settled Work
Completion. If all slots were already completed but a
later non-work Runtime/contract/integrity failure is permanently unrecoverable,
the settled Run maps to `FAILED` with a typed Run failure receipt and
`distillation_outcome=RUNTIME_FAILURE_AFTER_WORK`; it does not rewrite a Work
Completion as dead letter. If the exact manifest has zero dead letters and at
least one cancelled slot when that
independent failure wins, the immutable coverage maps to
`FAILED/RUNTIME_FAILURE_AFTER_CLOSURE`; it is never rewritten into dead letters.
`FAILED/CANCELLED` scientific Runs have no
scientific outcome. Terminal lifecycle state is immutable.

That receipt is a distinct immutable `RunTerminalFailureReceipt`, not a Work
Completion terminal receipt. It binds Run/spec/manifest, the exact settled-
manifest coverage digest (ordered slot/status/Completion digest; all-completed is
one special case), failure control event, a closed control-plane/contract/artifact/
infrastructure cause, source evidence, and its canonical digest. It is required
iff `FAILED/RUNTIME_FAILURE_AFTER_WORK|RUNTIME_FAILURE_AFTER_CLOSURE`, exposed by
a narrow Runtime getter and the Run snapshot, and forbidden for every other
terminal mapping. Missing,
foreign, or tampered receipt blocks terminalization.

### 7.2 Runtime Activity state

One Runtime Activity is one semantic stage and may own zero or more effects and
zero or more append-only checkpoints. Its normal path is
`READY → LEASED → RUNNING → COMMITTING → COMMITTED`. A campaign Activity alone
may start `AWAITING_ASSIGNMENT`; this state cannot be claimed, leased, or prepare
an Effect, and only the exact assignment-proof CAS described above can move it
to `READY`. `EffectPrepared`,
`EffectReceipt`, and semantic checkpoints have their own records; they are not
competing Activity terminal states. A retryable failure moves the same Activity
to `WAITING_RETRY`; an ambiguous effect moves it to `WAITING_INPUT`; permanent
failure and cancellation use `FAILED` and `CANCELLED`.
Campaign closure additionally uses nonclaimable `CLOSING` between the
system-control assignment/fence CAS and read-back of its terminal Work
Completion; it cannot prepare or dispatch Effects.

A successfully paused in-flight Activity atomically records
`PAUSED_AT_CHECKPOINT` with either a validated resume-token reference or an
explicit restart-from-last-committed-boundary disposition when the Research Run
enters `PAUSED`. `ResumeRun` moves that same Activity identity/generation back to
`READY`, preserving logical effect identities; it does not create a new
Experiment Attempt. If pause cleanup finished but the state transaction crashed,
recovery reconciles ownership/checkpoint evidence before committing this state.
An unresolved effect remains `WAITING_INPUT`, never pseudo-paused.

Cancellation is durable intent. `CANCELLED` is recorded only after the Adapter
confirms termination or reconciliation proves the external work cannot commit.
Operator acknowledgement of an unknown non-reconcilable remote outcome is
instead the typed `FAILED/UNKNOWN_ABANDONED` resolution above.

#### Fenced Decision Recall append authorization

Before an Intent exists in the Ledger, Runtime reads back a complete
`DecisionIntentProposal` artifact and CAS-creates `REGISTERING` plus an admission
authorization; its Store-facing strict proof is `DecisionIntentAdmissionProof`.
Ledger success advances to `OPEN`; a journaled no-commit retires the registration.
An unresolved registration is reconciled like every later append and blocks
retrieval/actor work. Cancel/failure during it is pending: success creates a real
Intent that must be closed, while no-commit leaves no record to fabricate.

The authorization model is the closed tagged union
`DecisionRecallAppendAuthorization = DecisionIntentAdmissionAuthorization |
DecisionRecallCommitAuthorization`. The admission subtype is exclusively
`APPEND_INTENT/ADMISSION` and its getter returns only
`DecisionIntentAdmissionProof`. The commit subtype is exclusively
`APPEND_CONTEXT/NORMAL` or `APPEND_OUTCOME/NORMAL|RUNTIME_CLOSURE`, and its getter
returns only `DecisionRecallCommitAuthorizationProof`; either getter rejects the
other subtype.

Runtime then owns one durable per-Intent phase projection:
`OPEN -> CONTEXT_COMMITTING -> CONTEXT_COMMITTED -> OUTCOME_COMMITTING ->
OUTCOME_COMMITTED`. A registered-not-requested or typed blocked path may enter
`OUTCOME_COMMITTING` directly from `OPEN`. The blocked path is legal only after
Runtime has read back an immutable `DecisionRecallBlockedProposal` and resolved
its strict `DecisionRecallBlockedProof`; a caller-provided reason code is not a
source fact. Runtime control is the only writer of
this projection and the only issuer of a single-use
`DecisionRecallCommitAuthorization`; the memory Store remains owner of immutable
Intent/Context/Outcome payloads.

Issuance of either tagged subtype uses one Run-version/control-event/
Activity-generation/fence CAS. The union pins transition kind
`APPEND_INTENT | APPEND_CONTEXT | APPEND_OUTCOME`, authority `ADMISSION | NORMAL |
RUNTIME_CLOSURE`, exact Intent and
optional preceding Context, and expected Ledger record ID/payload digest. A
Context grant and every normal or Runtime-closure Outcome grant also pin the
read-back proposal artifact ref/digest;
a blocked Outcome grant additionally pins the exact blocked-source proof
ref/digest carried by that Outcome proposal, while its generic terminal-evidence
receipt remains null;
a narrow public Runtime getter returns a digest-bound proof. After the memory Store
transaction, Runtime reads back the exact Ledger receipt and either advances the
phase or retires the authorization on a proved no-commit result. Reply loss and
restart reconcile the same authorization and expected content IDs; an unresolved
authorization forbids a second grant.

The transition/authority cross-product is closed:
`APPEND_INTENT <-> ADMISSION`, `APPEND_CONTEXT <-> NORMAL`, and
`APPEND_OUTCOME <-> NORMAL | RUNTIME_CLOSURE`. Both Runtime issuer and Store proof
validator enforce it; there is no closure Context or admission Outcome path.

Expected Intent/Context/Outcome record IDs and payload digests exclude authorization
linkage. The Store writes authorization ID/digest only as immutable append
metadata after grant; it never feeds that metadata back into the proposal or
record hash. This fixed acyclic order is part of the Runtime/Store contract.

Cancel/fatal-failure that wins before grant revokes the normal fence and may
mint only a mutually exclusive closure-Outcome authorization. If grant wins
first, the control request becomes `PENDING_AFTER_ARBITRATION` without revoking
that exact attempt. Context success advances to `CONTEXT_COMMITTED`, after which
the pending cause authorizes the unique closure Outcome; Context no-commit lets
the pending closure act from `OPEN`. Outcome success makes that immutable Outcome
win and the pending control proceeds without replacing it; Outcome no-commit
lets the pending closure win. Pending cancel/failure kind is itself selected by
one control-event CAS with the same precedence as Run closure. The Ledger never
accepts a boolean “current fence” supplied by an actor; it validates the exact
authorization proof, and Runtime never infers no write from an absent reply.

#### Fenced memory-distillation commit authorization

A `MEMORY_DISTILLATION` executor never writes the Experiment Ledger. It returns
one content-addressed proposal artifact. An independent Coordinator deterministically
prepares and publishes an immutable `DistillationCommitPlan` containing the exact
canonical output bytes/IDs/digests. Runtime control read-backs both artifacts, then
atomically CASes the current Run version,
Activity generation, and fence from `RUNNING` to `COMMITTING` while appending a
unique `DistillationCommitAuthorization`. The authorization binds the exact
Assignment, logical Effect, proposal and commit-plan refs/digests, and expected
Batch/Report IDs and digests; same authorization ID with different payload is an integrity
conflict. A narrow public Runtime getter returns a digest-bound proof.

`GRANTED` starts an exclusive pending attempt; the Coordinator derives the
successful Completion from the authorization digest and submits exact
plan+Completion+authorization. Only atomic Ledger success is the
irreversible logical commit point. The proposal pins every affected expected
lifecycle head. The memory Store either atomically appends Batch, Knowledge/
lifecycle records, Work Disposition, Report, and successful Work Completion,
or—before any semantic write—journals a `NO_COMMIT_CONFLICT` whose closed kind is
`LIFECYCLE_HEAD_STALE` (expected/observed heads) or `RETENTION_REVOKED` (current
retention frontier/set plus sorted reachable blocked targets). Runtime read-backs
the Store-selected kind; when both predicates hold, `RETENTION_REVOKED` has
mandatory precedence and the head-delta arm is canonical null. In the head-stale
arm every retention field is canonical null. Runtime read-backs the conflict
proof, CASes authorization to `RETIRED_NO_COMMIT`, and increments
generation/fence. Head-stale re-proposes from the current head; retention-revoked
first obtains clean inputs or follows pinned typed closure policy. Neither may
reuse the old plan, and a retired authorization can never later write a Batch.

CancelRun during unresolved `GRANTED` appends a durable
`PENDING_AFTER_ARBITRATION` intent without revoking the attempt. Success resolves
that intent `TOO_LATE_COMMITTED`; a no-commit result retires authorization and
applies the pending cancellation in the same CAS before any retry grant. If
fatal failure arrives first during `GRANTED`, success preserves the completed Work
Item then enters `FAILING/RUNTIME_FAILURE_AFTER_WORK`, while no-commit retires and
dead-letters before retry. One Run-version/control-event CAS chooses the pending
kind: cancel-first suppresses only cancellation-induced/duplicate failure;
failure-first makes later Cancel closure-help/no-op. Independent integrity/
contract/infrastructure failure remains durable secondary evidence and, after
success, can require `RUNTIME_FAILURE_AFTER_WORK`; after no-commit it forces
failure/dead-letter before retry. If cancel/failure wins before grant, no authorization can be minted and late worker
bytes have no write authority. Crash after grant or Ledger commit resumes by the
same IDs; unresolved proof keeps the Activity `COMMITTING` while the Run stays in
its prior non-terminal lifecycle (or moves the Run to `WAITING_INPUT` on integrity
ambiguity), never closes by guessing.

Pre-authorization exhausted failure or cancellation uses a mutually exclusive
`DistillationClosureAuthorization` plus a Runtime-owned terminal receipt
ref/digest. The closure CAS proves no commit authorization exists for that
Activity generation. The memory Store accepts that proof only for
`dead_letter/cancelled`; it can never use the closure path for `completed`.

### 7.3 Completion ordering

The required final order is:

```text
execution receipt
  → Trial Provenance + Observation committed atomically
  → Verification Record committed against both and the canonical AttemptSpec
  → Experience Record committed
  → every Run-owned Decision Intent has its Recall Decision Outcome
  → every completion-required Experience has its Experience Distillation Receipt
  → operational settlement barrier passed
  → Research Run COMPLETED
```

Verification cannot begin from an unprovenanced Observation. A crash anywhere
between execution receipt and the atomic Trial-Provenance/Observation commit
reconciles the receipt and recreates that pair; it never verifies a partial
record. The execution receipt, Trial Provenance, and Observation must all bind
the same canonical `AttemptSpec` digest. Before producing a valid Verification
Record, the verifier compares every pinned AttemptSpec field—including Run and
snapshot identity, Hypothesis, Intervention, seed, allocation, Evaluation
Contract, decision-input/Recall citations, source/dataset, environment, code,
container, model/tool configuration, and Intervention Catalog—against the
materialized execution and Trial Provenance. A provenance-valid result produced
under a different AttemptSpec is contract-invalid, not scientific evidence.

The settlement barrier is a separate terminal-state guard shared by
`COMPLETED`, `FAILED`, and `CANCELLED`. It requires every physical invocation to
have a final known/not-executed disposition or an explicit audited
worst-case-settled abandonment, every reservation to be settled, and every
Run-owned task/thread, process group, or container to be absent or reconciled,
every Run-scoped lease/role assignment to be released, and every Run-owned
artifact staging/materialization claim and Snapshot Build Claim to be in a
non-active published/released/revoked/reconciled state. Every Run-owned
artifact-filesystem mutation actor must also have exited or been reconciled.
Shared service roles are explicitly outside this per-Run barrier. An unresolved
remote call
therefore keeps the Research Run in `WAITING_INPUT`; finishing the scientific
record cannot bypass it.

A record-closure barrier precedes that operational barrier for every terminal
state. It scans the immutable set of preallocated Decision Intents and existing
completion-required Experience Records, appends/reconciles only their missing
terminal Outcome/Receipt suffix, and verifies exact cardinality/read-back
digests. `FAILING` and `CANCELLING` remain non-terminal until it passes. This
does not create a missing Experiment Attempt, Verification, Experience, or
Decision Intent merely to make a failed Run look complete.
For each queued Experience Distillation Receipt, the same barrier also verifies
the deterministic Work Item's stored artifact-ref ID against a Runtime
`WorkItemProfileArtifactProof` with handoff=`BOUND` and ref=`ACTIVE`. Only then
may source-owned staging/profile refs settle; the Work-Item-owned ref remains a
separate GC root beyond source-Run terminal state.

Every terminal path, including ordinary success with no pending cancel/failure,
uses a two-step private terminal barrier. `BeginTerminalBarrier` atomically sets
`new_work_admission_closed=true`, allocates a monotonically increasing
`terminal_barrier_epoch`, and appends `TerminalBarrierClosing` with the candidate
terminal kind, control-event sequence, Run version, and Activity fences. A
pending cancel/failure may perform this begin step in its own transaction. While
`CLOSING`, only exact pre-existing append-attempt reconciliation and
epoch/manifest-bound Runtime closure writes are legal; for example, campaign
failure/cancellation may still create its missing system Assignment and terminal
Completion. Claims, actor/model/tool preparation, Intent admission, normal
Context/Outcome authorization, normal assignment, and other new semantic work
must affect zero rows.

After all required closure records read back and every relevant authorization is
resolved, `FreezeTerminalBarrier` CASes the same epoch to `FROZEN` and appends
`TerminalBarrierFrozen`, binding the final closure-projection digest and current
fences. From that point even closure Assignment/Completion creation is forbidden;
only read-back, receipt capture, and operational settlement remain. Barrier-read
proofs are issued only in `FROZEN`. A changed terminal cause, control event,
fence, or closure projection starts a higher epoch and invalidates every earlier
proof. The terminal CAS rechecks and records the same frozen identity plus every
coverage frontier/digest. This gives normal completion the same closed,
race-free proof path as failure and cancellation without blocking required
system closure.

The barrier closes a Decision Intent only through the per-Intent authorization
protocol. It first reconciles any `REGISTERING/CONTEXT_COMMITTING/
OUTCOME_COMMITTING` attempt; admission success becomes a real `OPEN` Intent in the
closure denominator, while typed admission no-commit retires with no Outcome.
Only exact Ledger-backed `OPEN` or later Intents are counted. A Ledger Intent
without matching Runtime admission reconciliation is an integrity
`WAITING_INPUT`, not an omission.
Runtime obtains that set through a Store `DecisionIntentCoverageProof` built at
one fixed Ledger frontier under a Runtime barrier proof that embeds the exact
`TerminalBarrierFrozen` identity, then compares it in both directions with phase
projection and binds its digest into terminal CAS; Runtime
phase enumeration alone cannot detect an orphan Ledger Intent.
The barrier never races a normal actor with an unguarded closure append. For an absent
Context it emits the exact required-memory pre-recall closure status or the
registered not-requested status; for an existing Context it retains that source
status and Runtime-authors one closure disposition per card. A stale normal
Outcome authorization cannot append after closure wins, and a late Context
authorization cannot append after any Outcome.

For a `MEMORY_DISTILLATION` Run, that barrier also scans every immutable manifest
slot, not only existing assignments. `CANCELLING` must append/read-back the exact
Assignment when missing and one `cancelled` Work Completion with a typed
cancellation receipt for every slot with neither terminal Completion nor commit
authorization. `FAILING` must similarly close every unauthorized non-completed
slot as `dead_letter` with a typed terminal failure receipt. An authorized
Activity=`COMMITTING` slot is reconciled, never overwritten by a closure. Assignment
remains unique and is never silently released/requeued.
Until exact manifest coverage and kind-specific outcome mapping pass, the Run
remains non-terminal; this prevents assigned-incomplete work from being trapped
behind a terminal campaign.

Exact manifest coverage comes from an all-status
`DistillationCampaignCoverageProof` built in one Ledger read transaction after
the terminal barrier is frozen and all relevant authorizations reconcile. It
enumerates every Assignment/Completion referencing
the campaign Run, including completed and foreign rows, and is compared with the
manifest plus Activity states before terminal CAS. An incomplete-only scan is not
a proof of absence.

If the process dies after any step, replay schedules only the missing suffix.
A persisted Verification Record is never recreated merely because the terminal
projection was not updated. `VerificationRecord.passed` remains the scientific
outcome and does not change operational completion semantics.

## 8. Durable execution algorithm

After an accepted drive intent, one bounded control-role coordinator quantum,
plus an executor only when external work is claimed, performs the following
operations:

1. load the accepted, canonical Research Run spec and ready-work projection;
2. transactionally acquire or renew a Run Lease and increment its fencing token
   on acquisition;
3. replay new events, validate the projection, and reconcile referenced
   artifacts and unfinished effects;
4. call `StageContinuation.plan()` with committed state;
5. in the control role, atomically claim the Runtime Activity, create the
   physical invocation, reserve its budget, bind request/effect/worker epoch,
   and mark that invocation dispatchable;
6. have the executor request and receive the guarded `DISPATCHED` authorization,
   then execute outside the store transaction while lease liveness and Activity
   progress are recorded separately through the control role;
7. validate and content-address outputs outside the write transaction;
8. have the control role commit the proposed invocation receipt, ambiguity, or
   confirmed-not-executed outcome;
   settle only final known/non-executed results while ambiguity retains its
   reservation; then commit logical-effect selection, artifact references, stage
   events, and the new projection in transactions guarded by expected sequence,
   current owner, current unexpired fencing epoch, and invocation identity;
9. commit quantum completion; control may issue another executor claim for a
   ready Activity.

`apply(DriveRun)` performs spec canonicalization, identity binding, and ready
state creation before this coordinator path. Operator control commands use their
separate command-CAS rule and can revoke the worker fence; they never need to
wait for this quantum to release its lease.

An initial lease renewal interval of 10 seconds and TTL of 45 seconds is a
tuning default, not an invariant. Within one OS boot, lease expiry and timer due
checks use the host monotonic clock plus a persisted boot identity, never
adjustable wall time. On boot-identity change every old lease is expired; timers
carry both monotonic and UTC due metadata and are reconciled at startup only
after a clock-sanity check. If UTC uncertainty exceeds the deployment's frozen
bound, recovery fails closed as `ClockUncertain/WAITING_INPUT` instead of
guessing. The G3 RTO claim is scoped to same-boot process faults with a live
monotonic clock; reboot recovery is a separate safety/replay gate. The fencing
token provides safety if timing is wrong. Production values must be based on
observed scheduler and I/O delay.

## 9. Effect, artifact, and checkpoint semantics

### 9.1 Stable effect identity

```text
run_id / scope_id / stage_generation / effect_name / effect_index
```

This is the stable logical effect ID; the retry number is intentionally excluded.
Its record also binds canonical request digest, Adapter identity/version, and
operation identity. Reusing the same logical key with a different request or
Adapter contract is a conflict.

Logical-effect state is `PREPARED → RESOLVING → RECEIPT_SELECTED |
WAITING_INPUT`. Every physical call under it has a distinct `invocation_id` and
an independent durable state:

```text
CREATED_RESERVED → DISPATCHABLE → DISPATCHED
  → RECEIPT_KNOWN | CONFIRMED_NOT_EXECUTED | AMBIGUOUS
AMBIGUOUS → RECONCILED_RECEIPT_KNOWN | RECONCILED_NOT_EXECUTED | UNRESOLVED
UNRESOLVED → RECONCILED_RECEIPT_KNOWN | RECONCILED_NOT_EXECUTED
           | ABANDONED_WORST_CASE
```

Before any external dispatch, one transaction creates the invocation, reserves
its worst-case budget, binds the logical effect, canonical request digest,
Adapter/version, operation identity, worker owner and fencing epoch, and marks
it `DISPATCHABLE`. The Adapter may be called only after this commit. A separate
guarded transition records `DISPATCHED` immediately before crossing the external
call boundary; from that commit until a receipt/reconcile result, a crash is
treated as ambiguous even if the provider may not actually have received the
request. `DISPATCHED` is an irrevocable authorization: a concurrent fence may
win after that commit but before the physical boundary, so cancellation must
kill/query/reconcile and retain its reservation. The enforceable invariant is
zero new `DISPATCHED` authorization commits after fence revocation, not zero
provider packets after revocation. An invocation left only `DISPATCHABLE` is
proven not dispatched. After return or reconciliation, another guarded
transition records its immutable receipt, ambiguity, or proof of non-execution.
Known receipt/non-execution settles that invocation; `AMBIGUOUS` commits the
disposition while leaving the worst-case reservation open. Later reconciliation
appends a final record and advances the projection without overwriting the
original ambiguous evidence. `UNRESOLVED` remains `WAITING_INPUT`; explicit
operator abandonment appends an audited reason/evidence record, charges the
reserved worst case rather than releasing it, proves that no owned local work
remains, and advances to final `ABANDONED_WORST_CASE`. It does not assert that a
remote side effect did not occur. Its typed abandonment class is either
`REEXECUTABLE_NO_COMMIT` (the fenced result cannot affect the Run) or
`REMOTE_OUTCOME_UNKNOWN` (a non-reconcilable effect may still exist). Only the
known/not-executed reconciliation states and a typed
`ABANDONED_WORST_CASE` are final for accounting; `REMOTE_OUTCOME_UNKNOWN`
restricts the containing Run to `FAILED` and no scientific outcome.
This lifecycle is
not overwritten when a second or third invocation is needed, so replay can
prove how many physical calls were allowed, dispatched, and charged. A logical
effect selects at most one valid receipt for downstream commit:

- if the target supports idempotency, retry with the same key;
- if it supports querying, reconcile before retrying;
- if the effect is explicitly `REEXECUTABLE` (for example a bounded LLM
  generation with no irreversible remote side effect), start a new physical
  invocation under a fresh reservation and let fencing select one logical
  result;
- if none applies, transition to `WAITING_INPUT` rather than blindly repeating
  an ambiguous effect.

A returning Adapter or stale worker that no longer holds the Run Lease may
append raw evidence only to a non-authoritative `InvocationEvidenceInbox`, keyed
by invocation ID, request digest, Adapter identity, and evidence digest. Inbox
append uses authenticated Adapter/process identity and idempotent content
identity, but cannot change the Run projection, select a logical receipt, settle
budget, or justify completion. The current fenced owner validates provider
identity/signature, request/operation match, and conflicts, then promotes at
most one result through the normal guarded invocation transition. Conflicting or
unverifiable late evidence moves reconciliation to `WAITING_INPUT`. Thus late
receipts survive pause or lease takeover without giving a stale worker commit
authority.

LLM calls, tool calls, Docker executions, evaluator invocations, and experience
commits are effects even when their current Implementation is in-process.

### 9.2 Process and container ownership

In-process Adapters are permitted only for short, bounded, cooperatively
cancellable work with an enforced timeout. Any Activity that can block beyond
its progress deadline runs in an owned subprocess or container, so revoking its
fence cannot leave unbounded work consuming resources inside a shared worker.
Adapter registration requires a conformance test proving timeout/cancel leaves
zero owned task/thread and that no new post-fence dispatch authorization can
commit. A
deliberately blocking/non-cooperative implementation is rejected as in-process
and must be routed through the subprocess/container Adapter.

The subprocess Adapter first commits the invocation/effect identity, then starts
a tiny owned launcher shim in a new session. The shim carries non-secret
run/Activity/effect/invocation markers and cannot exec the real workload until
the parent has persisted PID, process-group/session ID, OS process start time,
executable marker, and a one-shot start authorization. EOF or a short timeout
before authorization makes the shim exit, so crash-between-spawn-and-persist
cannot leave unowned work. Recovery can discover a shim by the unique invocation
marker and prove whether execution was authorized.

The Docker Adapter uses `create` before `start`, labels the container with
run/Activity/effect/invocation identities plus a nonce, persists container ID,
engine identity, labels and creation time, then authorizes `start`. A crash after
create is reconciled by the unique labels before any retry. It queries those
labels before checkpoint, stop, kill, or reconcile; killing only a `docker run`
client is not successful cancellation. Both Adapters implement bounded `query →
checkpoint-if-native → TERM/stop → KILL/kill → reconcile`, revalidate ownership
before destructive control, and report an unresolved remote/container state as
`WAITING_INPUT` rather than a fabricated terminal result.

### 9.3 Artifact commit

Before an executor may write output bytes, the control role commits a durable
staging claim keyed by stable logical output identity. The claim binds the owner
Activity/generation/fence, a unique temp nonce/path on the target filesystem,
and lease/progress expiry. The executor then writes that temp file, flushes and
`fsync`s it, computes digest and size, and submits them to control. A control
transaction performs `ABSENT → MATERIALIZE_PREPARED` for generation 1, or
`DELETED → MATERIALIZE_PREPARED` with an incremented object generation, and
binds the exact staging claim/digest/size. If the object is already `LIVE`, the
existing bytes must first verify; control then atomically creates the new
owner's `ACTIVE` artifact ref and consumes/releases its staging claim, while the
executor removes the redundant temp file. This verified-LIVE reuse path never
enters materialization. A competing prepared generation is waited on or taken
over only after its claim is durably expired/revoked.

Only the exact materialization claimant may atomically install the temp file at
the content-addressed location and `fsync` the destination directory. A final
control transaction rechecks claim epoch, object generation, digest, and size,
then atomically performs `MATERIALIZE_PREPARED → LIVE`, publishes the first
artifact reference, and consumes the staging claim. Thus there is no
rename-before-row or `LIVE`-without-first-reference window. A staging cleaner
may act only after a claim is expired/revoked and won by CAS; a paused publisher
with a live claim is not an orphan, and a fenced publisher can no longer publish
even if it later leaves harmless unreferenced bytes. Recovery inspects the
staging/lifecycle state plus temp/live paths and deterministically completes or
rolls forward every claim/write/rename/finalize seam; ambiguous or missing
bytes fail closed.

Cancellation, incident fencing, or abandoned production uses a separate
crash-safe abort path. If verified-`LIVE` reuse has not acquired a materialization
generation, recovery CASes only its staging claim to `CLEANUP_PREPARED`, removes
the redundant temp after publisher exit, and releases the claim without changing
the existing object/ref set. Otherwise a recovery owner first revokes staging
install authorization and terminates/waits for the exact Run-owned publisher
task/process. It then fences any already-registered materialization actor using
the prior-actor termination and lock-release protocol below; only after that may
one transaction CAS the exact object/staging generation to
`MATERIALIZE_ABORT_PREPARED` with a fresh filesystem-mutation epoch. The newly
registered abort actor removes the temp file and, if install already happened,
atomically moves the zero-ref live-path bytes to quarantine and directory-fsyncs.
A final control transaction advances the object to `QUARANTINED` (installed
bytes retained for grace) or `DELETED` (no installed bytes), marks the staging
claim released/cleaned, and records the abort event. Crash recovery rolls
forward from `MATERIALIZE_ABORT_PREPARED` by inspecting both paths. If publisher
termination, prior mutation-actor exit/lock release, path ownership, or byte
state cannot be proved, the claim remains active and the Run stays non-terminal.

Every mutation of a shared content path—including materialization install,
abort-to-quarantine, GC move, restore, and final delete—runs in a dedicated,
killable, gated filesystem-mutation actor, never inside the control process or
an ordinary executor. A prepare transaction first reserves the exact object
generation, operation kind, operation nonce, and monotonic `fs_mutation_epoch`.
The launcher then creates a still-gated actor; a second CAS persists its exact
PID, OS process start time, session/process-group identity, executable identity,
and per-object-generation advisory-lock identity before the actor receives a
one-shot authorization. The actor holds that process-shared kernel lock across
the path mutation and required file/directory `fsync`, and finalization rechecks
the same object generation, operation, nonce, and mutation epoch. V1 never
adopts an unregistered actor.

Before any higher mutation epoch may be CASed or authorized, control must
revalidate the exact actor recorded for the prior epoch, terminate it with a
bounded TERM/KILL sequence, wait for process exit, and observe release of the
per-object-generation kernel lock. Failure to prove exact identity, exit, or
lock release leaves the lifecycle claim active and fails closed. Consequently,
a `SIGSTOP`ped old abort, materialize, GC, restore, or delete actor cannot later
resume beneath a restored `LIVE` object or an `ACTIVE` reference. Removing a
verified-`LIVE` reuse temp is staging-only cleanup of a unique nonce path and
does not mutate the shared content path. It nevertheless uses a durable
staging-cleanup epoch and exact gated cleanup-actor identity, requires publisher
exit and claim ownership, and rechecks that authorization immediately before
each `unlink`/directory-`fsync`; it does not allocate an object mutation epoch
or take the shared-content lock.

`runtime_artifact_refs` is the only GC-root relation: each row binds object
digest/generation to an owner kind/ID, creating event sequence, retention/export
policy digest, and `ACTIVE|RELEASED` state. Non-terminal Runs, retained replay
histories, workflow/policy/Adapter bundles, checkpoints, provenance/evidence,
and each snapshot consumer hold explicit active refs. A retained journal event
that records a now-released reference is audit history, not silently a root;
the `ArtifactReferenceReleased` event and tombstone make replay expect expired
bytes. Snapshot import creates the consumer ref before producer retention may
release its own.

`runtime_artifact_handoffs` is a coordination sidecar, never a second byte-root
relation. For Campaign Admission Profiles it stores deterministic handoff ID,
Experience ID, Work Item ID plus its frozen canonical projection/payload digest,
artifact ref ID plus object digest/generation, profile ref/digest,
owner, `PENDING|BOUND|RELEASED`, creating/current event sequence,
current `enqueue_attempt_id/generation/state/fence`, and nullable Ledger enqueue
receipt ref/digest plus enqueue-transaction sidecar ref/digest. Both pairs are
null while `PENDING`, both are non-null while or after `BOUND`, and both remain
null on an `ORPHAN_ABSENT/RELEASED` branch whose composite release evidence
instead binds the abandonment proof and abandoned receipt. The
`runtime_artifact_handoff_attempts` relation retains every
attempt identity and its monotonic state
`IN_FLIGHT -> RETIRED -> PROVED_ABSENT`, `IN_FLIGHT -> LEDGER_PRESENT`, or
`IN_FLIGHT -> RETIRED -> LEDGER_PRESENT`; every
transition is backed by an append-only Runtime event. Creation atomically inserts an `ACTIVE`
`runtime_artifact_refs` row and `PENDING` handoff after verified `LIVE` bytes.
`BOUND` requires read-back of a Ledger Work Item whose immutable artifact-ref ID
and profile identities match, plus the exact enqueue receipt and enqueue-
transaction sidecar whose attempt triple/original proof/transaction digests all
match. A `RETIRED -> LEDGER_PRESENT` recovery transition additionally requires
old-fence drain and a request-bound `QUEUED_PRESENT` proof for that exact attempt.
`RELEASED` requires
either a later-frontier pre-enqueue absence proof after stop + higher-fence
attempt retirement + old-transaction drain **and** the exact durable enqueue-
obligation-abandoned proof **and** independently read-back matching
`abandoned_before_enqueue` receipt ref/digest, or a
terminal Work Completion and satisfied campaign replay/audit-retention rule; it
atomically emits `ArtifactReferenceReleased` and releases the ref. A handoff row
without an active ref cannot protect bytes, and an active ref remains the sole
fact counted by GC.

After active references are later released by committed policy transitions,
garbage collection computes reachability as the count of `ACTIVE` ref rows for
the exact digest/generation, marks an unreachable `LIVE` object, and waits a
configured grace period. It uses serialized lifecycle CAS
transitions `LIVE → MOVE_PREPARED → QUARANTINED → DELETE_PREPARED →
DELETED`. The first transition succeeds only while reachability is still zero.
Publication/import creates its reference only in a transaction that observes
`LIVE`; if it commits first, the GC CAS fails, and if GC commits first,
publication waits and uses the audited `QUARANTINED → RESTORE_PREPARED →
LIVE` path before publishing. No reference can be committed while an object is
moving.

Filesystem rename/fsync work happens after each prepared-state transaction,
never inside it and only through the fenced filesystem-mutation actor protocol
above. Final deletion requires a second grace period, zero
reachability, and a `DELETE_PREPARED` CAS; restore and delete claims cannot both
win. The tombstone retains its monotonic object generation, and re-production
uses the same staged `DELETED → MATERIALIZE_PREPARED → LIVE` protocol with
freshly verified bytes. This closes both initial-publication and post-recheck
TOCTOU windows, so deleting a producer Research Run cannot remove content still
reachable from a consumer.

Artifact existence alone never marks a stage complete. Its digest, schema,
producer, input scope, and committed event must all agree.

### 9.4 Checkpoint contract

Every Runtime Activity declares one policy:

- `RESUMABLE`: produces durable semantic checkpoint and resume token;
- `RESTARTABLE`: safe to repeat from its Activity start under the same stable
  effect identities;
- `RECONCILE_ONLY`: an ambiguous external effect must be queried;
- `NON_RESUMABLE`: cannot be repeated automatically and waits for an operator.

Activities expected to exceed five minutes must implement a semantic progress
cursor and either `RESUMABLE` or an explicit, reviewed `RESTARTABLE` policy.
V1 checkpoints occur at model/tool calls, durable file outputs, training-native
checkpoints, and verification/recording commits. V1 does not serialize arbitrary
Python stacks, GPU memory, or browser process state.

## 10. Lease, concurrency, retry, and budget

### 10.1 Lease and fencing

The SQLite transaction assigns a monotonically increasing lease epoch. Every
stage commit, checkpoint, receipt, and budget settlement includes that epoch.
After takeover, writes from the old worker fail even if it resumes after a
pause or network partition.

V1 permits one active Runtime Activity per Research Run; run-level parallelism
is fixed to 1, while different Research Runs may execute concurrently. A renewal
is valid only for the same owner and unexpired epoch. After expiry, even the same
owner must reacquire and receive a new epoch. Operator control commands use
event-sequence CAS and may revoke this epoch without acquiring the lease.

Lease liveness answers “may this worker commit?” Activity progress answers “is
the work advancing?” A background heartbeat cannot satisfy both questions.

### 10.2 Retry taxonomy

| Failure class | Runtime decision |
| --- | --- |
| timeout, 429, 5xx, transient process exit, preemption | retry the same Runtime Activity within budget |
| invalid Observation or failed scientific metric | finish the Attempt as evidence; policy may open a new Attempt |
| authentication, invalid policy/configuration, incompatible version | fail or wait for operator; no blind retry |
| remote success with missing receipt | reconcile using stable effect identity |
| no idempotency/query and not explicitly re-executable after ambiguous effect | `WAITING_INPUT` |
| exhausted Budget Envelope | terminal or paused according to predeclared policy |

There is one retry owner. Stage Adapters may report typed failure information
but must disable hidden client retries. A client retry is allowed only when an
SDK hook returns control before every physical request so the Runtime can first
persist a new invocation and reservation; bounded but invisible retries are
still forbidden.

### 10.3 Budget reservation

Before work begins, the Runtime reserves upper bounds for Experiment Attempts,
LLM calls, tokens, wall time, and GPU time. Every physical `invocation_id` owns a
separate reservation even when several invocations implement one logical effect.
After a receipt it settles observed use and releases only the proven remainder.
An ambiguous or fenced-out invocation retains its worst-case reservation until
the Adapter proves it did not execute or reports final usage. This prevents a
takeover from hiding spend by settling only the winning receipt.

Attempt-scoped work uses dual-scope admission. Its reservation must fit both the
remaining effective Run cap and that immutable AttemptSpec's allocation; receipt
settlement is charged atomically to both ledgers. Infrastructure retry/takeover
stays under the same Attempt allocation, and unused capacity from another
Attempt cannot be borrowed or reassigned. Run-scoped snapshot/decision work is
charged only to the Run ledger but remains in campaign totals.

The hard invariant is an **admission cap**: settled usage plus open worst-case
reservations never exceeds the effective Budget Envelope. It is also an
external-spend cap only for Adapters that enforce request token limits,
timeouts, or GPU limits. Unenforceable provider billing is reported separately
and is never described as provably capped. A crash cannot double-settle one
invocation because receipt and settlement share its idempotency identity.

`AmendBudget` appends a run-level effective-cap overlay and can affect only
future reservations. It cannot reduce below settled plus open reserved usage or
change an Experiment Attempt allocation after that Attempt is created.

`max_attempts=3` means at most three Attempts, not a requirement to consume all
three. Early stopping is a first-class Continuation Decision.

## 11. Stage Continuation and reuse

### 11.1 V1 workflow

```text
Research Run scope
  prepare → survey → method_review → freeze_context

Research Run decision scope (no new Hypothesis or Attempt yet)
  diagnose → intervention_plan (includes Hypothesis/Intervention validation)

Experiment Attempt scope (opened only after the Intervention is fixed)
  materialize → execute → verify → reflect → record → distillation_receipt
```

The current broad `plan` responsibility is split:

- `method_review` belongs to the immutable Research Context Snapshot;
- `diagnose/intervention_plan` may cite an existing Hypothesis and Recall
  Context, but a new Hypothesis is not persisted yet. After the decision produces
  a schema-valid Hypothesis, Intervention, seed, Attempt allocation, and
  Evaluation Contract binding, the Runtime atomically creates a new Hypothesis
  with its first immutable Experiment Attempt, or opens another Attempt under an
  existing Hypothesis. Cancellation or validation failure before that transition
  leaves neither a zero-Attempt Hypothesis nor a partial Attempt.

Recall Context enters `diagnose` and `intervention_plan` only after the shared
snapshot is frozen. This prevents later experience, private labels, or mutable
workspace data from contaminating supposedly reusable preparation.

The current `implement`, `judge`, `submit`, and `analyze` implementations are
initially wrapped by attempt-scoped Stage Adapters. Their responsibilities can
then be narrowed without changing the Runtime Interface.

### 11.2 Reuse key

```text
stage_contract_version / stage_name / canonical_scope_digest / input_digest
```

`run_id` is provenance, not part of reusable content identity. Reuse requires an
exact digest match and a committed successful stage event. The canonical scope
digest includes task request, references, source and dataset identities,
workflow-definition reference/version/digest, continuation-policy reference/
version/digest, Runtime/stage/Adapter interpreter-contract bundle digests,
model/tool configuration, and
the actor-visible `DecisionContractView`. It excludes the full/private Evaluation
Contract digest, evaluator identity, treatment metadata, and attempt-specific
Recall Context by construction. The Run spec and AttemptSpec still bind the full
Evaluation Contract for verification; a private-only contract change may create
a new Run while preserving actor-side snapshot/cache identity when the public
view and reuse-governance policy are unchanged.

Content identity is separate from reuse authorization. Every Run spec also
derives a `reuse_governance_digest` from tenant/security boundary, data
classification, source export permission, evaluator privacy, storage locality,
retention, and execution-isolation policy. A Snapshot Build Claim is keyed by
`canonical_scope_digest + reuse_governance_digest`, so incompatible isolation
domains never share a producer. Before import, the Runtime re-evaluates both
producer export and consumer admission policy; the import event records both
policy digests and the authorization result. Consumer retention may extend an
artifact lifetime but can never weaken producer restrictions. Exact content
match without policy compatibility is a cache miss, not permission to import.

Every stage contract declares exactly one reuse policy:

- `SNAPSHOT_IMPORTABLE`: only `prepare`, `survey`, `method_review`, and
  `freeze_context`; exact-scope artifacts may be imported across Research Runs;
- `RUN_LOCAL_REPLAY_ONLY`: `diagnose` and `intervention_plan`; a committed result
  may satisfy replay within its original Run/generation and identical Recall/
  decision-input digest but cannot become evidence for another Run;
- `NEVER_REUSE_AS_NEW_ATTEMPT_EVIDENCE`: all Attempt-scoped stages, including
  materialize, execute, verify, reflect, record, and distillation receipt.

Cross-Run import defaults to forbidden unless the contract explicitly declares
`SNAPSHOT_IMPORTABLE`. The consuming Research Run commits a
`SnapshotImported`/`StageReused` event that cites the producing run and artifact
digests; it never aliases another run's mutable projection. An Observation,
Verification Record, or Experience Record is never rebound to a new Experiment
Attempt, even when its bytes or input digest happen to match.

On a cold concurrent miss, a unique private Snapshot Build Claim keyed by the
content scope plus reuse-governance digest elects one producer and carries its
own owner Activity, fencing epoch, same-boot monotonic lease expiry, progress
cursor/deadline, and `BUILDING | PUBLISHED | ABANDONED` state. The producer must
hold both its Run Lease and current Claim epoch to publish. Claim renewal is
coupled to semantic build progress, not a background heartbeat. Producer pause/
cancel/stall atomically abandons or revokes its Claim; producer death lets the
Claim lease expire, after which waiting consumers race to acquire a higher epoch.
Other Research Runs wait on a durable Claim timer, then commit import events
after publication. Stale producer publish is rejected by both fences.
This single-flight state is not a shared Research Run projection; it exists only
to prevent duplicate expensive snapshot construction.

Cross-run, cross-seed, or cross-arm snapshot import is allowed only when the
complete actor-visible snapshot scope/DecisionContractView matches and the
reuse-governance policy derived from the full Evaluation Contract declares that
reuse cannot leak evaluation information. Reports must show both unamortized
first-Run cost and amortized campaign cost.

### 11.3 Invalidation matrix

| Change | Required invalidation |
| --- | --- |
| task, references, source, dataset, workflow, model/tool configuration, or full Evaluation Contract | new Research Run; the old spec/snapshot remain immutable, and snapshot import additionally requires an identical actor-visible DecisionContractView and compatible governance |
| corrupt/invalid derived snapshot under the same pinned spec | new snapshot generation; reuse only stage artifacts whose own input digests still match |
| method family or main Hypothesis changes under the same request | new Hypothesis; reuse the snapshot only if its scope remains exact |
| Recall Context or proposed Intervention before Attempt creation | Hypothesis diagnosis/plan only; no existing Attempt is mutated |
| Intervention after an Attempt exists | create a new Experiment Attempt; never mutate the old one |
| seed or Attempt budget | new Experiment Attempt |
| reflection or Experience-ingestion/distillation policy | new Research Run in v1 because workflow/continuation policy is pinned; old records and Attempt evidence remain immutable |

Candidate branching and parallel search can later be represented by additional
commands and workflow actions. V1 deliberately keeps one active Hypothesis path;
it must not pre-build an unused distributed DAG Seam.

## 12. Storage Implementation

SQLite runs in WAL mode with foreign keys enabled and `synchronous=FULL` for
authoritative transitions. The minimum logical tables are:

- `runtime_runs`: immutable spec digest, pinned versions, admission key, current
  projection, new-work gate, terminal-barrier state, and terminal-failure
  receipt binding; `UNIQUE(run_kind, admission_key)` is the start/reply-loss
  idempotency authority;
- `runtime_commands`: command ID, payload digest, receipt, accepted version;
- `runtime_events`: append-only event sequence and canonical payload;
- `runtime_leases`: owner, epoch, expiry, last renewal;
- `runtime_activities`: scope, generation, input digest, policy, state;
- `runtime_checkpoints`: Activity/generation/progress cursor, checkpoint policy,
  input/schema digests, resume-token artifact reference/digest, and producer epoch;
- `runtime_effects`: stable effect key, prepared state, receipt, reconciliation;
- `runtime_invocations`: physical invocation ID, logical effect, request and
  Adapter digests, worker epoch, reservation, durable dispatch state, receipt,
  and observed/worst-case usage;
- `runtime_timers`: stable timer ID, due time, claim owner/epoch/expiry, and
  timer kind including commit-reconciliation deadlines, bound authorization,
  and scheduled/claimed/fired/cancelled state;
- `runtime_pending_control_resolutions`: append-only resolution of each pending
  public cancel or authenticated system failure against one authorization;
- `runtime_pending_controls`: durable `PRIMARY|FOLLOWER` control intents and
  typed command/system sources; a partial unique index permits exactly one open
  primary per target authorization and each control has one resolution;
- `runtime_run_terminal_failure_receipts`: immutable cause and exact settled-
  coverage proof for `RUNTIME_FAILURE_AFTER_WORK|RUNTIME_FAILURE_AFTER_CLOSURE`;
- `runtime_decision_recall_phases`: per-Intent registering/context/outcome phase
  and its sole active authorization;
- `runtime_decision_recall_append_authorizations`: tagged admission-or-commit
  single-use exact Intent/Context/Outcome append proof and terminal no-commit
  state;
- `runtime_distillation_commit_authorizations`: single-use proposal/commit-plan
  proof and terminal success/no-commit state;
- `runtime_distillation_closure_authorizations`: mutually exclusive typed
  cancelled/dead-letter closure proof;
- `runtime_artifact_staging`: stable logical-output ID, owner Activity/
  generation/fence, temp nonce/path, claim epoch/expiry/progress deadline, and
  cleanup epoch/operation nonce/exact gated cleanup-actor identity, plus
  `CLAIMED|DIGESTED|BOUND|CLEANUP_PREPARED|CONSUMED|RELEASED` state before
  digest-keyed materialization;
- `runtime_artifacts`: digest, schema, scope, producer, durable location,
  lifecycle state/object generation including `MATERIALIZE_ABORT_PREPARED`,
  filesystem-mutation operation/nonce/epoch, exact actor PID/start/session/
  executable identity and per-object-generation lock identity, and pinned
  workflow/policy/Adapter-contract artifacts;
- `runtime_artifact_refs`: object digest/generation, owner kind/ID, creating
  event, retention/export policy digest, and active/released state; this is the
  only artifact-byte GC-root relation;
- `runtime_artifact_handoffs`: deterministic Work Item/profile handoff ID,
  Experience, Work Item/payload-digest, artifact-ref identities, object/profile
  digests, owner, current
  event, enqueue attempt ID/generation/state/fence, optional Ledger enqueue
  receipt ref/digest and enqueue-transaction sidecar ref/digest, and
  `PENDING|BOUND|RELEASED` state; this coordinates cross-store ownership but is
  never itself a byte GC root;
- `runtime_artifact_handoff_attempts`: one row per per-handoff enqueue attempt,
  with monotonic generation/fence and journal-backed monotonic state/evidence;
- `runtime_distillation_enqueue_obligation_abandonments`: immutable source-
  control proof binding the exact Experience, Work Item payload digest, and
  semantic lineage, and asserting that a proved-absent pre-enqueue obligation will never retry and
  may release its orphan Work-Item reference;
- `runtime_shared_work`: Snapshot Build Claims by canonical content scope plus
  reuse-governance digest, with owner Activity, epoch, expiry, progress deadline,
  state, and published artifact references;
- `runtime_invocation_evidence`: non-authoritative append-only late evidence,
  keyed by invocation/request/Adapter/evidence digests;
- `runtime_budgets`: cap, reservation, settlement, cumulative usage;
- `runtime_outbox`: durable notifications and compatibility projections;
- `runtime_admission_incidents`: admission epoch, enabled flag, incident ID/
  scope/reason, and audited resolution.

Event append and projection update occur in one transaction. The event journal
is authoritative; the projection is rebuildable and checked during recovery.
Schema migrations are versioned and replay-tested. A corrupt journal, an
artifact missing while an active ref/lifecycle requires live bytes, an invalid
digest, or an incompatible event version fails closed; a released ref plus
audited `DELETED` tombstone is valid replay state.

Only the supervised control-role process may open authoritative SQLite write
transactions. Before each write it acquires a process-shared advisory writer
gate and publishes a non-authoritative owner marker containing control ID,
PID/start time, transaction ID/kind, and acquisition monotonic time. SQLite
remains the safety authority; the gate exists only to identify a stopped lock
holder during control-role restart races. Write transactions perform no IPC,
artifact-filesystem, external, or model work beyond SQLite's own commit I/O and have a hard 2-second hold ceiling
(normal p95/p99 gates are much lower). If the gate is held beyond that ceiling,
the launcher revalidates the exact supervised control child, sends bounded
TERM/KILL, waits for kernel gate release, restarts control, and retries through
the idempotent client protocol. It never signals CLI/Web or an executor for a DB
lock because those processes cannot own one. Killing during commit relies on
SQLite recovery, then event/fence replay; a stopped process cannot indefinitely
block Pause, Cancel, incident, or watchdog preemption.

`InMemoryRuntimeStore` and `SQLiteRuntimeStore` must pass the same contract suite.
The repository already has a useful precedent in the SQLite experience ledger,
but runtime state remains a separate Module and references experience IDs rather
than sharing partial transactions across unrelated stores.

## 13. Adapter policy and Locality

Real variation justifies these Adapters:

- workflow: `ProvidedIdeaStagesAdapter` and
  `ReferenceIdeationStagesAdapter`;
- execution: in-process, local subprocess/Docker, and scripted fault-test
  Adapters;
- verification: command-backed and fake deterministic Adapters;
- storage/artifacts: SQLite/filesystem and in-memory test Implementations.

Pure budget arithmetic, retry classification, projection, and continuation stay
inside the two Modules. V1 does not add object-store, queue, or distributed
execution Adapters that have no second real Implementation.

Recommended file Locality:

```text
research_agent/runtime/
  long_task.py                 # public commands, queries, snapshots, Interface
  stage_continuation.py        # pure continuation Interface + Implementation
  _journal.py                  # SQLite events, projection, lease transaction
  _effects.py                  # effect receipts and reconciliation
  _artifacts.py                # content-addressed artifact commits
  _budget.py                   # reservation and settlement
  launcher.py                  # operational Interface; supervises local roles
  _control_server.py           # sole SQLite writer + authenticated local IPC
  worker.py                    # private executor/control role entrypoint
  adapters/
    stages.py
    process.py
    verification.py
```

Types live beside the Seam that owns them. A catch-all `models.py`, `state.py`,
or `status.py` would disperse invariants and reduce Locality.

### 13.1 Launcher/control/executor operational Interface

The durable journal makes work resumable; automatic recovery additionally
requires a launcher independent of CLI/Web. Supported v1 profiles are a
foreground test launcher plus documented `launchd`, `systemd`, or container
deployments; all invoke the same long-lived
`python -m research_agent.runtime.launcher --root ABSOLUTE_RUN_ROOT` wrapper,
not `worker.py` directly. The wrapper starts exactly one control child and one or
more executor children through private `worker.py --role control|executor`
commands, creates/owns their readiness pipes, interprets child exit codes,
monitors the SQLite writer-gate owner, and applies bounded restart backoff.
Native launchd/container exit filtering or ready-pipe creation is therefore not
assumed, and Docker `restart=always` alone is not conforming. `--root` resolves the journal and artifact root
without consulting the caller's current directory; its canonical path and
storage identity are logged before readiness. Install-time `--check-config`
returns `64/70/78` for usage/integrity/incompatibility, but service mode keeps
the launcher alive in `BLOCKED_OPERATOR` on those errors so native on-failure
supervision cannot loop. Control-child incompatible schema/version is `78`, integrity failure
is `70`, transient failure is `75`, and unexpected fault is `1`. Child `1/75`
gets bounded-backoff restart; child `64/70/78` puts the still-live launcher into
`BLOCKED_OPERATOR` without a restart loop. The service-mode wrapper itself exits
`0` only for a requested clean drain and `1/75` for unexpected/transient wrapper failure;
ordinary systemd/launchd `on-failure` behavior can therefore supervise it.

POSIX parentage alone is not an ownership mechanism. Every child is born behind
an exec gate and receives a dedicated parent-death guard pipe whose only writer
is the launcher; all unrelated descriptors are close-on-exec. Before sending
the one-shot exec authorization, the launcher atomically writes and
directory-fsyncs an operational cohort record containing storage/root identity,
launcher generation and nonce, child role, PID, OS process-start identity, and
executable digest. Guard EOF makes a child close admission/claims, terminate
its owned descendants through their normal ownership protocol, and exit.
Linux parent-death signals, service cgroups, or container init are optional
hardening; the guard-pipe contract is the portable v1 baseline.

On every start, the launcher first acquires an exclusive per-root launcher gate
and completes a role-reconciliation barrier before spawning a control role. It
validates each prior control/executor cohort member by the exact PID +
process-start + role + executable + storage/generation tuple, sends bounded
TERM/KILL, waits for that role identity to disappear, and reconciles stale
socket/status/cohort records. V1 does not adopt an old role. A mismatched
identity is never signalled; an unprovable or unterminated prior role puts the
new launcher in `BLOCKED_OPERATOR` and forbids a new control child.

Persisted subprocess/container workloads are deliberately not part of that
pre-control barrier: only the Runtime journal can authorize their reconciliation,
and the launcher is not a Run-state writer. After old roles are gone, the new
control starts as the sole writer in `RECOVERING`, advances the control/fencing
generation, and lets recovery executors query/stop/reconcile exact journal-owned
work. During this second barrier, application handshakes are not ready and no
new external dispatch is authorized. Only zero unreconciled owned workload may
advance the launcher to `READY`; an unprovable/unterminated workload instead
holds `BLOCKED_OPERATOR` with the new control available only for authenticated
recovery/inspection. Child startup uses the same gated persist-before-authorize
handshake, so a launcher crash before cohort persistence cannot create an
unrecorded worker. The launcher gate plus the two barriers prevent overlapping
wrapper restarts from creating two control roles without deadlocking journal
reconciliation.

Children emit one JSON readiness record to launcher-owned private pipes. After
the control child opens/replay-validates the store, binds the permission-checked
Unix socket, and the configured minimum executor count is ready, the launcher
atomically writes and directory-fsyncs a non-authoritative status projection
under the run root. Its schema contains protocol, `READY|BLOCKED_OPERATOR|
DRAINING`, launcher/control PID+start identities, executor count, storage ID,
runtime/schema versions, and generation. Application readiness additionally
requires a successful socket handshake with the same generation; process-alive
or a stale status file is not ready, and ready is not semantic progress.

The launcher also owns an out-of-band control-liveness channel. It sends a
nonce ping every 5 seconds and requires the exact control child to echo it within
15 seconds; control requests/planning/reads have a pinned 5-second hold ceiling
and writes the stricter 2-second gate ceiling. Missed liveness or an over-ceiling
outstanding request causes TERM/KILL of that exact child and restart, even when
no SQLite writer gate is held. This process-health signal is separate from both
Run Lease renewal and Activity semantic progress.

`SIGTERM`/`SIGINT` to the launcher initiate bounded drain: close command
admission, stop executor claims, reconcile children/leases, remove the socket,
publish `DRAINING`, and exit `0`. If safe drain cannot complete, it fences work,
leaves durable recovery evidence, and exits `75`. `SIGKILL` recovery is handled
by guard EOF plus external-supervisor restart, startup reconciliation, and
lease/fencing. Poll/backoff bounds and the
independent progress-watchdog interval are pinned deployment configuration and
recorded in the acceptance manifest. Exactly one control role per store and
multiple executor roles are allowed; correctness relies on store claims/fencing,
not launcher process liveness.

Acceptance separately kills an executor, the control child, and the launcher
alone. The launcher-only case deliberately exercises surviving or stopped
children, stale socket/status/cohort data, and overlapping supervisor restarts;
no new control may start until exact prior role identities are gone, and a
`RECOVERING` control may not become ready or authorize new dispatch until owned
work is reconciled. The test measures fault timestamp through restart to the
first new semantic continuation event. An embedded worker without an external launcher/control service provides
durable resumability after a human restart, but must not be advertised as
automatic recovery or as meeting the RTO SLO.

### 13.2 Admission circuit breaker and integrity incidents

The Long-Task Runtime store owns a small operational safety projection with
`admission_epoch`, `durable_admissions_enabled`, and active incident IDs/scopes.
It is not another workflow authority. Creating an integrity incident and closing
new admissions is one authenticated operational transaction. A `DriveRun` that
would create a new Run in the closed scope returns public `AdmissionClosed`; a
command for an already-bound Run matching the active incident returns public
`IncidentFenced`, except the monotonic fail-safe `CancelRun`; reads remain
available. Previously accepted command replay is resolved before this current-
epoch gate. Every worker claim/commit checks the same epoch through the
private control protocol and is rejected before its per-Run projection is
updated, so an all-Run incident cannot race stale workers. Existing Runs outside
the incident scope remain driveable.

An idempotent sweeper then uses a private authenticated `RunQuarantined` system
transition, incident ID, and per-Run event-sequence CAS retry to revoke each
affected fence and place the Run in `WAITING_INPUT` with integrity provenance.
The sweep is not falsely described as one cross-Run atomic transaction; the
global incident check supplies immediate safety, and per-Run events supply
replayable state. Clearing an incident or resolving a Run is separately
authenticated and audited. Public application commands remain the closed v1
union.

## 14. Integration and migration

Migration is incremental but has one source of truth at each step:

1. instrument the current path and freeze baseline traces;
2. land the event/store contracts and pure continuation policy;
3. express the current seven-stage order through `StageContinuation` without
   changing behavior;
4. add leases, fencing, effect receipts, process-group cancellation, budgets,
   and recovery;
5. extract the run-scoped Research Context Snapshot and split current planning;
6. wrap both entry flows and `AdaptiveExperimentRunner` behind Stage Adapters;
7. make the new journal authoritative and emit legacy JSON from the outbox;
8. switch CLI/web callers to the two public Runtime entrypoints;
9. remove `MasterRuntime`, the independent Supervisor state machine, manual
   `progress()/complete_stage()/finalize()`, and redundant retry owners.

A temporary `LegacyFlowStageAdapter` may treat an entire old `InnoFlow` as one
Runtime Activity. This gives coarse restart protection, but it must not be
reported as fine-grained Stage Continuation.

During migration the rollout flag is `legacy | durable`. There is no mode in
which legacy JSON and the SQLite journal are both authoritative. Phase 8 retires
the flag and all production legacy admission; later rollback means deploying a
manifest-approved, retained content-addressed previous durable deployment bundle
whose Runtime/Adapter/schema replay compatibility has passed against a copy of
the current journal, or closing admissions. It never downgrades the journal and
never executes the sealed benchmark-only legacy harness.

## 15. Observability and operator behavior

Every event includes `run_id`, event sequence, workflow and continuation-policy
digests, snapshot
generation, stage/Activity identity, Attempt identity when applicable, fencing
token, command ID, and trace ID.

Minimum operator views:

- why the Research Run is running, waiting, paused, failed, or terminal;
- the next Continuation Decision and its input digest;
- lease owner versus last scientific progress;
- reserved and settled budget by category;
- retries by typed failure class;
- ambiguous effects requiring reconciliation or input;
- exact Observation and Verification Record that justify completion.

The web stop action submits `CancelRun`; it no longer sets an unrelated flag.
Cancellation sends signals to a new process session/group, waits a bounded
grace period, then kills the entire owned process tree. Late commits still fail
through version and fencing checks.

## 16. Interface alternatives considered

Three deliberately different Interface designs were evaluated:

1. **Lifecycle methods** — `run`, `submit`, `resume`, `events`, `cancel`. This is
   convenient for one caller but exposes orchestration order and grows whenever
   a lifecycle action is added.
2. **Handle-oriented Runtime** — return a mutable run handle with `step`,
   `checkpoint`, and `complete`. This is small initially but makes caller-held
   process state part of recovery and permits invalid transitions.
3. **Command/event Runtime plus pure continuation** — two application entrypoints
   and one internal planning Seam. Closed command types preserve idempotency and
   optimistic concurrency while a thin Adapter retains convenient CLI usage.

Option 3 is selected because it maximizes Interface leverage without forcing
callers to understand ordering. Public `ForkRun` is deferred until candidate
branching exists; speculative extensibility is not a reason to enlarge v1.

## 17. Rejected alternatives

- **Patch the current heartbeat files.** This cannot atomically bind artifacts,
  budget, verification, and state, and cannot fence a stale worker.
- **Treat artifact existence as a checkpoint.** A partial or stale artifact is
  not proof of a committed stage under the current inputs.
- **Restart the whole script under Supervisor.** This repeats expensive work and
  leaves ambiguous external effects unresolved.
- **Adopt a workflow platform first.** Temporal and similar systems provide
  valuable semantics, but importing one before defining AI-Researcher’s
  scientific identities and effect contracts would move rather than solve the
  ambiguity. A future remote Implementation may preserve this Interface.
- **Checkpoint arbitrary process memory.** Semantic checkpoints are portable,
  testable, and bindable to scientific provenance; opaque process snapshots are
  optional execution optimizations, not the correctness model.
- **Call every retry a new Attempt.** Infrastructure retries do not change the
  scientific intervention and would corrupt the experience ledger.

## 18. Source-backed design rationale

- [Temporal architecture](https://github.com/temporalio/temporal/blob/main/docs/architecture/README.md)
  documents durable event history and deterministic workflow replay; Temporal’s
  [AI FAQ](https://go.temporal.io/platform-hub/faqs) explains why nondeterministic
  model calls belong in Activities rather than workflow logic. This motivates a
  pure `StageContinuation.plan()` and side-effecting Runtime Activities.
- LangGraph documents persistent checkpoints and notes that resume re-executes a
  node from its beginning, so node work should be deterministic or idempotent:
  [persistence](https://docs.langchain.com/oss/python/langgraph/persistence),
  [time travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel),
  and the [Functional API idempotency guidance](https://docs.langchain.com/oss/python/langgraph/functional-api).
- The AWS Builders’ Library explains why timeouts/retries need bounded backoff
  and why a timeout leaves side-effect outcome ambiguous
  ([timeouts and retries](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/)),
  and why caller-provided request identity makes retries safe
  ([idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)).
- AWS also documents the limits of lease-based leader election and the need to
  treat lease timing as a liveness aid rather than a correctness proof
  ([leader election](https://aws.amazon.com/cn/builders-library/leader-election-in-distributed-systems/)).
  This is why every worker-authored commit proposal is fenced even when the
  lease appears valid.
- SQLite documents serializable isolation, WAL behavior, and atomic commit:
  [isolation](https://www.sqlite.org/isolation.html),
  [atomic commit](https://sqlite.org/atomiccommit.html), and
  [`synchronous` durability](https://sqlite.org/pragma.html#pragma_synchronous).
- The [Crab paper](https://arxiv.org/abs/2604.28138) reports that semantic OS
  checkpointing improved recovery in its benchmark and reduced checkpoint
  traffic substantially with low no-fault overhead. It is evidence for semantic
  checkpoints, not evidence that those exact percentages transfer here.
- [LongDS](https://arxiv.org/abs/2605.30434) and METR’s
  [same-model scaffold analysis](https://metr.org/notes/2026-02-13-measuring-time-horizon-using-claude-code-and-codex/)
  are the basis for separating reliable long execution from improved reasoning.
- Python documents POSIX `start_new_session` and `process_group` primitives in
  [`subprocess`](https://docs.python.org/3/library/subprocess.html); v1 process-tree
  ownership and cancellation target supported macOS/Linux deployments.

## 19. Consequences

Positive consequences:

- Research Runs can survive process death and resume from committed semantic
  work;
- stale workers and duplicate commands cannot silently fork history;
- costly run-scoped preparation can be amortized safely across Attempts;
- every terminal completion points to immutable valid verification, including
  valid negative scientific outcomes;
- two entry flows converge behind one small Interface;
- fault behavior becomes deterministically testable.

Costs and limitations:

- event schema evolution and replay add Implementation complexity;
- splitting the two large `InnoFlow` implementations is the largest migration;
- ambiguous effects without idempotency or query support sometimes require an
  operator;
- SQLite is a deliberate single-host constraint for v1;
- no amount of recovery logic guarantees better scientific decisions;
- more granular checkpoints reduce repeated work but increase write volume.

The exact release gates, fault matrix, rollout order, and scientific evaluation
are normative in the linked implementation plan.
