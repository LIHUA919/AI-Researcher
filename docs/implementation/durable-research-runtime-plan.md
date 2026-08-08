# Durable Research Runtime 实施与验收计划

**Status:** Ready for implementation

**Scope:** Long-Task Runtime Module + Stage Continuation Module（“1 + 2”）

**Owner:** AI-Researcher maintainers

**Last updated:** 2026-07-31

**治理设计：**
[Durable Research Runtime and Stage Continuation](../design/durable-research-runtime.md)

**相关设计：**
[Experience-Driven Research Loop](../design/experience-driven-research-loop.md)、
[Verified Research Memory](../design/verified-research-memory.md) 和
[Context-Aware Tool Use](../design/context-aware-tool-use.md)

## 1. 交付目标

本计划把“长任务能力”拆成可验收的工程事实，而不是用“脚本跑得更久”代替：

1. Research Run 的 identity、event、checkpoint、budget、verification 和
   terminal status 在进程崩溃后仍然成立；
2. 新 worker 可以接管，但旧 worker 永远不能在接管后提交；
3. 已成功但回执未知的外部 effect 会 reconcile 或等待人工，不会盲目重复；
4. 同一任务的 `prepare → survey → method_review` 只形成一次不可变
   Research Context Snapshot；
5. 后续 Hypothesis 先完成 `diagnose → intervention_plan`，只有 Intervention、
   seed、allocation 和 contract 固定后才打开 Experiment Attempt；
6. `COMPLETED` 必须由所有 completion-required durable valid Verification/Experience、
   每个 Run-owned Decision Intent 的 Recall Decision Outcome、每个
   completion-required Experience 的 Experience Distillation Receipt 共同证明；
   Verification 的 `passed=false` 是有效负结果，不是 Runtime failure；receipt 不要求
   立即 promotion；
7. CLI 和 Web 只依赖两个公开 Runtime 入口；私有 worker/coordinator 藏在
   Long-Task Runtime Module 内，workflow policy 只通过一个纯 continuation Seam；
8. 可靠性、效率与科学能力分别验收，不把三者混成一个数字。

完成本计划后，可以主张“本地单机 Research Run 具备 durable semantic
continuation”。不能主张通用分布式调度、任意进程内存恢复或模型智能已经
提高。

## 2. 冻结基线与先决条件

### 2.1 当前可复现实验基线

VQ V2 报告把每个顶层执行标为 `trial`；按本文 canonical language，它对应一个
Research Run。其每 Run 平均值是后续效率对比的冻结基线：

| 指标 | 当前基线 |
| --- | ---: |
| Experiment Attempts | 3 |
| LLM calls | 133.5 |
| LLM tokens | 1,289,839 |
| serial wall time | 44.28 分钟 |
| training wall time | 10.94 秒 |
| training 占比 | 0.41% |

基线出处与实验语义见
[`experience-gain-next-round-plan.md`](experience-gain-next-round-plan.md)。
Phase 0 必须从原始 trace 重新生成机器可读 baseline manifest；文档里的数字
不能代替 benchmark 输入。

### 2.2 实施前冻结内容

在改 Runtime 前冻结：

- provided-idea 和 reference-ideation 各一份七阶段成功 trace；
- 每个 stage 的输入/输出 schema、artifact digest、LLM/tool calls、tokens、
  wall/GPU time；
- 当前成功、结构失败、训练失败、验证失败各至少一份 fixture；
- Evaluation Contract、evaluator digest、workflow/model/tool version；
- 旧流程最终 Observation、Verification Record、Experience Record、per-Intent Recall
  Decision Outcome 和 per-Experience Experience Distillation Receipt（当前不存在的明确标为缺口，
  不能伪造 fixture）；
- `git` revision、Python/runtime dependencies、数据集/source identities。

### 2.3 不可绕过的前置修复

治理设计已指出 writer 与 guardrail schema 不完全一致。正式迁移某 stage
前，该 stage 的 writer、validator 和 artifact contract 必须使用同一版本化
schema。测试中手写一个“guardrail 喜欢的 artifact”不等于真实 writer 已通过。

## 3. Release gates 总览

所有 Hard gate 必须通过；Stretch gate 不阻塞发布，也不能在未通过时写入
发布主张。

| Gate | 类别 | Hard 标准 |
| --- | --- | --- |
| G1 | Interface / Locality | 两个应用入口 + 一个 continuation 入口；CLI/Web 无旧 Runtime 直连 |
| G2 | durable safety | 已确认 transition 的 RPO = 0；false completion、duplicate logical commit、stale commit = 0 |
| G3 | recovery liveness | 预注册 recoverable profile 随机样本 100/100 自动恢复；端到端 RTO p95 ≤ 60 秒 |
| G4 | completion integrity | `SCIENTIFIC + COMPLETED` 无有效 Verification Record 数量 = 0；`MEMORY_DISTILLATION` exact-manifest Assignment/Completion coverage=100%、foreign=0、outcome mapping 正确；任一 terminal Run 的 open reservation/unfinal invocation/Run-owned execution/active artifact staging/materialization claim/Run-owned artifact filesystem-mutation actor/active Snapshot Build Claim = 0；valid negative 可正常完成 |
| G5 | cancellation | 每个 local eligible case 的 Run-owned task/thread/process-group/container/artifact mutation actor ≤ 10 秒清理并 reconcile；取消后无迟到 commit |
| G6 | continuation correctness | 每 snapshot generation 的 run-scoped logical commit 恰好一次；invalidation matrix 100% 命中 |
| G7 | efficiency | 10 个同 scope Research Runs：calls ≤ 255、tokens ≤ 2.5M、serial wall ≤ 90 分钟、throughput ≥ 6.5/hour；首 Run 也过 ceiling |
| G8 | regression | 无故障 paired pass delta 的 95% CI 下界 > -2 pp；每个正式 recoverable-fault pair 均实际触发，durable fault cell 自动恢复到与同 task/seed durable 无故障 cell 相同的 `scientific_outcome_digest` 和 terminal disposition；各 artifact stratum wall-overhead median/p95 的 UCB95 ≤3%/5% |
| G9 | soak | 24 小时 fault soak 无 duplicate/corruption/false completion/manual repair |

Stretch gate：同 scope campaign 的 calls 相对 1,335 下降至少 90%，且 tokens
平均每 Research Run 不超过 100k。它需要把 Attempt 压到至多四 calls，或靠有效 early
stop；在 `12 snapshot calls + 5 calls/Attempt` 的具体方案下，campaign 平均
Attempts 必须至多 2.4。该上限不是对所有 snapshot/call 组合的通式，也不能从
“每 Attempt 5–7 calls”直接推导。Calls 降低本身还不能推出 100k-token gate；若用满 133
calls，平均还必须压到约 7,519 tokens/call（比基线低约 22.2%）。

## 4. Normative Interface contract

### 4.1 允许的入口

```python
class LongTaskRuntime(Protocol):
    def apply(self, command: RuntimeCommand) -> CommandReceipt: ...
    def inspect(self, query: RunQuery) -> ResearchRunSnapshot: ...


class StageContinuation(Protocol):
    def plan(self, request: ContinuationRequest) -> ContinuationPlan: ...


class DecisionRecallRuntimeRead(Protocol):
    def get_admission_authorization(
        self, authorization_id: str
    ) -> DecisionIntentAdmissionProof: ...
    def get_commit_authorization(
        self, authorization_id: str
    ) -> DecisionRecallCommitAuthorizationProof: ...
    def get_intent_phase(self, intent_id: str) -> DecisionRecallPhaseProof: ...
    def get_barrier_read_proof(
        self, run_id: str
    ) -> DecisionIntentBarrierReadProof: ...


class DistillationRuntimeRead(Protocol):
    def get_work_item_profile_artifact_proof(
        self, work_item_id: str
    ) -> WorkItemProfileArtifactProof: ...
    def get_enqueue_obligation_abandoned_proof(
        self, work_item_id: str
    ) -> DistillationEnqueueObligationAbandonedProof: ...
    def get_campaign_assignment_authorization(
        self, run_id: str, activity_id: str
    ) -> DistillationCampaignRuntimeProof: ...
    def get_campaign_barrier_read_proof(
        self, run_id: str
    ) -> CampaignBarrierReadProof: ...
    def get_commit_authorization(
        self, authorization_id: str
    ) -> DistillationCommitAuthorizationProof: ...
    def get_closure_authorization(
        self, authorization_id: str
    ) -> DistillationClosureAuthorizationProof: ...
    def get_terminal_receipt(
        self, receipt_ref: str
    ) -> DistillationTerminalReceiptProof: ...
    def get_run_terminal_failure_receipt(
        self, receipt_ref: str
    ) -> RunTerminalFailureReceipt: ...


class RetentionRuntimeRead(Protocol):
    def get_artifact_erasure_receipt(
        self, receipt_ref: str
    ) -> ArtifactErasureReceiptProof: ...
    def get_index_invalidation_receipt(
        self, receipt_ref: str
    ) -> IndexInvalidationReceiptProof: ...
```

`DecisionRecallRuntimeRead`、`DistillationRuntimeRead` 与 `RetentionRuntimeRead` 是 Runtime control 与 memory
Store 间的 narrow internal read Seams，不是用户 command surface；proof/receipt 都必须
带 canonical payload digest、Run/Activity/generation/fence/control-event identity，并从
Runtime Store read-back。Retention proof 另绑定 target artifact/object generation、
namespace、operation/incident ID 和 terminal erasure/invalidation state；裸 ref/digest
不能作为完成证明。

`DistillationTerminalReceiptRef` 是 Experiment Ledger Completion payload 中仅含
`ref+digest` 的 immutable reference。`DistillationTerminalReceiptProof` 是 Runtime-owned
full strict read model：至少含该 ref/digest、Run/Activity/generation/fence、closed
`dead_letter|cancelled` status、typed cause/evidence identity 和 Runtime event seq；getter
独立 read-back/recompute 后返回，二者禁止同名或相互冒充。

Runtime writer transaction 只提交 authorization/proof，不同步调用 Experiment Ledger。
独立 system Commit Coordinator 在无任何 Store write transaction 时通过上述 read-only
Interface 取得 immutable proof，随后调用 Ledger，再回传 receipt 供 control reconcile。
control 必须能并发服务 getter；任何 Runtime/Ledger SQLite write transaction 内的
cross-store IPC 都被 contract test 禁止。
`get_work_item_profile_artifact_proof()` 在任何 campaign Run 创建前即可读取，但只能
返回 strict、digest-bound view：deterministic handoff/ref ID、Work Item ID、
owner=`DISTILLATION_WORK_ITEM:<work_item_id>`、profile ref/digest、object digest/
generation、Artifact Store event seq、ref=`ACTIVE`、handoff=`PENDING`，以及 exact
current `enqueue_attempt_id/generation/fence/state=IN_FLIGHT`。首次 Ledger insert 只接受该 proof；
`NOT_STARTED`/bare `PENDING` 不授权 enqueue。若 Work Item 已 committed，getter 改为返回
绑定原 enqueue receipt/proof digest 的 typed `BOUND` replay proof，不产生新 authority。
若 current attempt 已 `PROVED_ABSENT` 且 handoff/ref 仍为 `PENDING + ACTIVE`，显式 retry
必须先 append higher-generation/higher-fence attempt 并把 current projection CAS 到新的
`IN_FLIGHT`，getter 才可返回新 proof。它不授权其他 Ledger 或 Runtime transition；
retired/old attempt、`RELEASED`、inactive、
foreign 或 mismatch 不可返回为成功 proof。
`get_campaign_assignment_authorization()` proof 绑定 `MEMORY_DISTILLATION` Run/spec/
manifest ref+digest、exact Work Item/ordinal、owned Activity、current Run version、Activity
generation/fence/state=`AWAITING_ASSIGNMENT`、control-event seq 和 payload digest；只授权
Experiment Ledger append exact Assignment，不授权 activation/dispatch。Ledger Assignment
成功后 Runtime 必须从 memory Store 的反向 proof getter 自己 read-back，再做 activation
或 closure-bind CAS。
两个 barrier-read proof 都内嵌同一个 `TerminalBarrierFreezeProof`，只能在 private
`BeginTerminalBarrier -> FreezeTerminalBarrier` 已把同一 epoch 从 `CLOSING` CAS 到
`FROZEN` 并写入 `TerminalBarrierFrozen`、
`new_work_admission_closed=true`、relevant active authorization 已 resolved 且 current
control event/fence/terminal kind 与 freeze epoch 固定时签发。Store 在一个 read
transaction 返回 per-Run Intent 或 all-status campaign coverage frontier/digest；Runtime
terminal CAS 必须重验 freeze ID/epoch/event/fence/terminal kind 并绑定 coverage。stale
proof、foreign row、任一侧
missing/extra 都进入 `WAITING_INPUT`/closure，而非 terminal。
`RunTerminalFailureReceipt` 专门证明 manifest 已 settled 之后、terminal CAS 之前赢得的
non-work Run failure；它绑定 Run/spec/manifest digest、exact settled-manifest coverage
digest（ordered slot/status/Completion digest；all-completed 只是特例）、failure control event、
closed cause `CONTROL_PLANE_FAILURE|CONTRACT_INTEGRITY_FAILURE|
ARTIFACT_INTEGRITY_FAILURE|RUNTIME_INFRASTRUCTURE_FAILURE`、source incident/evidence refs
和 canonical ID/digest。它不是 Work Completion 的 dead-letter/cancel receipt。

V1 command union：

```python
DriveRun | PauseRun | ResumeRun | CancelRun | AmendBudget | ResolveRun
```

V1 不公开 `ForkRun`，也不公开 `complete_stage`、`progress`、`finalize`、
`write_heartbeat`、store transaction 或 lease mutation。

`ResearchRunSpec = ScientificResearchRunSpec | MemoryDistillationResearchRunSpec` 是
以 `run_kind` 判别的 closed tagged union。两臂只共享 run/workflow/continuation/
interpreter/model/tool/input/Budget/retention 字段，kind-specific validator 在 admission
前 fail closed：

- `SCIENTIFIC` 绑定普通研究 workflow、task/input、full Evaluation Contract 与
  actor-visible `DecisionContractView`，并遵守 Verification/Experience/Recall/
  Distillation Receipt completion contract；
- `MEMORY_DISTILLATION` 绑定可 read-back 的 immutable
  `DistillationCampaignManifest` ref/digest、v1 cardinality=1 Work Item ID/digest、namespace、
  Distillation/Lifecycle policy，以及 Work Item 预先固定的 Campaign Admission Profile
  ref/digest；workflow/continuation、model/tool/Adapter configuration、Budget Envelope、
  retention 与 cardinality 必须由该 profile 确定性展开。它禁止 `OpenExperimentAttempt`，可拥有
  零 Hypothesis/Attempt/Decision Intent；每个 manifest slot 的 deterministic Activity
  初始为 non-claimable/non-dispatchable `AWAITING_ASSIGNMENT`，只有 Runtime 自行
  read-back exact Assignment proof 后的 Run-version/Activity-generation CAS 才能 READY；
- public command 仍是 `DriveRun`；该 kind 的 shared canonical helper 固定
  `admission_key=Work Item ID`，从它派生 versioned `run_id` 与 initial `command_id`，Runtime
  拒绝 caller-chosen alternatives 并以 `UNIQUE(run_kind,admission_key)` 落库；same key/same
  manifest 返回同一 Run，same key/different manifest/profile/config 是 spec-identity
  conflict，caller 只能 read-back/reconcile winner，不能创建第二 Run；
- terminal source `SCIENTIFIC` Run 永远不能因 deferred distillation 新建 Activity。
  它进入 terminal 前，每个 queued receipt 必须 read-back exact Work Item、enqueue
  receipt、handoff=`BOUND` 和 Work-Item-owned ref=`ACTIVE`；该 ref 不计作 source
  Run-owned unsettled claim，且 source terminal 不授权释放它。

Runtime-owned `DistillationCampaignAdmissionProfileV1` 与
`DistillationCampaignManifestV1` 都是 `frozen/extra=forbid` canonical payload。前者的
domain 是 `ai-researcher/distillation-campaign-admission-profile/v1`，字段闭合为
workflow/continuation refs+versions+digests、interpreter-contract bundle、model/tool/
Drafting-Adapter config digests、Budget Envelope、execution/retention policies 和
`cardinality=1`；后者 domain 是
`ai-researcher/distillation-campaign-manifest/v1`，字段闭合为 run kind、namespace/scope、
profile ref/digest、Distillation/Lifecycle policy identities 和唯一 ordered member
`{ordinal:0,work_item_id,work_item_payload_digest,experience_id}`，并禁止 run/command ID、
mutable state 或 spec digest。单一 shared pure helper 实现
`profile + canonical Work Item -> manifest -> ResearchRunSpec` 以及 Work Item ID→admission/
Run/Activity/initial-command IDs；两组 golden vectors覆盖 key order、Unicode、same-input
replay 和 config skew。

该 helper 的 canonical ID table 是两 Store 唯一规范：

| Identity | Domain / projection |
| --- | --- |
| `admission_key` | exact `work_item_id`（不是 caller 字符串或二次 hash） |
| `admission_attempt_id` | `ai-researcher/memory-distillation-admission-attempt/v1` over `{work_item_id,initial_command_id}` |
| `run_id` | `ai-researcher/memory-distillation-run/v1` over `{work_item_id}` |
| `initial_command_id` | `ai-researcher/memory-distillation-initial-command/v1` over `{work_item_id,run_id}` |
| `activity_id` | `ai-researcher/distillation-activity/v2` over `{campaign_run_id,work_item_id}` |
| `assignment_id` | `ai-researcher/distillation-work-assignment/v1` over `{work_item_id,campaign_manifest_ref,campaign_manifest_digest,campaign_run_id,activity_id}` |
| `campaign_profile_artifact_ref_id` | `ai-researcher/distillation-work-item-profile-ref/v1` over `{work_item_id,profile_ref,profile_digest,object_digest,object_generation}` |
| `work_item_profile_handoff_id` | `ai-researcher/distillation-work-item-profile-handoff/v1` over `{work_item_id,campaign_profile_artifact_ref_id,profile_digest,object_generation}` |
| `work_item_profile_enqueue_attempt_id` | `ai-researcher/distillation-work-item-profile-enqueue-attempt/v1` over `{work_item_profile_handoff_id,attempt_generation}` |
| `manifest_temp_ref_id` | `ai-researcher/distillation-manifest-temp-ref/v1` over `{work_item_id,manifest_digest,admission_attempt_id}` |
| `manifest_run_ref_id` | `ai-researcher/distillation-manifest-run-ref/v1` over `{run_id,manifest_digest}` |

除专门以 monotonic `attempt_generation` 区分 append-only enqueue attempt 的上一行外，
所有 base-identity projection 排除 clock、retry ordinal、lease/fence、mutable state、
filesystem path 和 deployment defaults。Runtime 与 memory projector 必须 import 同一 pure module/schema
version 并运行同一 golden-vector file；各自重写 helper 或只比较“看起来相同”的字符串
禁止。profile ref/handoff IDs 还明确排除 handoff state、enqueue attempt/fence、Ledger
receipt、clock 与 filesystem path，避免 retry/BOUND transition 改 identity。

其他 reply-loss-sensitive Runtime IDs 同样固定；authorization ID 排除 proposed/output
payload，projection row 另以 exact payload digest 防 identity cycle：

| Identity | Domain / projection |
| --- | --- |
| `decision_intent_admission_authorization_id` | `ai-researcher/decision-intent-admission-authorization/v1` over `{intent_id,run_id,activity_id,generation,fence,attempt_ordinal,logical_effect_id}` |
| `decision_recall_commit_authorization_id` | `ai-researcher/decision-recall-commit-authorization/v1` over `{intent_id,run_id,activity_id,generation,fence,transition_kind,attempt_ordinal,logical_effect_id}` |
| `run_terminal_failure_receipt_id` | `ai-researcher/run-terminal-failure-receipt/v1` over `{run_id,spec_digest,manifest_digest,exact_settled_manifest_coverage_digest,control_event_seq,cause_code,source_evidence_digest}` |
| `pending_control_id` | `ai-researcher/pending-control/v1` over `{run_id,target_authorization_id,kind,source_identity}`；source identity 是 public command ID 或 authenticated system-failure event ID |
| `pending_control_resolution_id` | `ai-researcher/pending-control-resolution/v1` over `{pending_control_id,target_authorization_id,outcome}` |
| `enqueue_recovery_request_id` | `ai-researcher/distillation-enqueue-recovery-request/v1` over `{experience_id,work_item_id,work_item_payload_digest,handoff_id,artifact_ref_id,enqueue_attempt_id,attempt_generation,attempt_fence}` |
| `enqueue_recovery_proof_id` | `ai-researcher/distillation-enqueue-recovery-proof/v1` over `{recovery_request_id,recovery_request_digest,arm,ledger_frontier,arm_evidence_digest}`；arm evidence 分别是 queued Work Item/receipt/sidecar projection、abandoned receipt/proof projection 或 exact absence coverage digest |
| `enqueue_obligation_abandoned_proof_id` | `ai-researcher/distillation-enqueue-obligation-abandoned/v1` over `{experience_id,work_item_id,work_item_payload_digest,handoff_id,enqueue_attempt_id,attempt_generation,attempt_fence,recovery_request_id,recovery_request_digest,source_run_id,source_activity_id,absence_proof_ref,absence_proof_digest,terminal_control_event_seq,disposition}` |

这些 helper 与上表共用 canonical JSON/versioned hash library 和 golden-vector artifact；
clock、display reason、receipt position、target output bytes 和 later resolution 都排除。
same ID/different immutable payload 是 integrity conflict，exact retry read-back 原 row。

profile artifact 严格走本计划 §5.2 的 `PENDING|BOUND|RELEASED` Work-Item handoff；
普通 no-commit/not-found 不构成 orphan release proof。manifest 另有 admission handoff：
publish 后、`DriveRun` 前由 deterministic initial command/admission attempt 持 temporary
`ACTIVE` ref，Run admission transaction 创建 Run-owned ref 后才能释放 temporary ref。
profile/manifest GC 与 enqueue/admission/reply-loss 的 race tests 必须证明 bytes 不会在
任一 handoff window 消失。

`MEMORY_DISTILLATION` Run 的 terminal predicate 枚举 manifest exact ordered set，而
不是现有 assignment 集：每个 slot 恰有一项 matching Assignment/Activity/terminal
`DistillationWorkCompletion`，Activity terminal state 必须与 Completion 精确对应
`COMMITTED/completed | FAILED/dead_letter | CANCELLED/cancelled`，无 foreign item，再加公共 record-closure 与
operational-settlement barriers。terminal predicate 按顺序互斥：任一 dead-letter ->
`FAILED/DEAD_LETTER_PRESENT`；否则 all-completed -> `COMPLETED/ALL_COMPLETED`，但独立
non-work failure 在 terminal CAS 前赢则 `FAILED/RUNTIME_FAILURE_AFTER_WORK`；否则至少
一个 cancelled -> `CANCELLED/CANCELLED`，但该 failure 先赢则
`FAILED/RUNTIME_FAILURE_AFTER_CLOSURE`。failure authorization 与 CancelRun 以同一
Run-version/control-event CAS 决定 `FAILING`/`CANCELLING` precedence。它不伪造科学记录。

`lifecycle_status` 是
`NEW | RUNNING | WAITING_RETRY | WAITING_INPUT | PAUSING | PAUSED |
CANCELLING | FAILING | COMPLETED | FAILED | CANCELLED`；`verify/record` 只出现在独立的
`current_stage`，不是 lifecycle state。`COMPLETED` 的
terminal outcome 按 run kind 区分：只有 `SCIENTIFIC + COMPLETED` 必须且只能携带
`scientific_outcome = VALID_PASS | VALID_FAIL | EXHAUSTED_NO_PASS`；
`MEMORY_DISTILLATION` 禁止 scientific outcome，并使用
`distillation_outcome = ALL_COMPLETED | DEAD_LETTER_PRESENT | CANCELLED |
RUNTIME_FAILURE_AFTER_WORK | RUNTIME_FAILURE_AFTER_CLOSURE` 与上述
lifecycle mapping。invalid 或不完整证据不能伪装成 completed negative。Terminal
lifecycle state 不可逆。
任何 `COMPLETED|FAILED|CANCELLED` transition 必须先通过 record-closure barrier：
每个已预分配 Run-owned Decision Intent 有唯一 terminal Recall Decision Outcome，
每个已存在 completion-required Experience 有唯一 Experience Distillation Receipt；
失败/取消不伪造从未存在的 Intent、Attempt、Verification 或 Experience。
该 receipt 可为 queued、deferred、not-required，或由 exact Runtime abandonment proof
授权且已独立 read-back 的 `abandoned_before_enqueue`；最后一类只关闭从未落账的
pre-enqueue obligation，不创建 Work Item。
`FAILING/CANCELLING` 在该 barrier 未完成时仍是 non-terminal。随后还必须通过独立的
operational settlement barrier：所有 physical invocation 已 final known/not-executed 或由
operator 显式 `ABANDONED_WORST_CASE`、所有 reservation 已 settle、所有 owned
execution（task/thread、process group、container）已确认不存在或完成 reconcile，
Run-scoped lease/role assignment 已释放，且 Run-owned artifact staging/
materialization claim、artifact-filesystem mutation actor 与 Snapshot Build Claim
已 publish/release/revoke/exit/reconcile 为 non-active。共享 launcher/control/
executor service process 不属于单个 Run，
不要求退出。否则保持 `WAITING_INPUT`；科学
记录完整不能绕过该 barrier。

对每个 `queued_for_comparison` Receipt，record-closure 还把 Ledger Work Item/
enqueue receipt 的 ref ID/digest 与
`DistillationRuntimeRead.get_work_item_profile_artifact_proof()` 双向核对；只有
handoff=`BOUND` 且 ref=`ACTIVE` 才满足。缺失、`PENDING`、foreign 或 `RELEASED` 时继续
reconcile/`WAITING_INPUT`，不能 terminal。成功后可 settle source-owned staging/ref，
但 Work-Item-owned ref 不在 source Run operational denominator 内。

record-closure 先 reconcile 每个 `REGISTERING/CONTEXT_COMMITTING/
OUTCOME_COMMITTING` attempt。admission success 才把 exact Ledger-backed Intent 放入
closure denominator；admission no-commit 退休且 Outcome=0。Ledger Intent 没有 matching
Runtime OPEN reconciliation 是 integrity `WAITING_INPUT`。随后所有 OPEN+ Intent 只能经
normal/closure Outcome authorization 关闭，不能由 barrier 直接写 row。

#### Decision Recall append arbitration

完整 `DecisionIntentProposal` 先发布/read-back；Runtime 以 Run version + control event
seq + Activity generation/fence CAS 创建 `REGISTERING` 和 admission authorization，
`DecisionIntentAdmissionProof` 是其 Store-facing view。Ledger success 才推进 `OPEN`；
journaled no-commit 退休 ghost registration。unresolved REGISTERING 禁止 retrieval/actor，
cancel/failure 进入同一 pending arbitration：success 后关闭真实 Intent，no-commit 后不
伪造 Outcome。

Runtime 为每个已注册 Intent 投影 closed phase：`OPEN | CONTEXT_COMMITTING |
CONTEXT_COMMITTED | OUTCOME_COMMITTING | OUTCOME_COMMITTED`。只有 control role 能以
Run version + control event seq + Activity generation/fence CAS 发 single-use
authorization。closed tagged union 是
`DecisionRecallAppendAuthorization = DecisionIntentAdmissionAuthorization |
DecisionRecallCommitAuthorization`；前者只允许 Intent admission，后者只允许 Context/
Outcome commit。两种 subtype 共同绑定
`APPEND_INTENT | APPEND_CONTEXT | APPEND_OUTCOME`、
`ADMISSION | NORMAL | RUNTIME_CLOSURE`、exact Intent/optional Context、expected Ledger record ID/
payload digest 与 Runtime proposal artifact ref/digest。public getter 返回
content-digested proof，memory Store 三个 append
transaction 必须自行 read-back，caller bool/旧 fence 不构成授权。
合法 pair 只允许 `APPEND_INTENT/ADMISSION`、`APPEND_CONTEXT/NORMAL`、
`APPEND_OUTCOME/NORMAL|RUNTIME_CLOSURE`；issuer、proof model 和 Store validator 都用同一
closed matrix，非法 cross-product 零 Ledger write。

Context grant 只从 `OPEN`；normal Outcome grant 只从 `CONTEXT_COMMITTED`，或 registered
not-requested/typed blocked 从 `OPEN`。Ledger receipt 成功后 Runtime read-back 并推进
committed phase；只有 proved no-commit 才可 retire authorization。unresolved attempt
期间不得第二次 grant，reply loss/restart 以相同 authorization/expected IDs reconcile。

cancel/failure-first CAS 撤销 normal fence，只能创建 mutually-exclusive closure Outcome
authorization。grant-first 时控制原因返回/记录 `PENDING_AFTER_ARBITRATION`，不提前
revoke：Context success 后从 `CONTEXT_COMMITTED` 补 closure Outcome，Context no-commit
从 `OPEN` 补；Outcome success 保留 immutable winner，Outcome no-commit 才补 closure。
pending cancel/ordinary closure failure 由同一 control-event CAS 选 primary kind：
cancel-first 只抑制 duplicate/cancellation-induced failure，failure-first 令 later Cancel
成为 closure-help/no-op；独立 integrity/contract/infrastructure failure 另存 secondary
evidence。Decision Recall success/no-commit 必须先 reconcile exact Intent phase，再写或
保留真实的 typed closure Outcome，并按 scientific Run 的普通 failure contract 进入
`FAILING`；它绝不使用 memory-distillation-only 的 outcome 或 dead-letter。record-closure barrier 必须先
reconcile `*_COMMITTING`，不能直接写 Ledger 猜谁先赢。

写 pending control 的同一 transaction 必须置 Run `new_work_admission_closed=true`。
所有 claim、Effect/Invocation preparation、Intent admission、Context grant、normal Outcome
grant SQL predicate 都要求该值为 false；pending 期间唯一例外是 exact active
authorization 的 Ledger success/no-commit reconcile。其他已经 in-flight 的 normal
semantic commit/Activity-advance 也必须拒绝；late receipt capture、evidence inbox、budget
settlement、termination/reconcile 仍允许，但不得选择为新 semantic state。closure grant
只能在该 attempt resolved 后发生。post-pending 并发 claims/grants/parallel Effect commit
1,000-race 的新增或 normal committed work 必须为 0。

pending gate close 不能代替 terminal barrier freeze。所有 normal-success、failure、cancel
terminalization 都必须先经 private `BeginTerminalBarrier` CAS：同一 transaction 关闭 gate、
分配递增 epoch、写 `TerminalBarrierClosing` 并固定 candidate terminal kind、Run version、
control-event seq 与 Activity fences。`CLOSING` 期间只允许 exact in-flight authorization
reconcile 和该 epoch/manifest-bound 的 Runtime closure Intent Outcome、campaign system
Assignment/Completion；normal assignment、claim/admission/normal authorization 为 0。
closure records 全部 read-back 且 relevant authorization 全部 terminal 后，第二个
`FreezeTerminalBarrier` CAS 以 closure-projection digest 将同一 epoch 置 `FROZEN` 并写
`TerminalBarrierFrozen`。此后连 closure Assignment/Completion 新写也为 0，只允许
read-back/receipt/settlement，Runtime 才能签发内嵌该 freeze 的 barrier-read proof。
terminal cause、event、fence、closure projection 任一变化都必须推进 epoch 并重取
coverage；terminal CAS 逐字段重验同一 freeze 和 coverage digests。

#### Memory-distillation commit arbitration

Executor only publishes a content-addressed `DistillationProposal`; it has no
Experiment Ledger writer. The independent Commit Coordinator deterministically
prepares/publishes `DistillationCommitPlan` with exact canonical output bytes,
IDs and digests. Runtime control read-backs proposal, plan and exact Assignment,
then one control-store transaction CASes Run version + Activity
generation/fence `RUNNING -> COMMITTING` and appends a unique
`DistillationCommitAuthorization`. Its stable ID includes Assignment,
Run/Activity, generation/fence, commit-attempt ordinal, and logical Effect; its
immutable payload additionally pins proposal ref/digest, commit-plan ref/digest,
affected expected lifecycle heads, and expected Batch/Report IDs/digests. Same ID/different payload
is an integrity conflict.

The memory Store returns exactly one of two digest-bound results:

- atomic success: plan-derived Knowledge, Batch, Work Disposition, Report, and
  authorization-derived `completed`
  Completion commit together; Runtime read-backs all receipts, marks the
  authorization `COMMITTED`, and commits Effect/Activity;
- `NO_COMMIT_CONFLICT`: before any semantic write, the Store journals closed kind
  `LIFECYCLE_HEAD_STALE|RETENTION_REVOKED`；前者绑定 exact expected/observed heads，后者
  绑定 current retention frontier/set 与 sorted reachable blocked targets。两项同时命中时
  必须选择 `RETENTION_REVOKED`，head-delta arm canonical null；只命中 head stale 时所有
  retention fields canonical null。Runtime read-backs that receipt and CASes
  the authorization to `RETIRED_NO_COMMIT`; without a pending control intent it
  increments generation/fence；head stale 从 current head fresh propose，retention revoked
  则先取 clean Snapshot/source 再 propose，或按 pinned policy typed closure，绝不重用 plan。

`GRANTED` is an exclusive pending arbitration state, not an irreversible claim
that lifecycle CAS will succeed. During it, CancelRun/fatal failure appends a
durable `PENDING_AFTER_ARBITRATION` intent and does not revoke the attempt.
Success resolves cancel as `TOO_LATE_COMMITTED`; no-commit retirement applies
the pending cancel/failure in the same CAS before any reauthorization. The same
Run-version/control-event CAS chooses exactly one primary pending kind:
cancel-first suppresses only duplicate/cancellation-induced failure; failure-first
makes a later Cancel closure-help/no-op. Independently authenticated integrity/
contract/infrastructure failure remains secondary evidence and is re-evaluated
after arbitration. Success with applicable failure preserves Completion then uses
`RUNTIME_FAILURE_AFTER_WORK`; no-commit dead-letters before retry. A
cancel/failure CAS that wins before authorization creates a mutually exclusive
`DistillationClosureAuthorization`, binding exact terminal receipt ref/digest,
and permits only a `cancelled/dead_letter` Completion. Unresolved or ambiguous
authorization keeps the Activity `COMMITTING` and the Run in its prior non-terminal
lifecycle, or moves the Run to `WAITING_INPUT` on integrity ambiguity; it cannot
be terminally closed by guessing.

### 4.2 Contract tests

`tests/test_runtime/test_long_task_interface.py` 必须证明：

- 同一 `command_id + payload` 重放得到 deterministic `DUPLICATE` receipt，并
  引用原 `ACCEPTED` 的 accepted version/event sequence；
- 同一 `command_id` 不同 payload 返回 `CommandIdentityConflict`；
- 同一 `run_id` 不同 spec 返回 `RunIdentityConflict`；
- 除 monotonic `CancelRun` 外，mutating command 的 `expected_version` 过期时
  返回 `VersionConflict`；
- terminal Research Run 再次 `DriveRun` 不 dispatch 新 Activity；
- terminal source `SCIENTIFIC` Run 的 queued distillation item 只能由独立
  `MEMORY_DISTILLATION` Run/Activity 消费；start-after-reply-loss、重复 projector 和
  assignment race 不产生第二 Run/Activity/Assignment；
- v1 manifest cardinality 必须为 1；100 concurrent projectors 对同一 oldest item
  派生同一 manifest/Run/Activity/Assignment，multi-item manifest admission fail closed；
- `MEMORY_DISTILLATION` Run 未覆盖 manifest 全部 Work Item 的 assignment/activity/
  terminal completion 时
  不得 terminal，且其 workflow 不能打开 Experiment Attempt；missing assignment/
  completion 或 foreign item 也不得以空/partial set 通过；
- campaign Activity 在 Assignment proof CAS 前不可 claim/dispatch；assignment append、
  activation、CancelRun/terminal races 中 stale proof 新 Effect=0；
- campaign cancel/fail closure 覆盖 manifest 每个 slot，terminal 后
  `assigned-incomplete=0`，kind-specific outcome 与 lifecycle 精确匹配；all work
  completed 后的 permanent non-work failure 使用 `RUNTIME_FAILURE_AFTER_WORK`，不篡改
  Work Completion；零 dead-letter 且含 cancelled 的 settled coverage 后独立 failure 使用
  `RUNTIME_FAILURE_AFTER_CLOSURE`，同样不篡改 Completion；
- missing Assignment 的 closure proof→append/read-back→closure-bind CAS 必须直接
  `AWAITING_ASSIGNMENT->CLOSING`、READY/dispatch=0；Completion read-back 后才 terminal
  Activity。每个 crash seam 可恢复，Activity 仍 awaiting/ready/closing 或 Completion/state
  mismatch 时 terminal Run=0；
- normal-success（无 pending control）也必须
  `BeginTerminalBarrier(CLOSING) -> closure/reconcile -> FreezeTerminalBarrier(FROZEN)`；
  freeze 后并发 claim、Intent admission、normal authorization、Assignment/Completion grant
  各 1,000 次新增均为 0，terminal CAS 只接受同 epoch/event/fence/closure digest；cause 或
  fence 改变后旧 coverage proof 必须 stale；
- all-status campaign coverage 在同一 fixed frontier 枚举 completed/incomplete 及 foreign
  Assignment/Completion；注入 missing、extra、duplicate projection 或已完成 foreign row
  均使 terminal=0，incomplete-only scan 不得替代；
- `RUNTIME_FAILURE_AFTER_WORK|RUNTIME_FAILURE_AFTER_CLOSURE` 必须且只能绑定可
  read-back `RunTerminalFailureReceipt`，ordered slot/status/Completion coverage、cause、
  source digest exact；missing/foreign/tampered/duplicate receipt 与非该 outcome 伪绑
  全部拒绝；
- `DistillationCommitAuthorization`/CancelRun/fatal failure 的 3-way 1,000 次 race：
  unresolved attempt 返回 `PENDING_AFTER_ARBITRATION` 且同一 CAS 只选一个 pending kind；
  Ledger success 分别得到 `TOO_LATE_COMMITTED + ALL_COMPLETED` 或 completed Work
  Completion 后 `FAILED/RUNTIME_FAILURE_AFTER_WORK`；NO_COMMIT_CONFLICT 分别 cancel 或
  dead-letter before retry；cancel/failure-first authorization=0，precedence/replay 稳定；
- authorization grant -> cancel primary pending -> independent integrity failure 的排序：
  failure evidence 不丢；Ledger success 为 completed Work +
  `FAILED/RUNTIME_FAILURE_AFTER_WORK`，no-commit 为 failure/dead-letter before retry；
- zero-dead-letter + cancelled manifest coverage settle 与独立 failure/terminal CAS 的 1,000-race：
  failure-first 或 terminal 前 failure 均保留 immutable Completion，并得到
  `FAILED/RUNTIME_FAILURE_AFTER_CLOSURE`；terminal-CANCELLED 先提交则 terminal immutable；
- atomic Work Completion success 后、Run terminal CAS 前注入 CancelRun：100% 返回
  `TOO_LATE_COMMITTED`、CANCELLING transitions=0，最终
  `COMPLETED/ALL_COMPLETED`；reply-loss/replay read-back 同一 Completion；
- 每个 pending command 恰有一个 append-only resolution；`inspect(command_id)` 可读，
  duplicate apply receipt bytes 不随 resolution 改变，foreign auth/second resolution 拒绝；
- unresolved authorization 下 deterministic system-failure pending control 不要求伪造
  public command ID；其 authenticated source event/ref/digest 可回读、exact replay 同一
  resolution，command/system 两组 source fields 混填或双 resolution 拒绝；
- failure-primary 后 1,000 个 concurrent late Cancel 各有 stable follower/control+command
  resolution=`CLOSURE_ASSIST_NOOP`，primary count 始终 1；reply loss/exact replay 不丢
  inspect join，也不产生第二 failure/cancel primary；
- Context append vs closure Outcome、normal Outcome vs cancel/failure 各做 1,000 次 race：
  每个 Intent 只有一条合法 phase path、一个 unresolved authorization、一个 terminal
  Outcome；authorization-first success/no-commit 按协议仲裁，closure-first 后 stale Context/
  normal Outcome append=0，crash/reply-loss 可用 same IDs 收敛；
- Intent proposal/registering/Ledger append/Runtime OPEN 每个 crash seam 与 cancel/failure
  1,000-race：Ledger success 后 Intent 必进入 closure denominator；typed no-commit 后 phase
  只能 retired 且 Outcome=0；stale/retired admission append=0；不存在 Ledger-only Intent、
  ghost OPEN 或重复 admission；
- fixed-frontier Intent coverage 必须双向覆盖所有 Ledger Intent/admission metadata 与 Runtime
  `REGISTERING/OPEN+` projection；注入 Ledger-only orphan、Runtime-only ghost、stale frontier
  或 coverage digest swap 均使 terminal=0；
- cancel/failure 在 Decision Intent 预分配后、actor/Outcome 前注入时，Run 先停在
  pending arbitration 或 `CANCELLING/FAILING`；Context 尚未提交的 REQUIRED Intent 只补
  唯一 `cancelled_before_recall/cancelled` 或 `failed_before_recall/actor_failed` Outcome；
  registered-not-requested 在 actor 前关闭仍用 `not_requested + cancelled|actor_failed`；
  Context 已存在时 Runtime 为每张 card 写 exact closure disposition；已有
  completion-required Experience 也先补唯一 Receipt，随后才可 terminal；
- paused Research Run 不能被 `DriveRun` 静默恢复；
- `WAITING_INPUT` 只能由绑定 `wait_id` 的 typed `ResolveRun` 或 `CancelRun`
  离开；confirmed-executed/not-executed/abandon/retry-risk disposition 可审计；
- `ResolveRun` 可引用已恢复的 credential/provider availability，但不得携带 secret
  或改变 pinned workflow/model/tool/policy/contract digests；行为配置变化必须新建
  Research Run；
- stale/duplicate/conflicting resolution 分别得到 deterministic receipt/error；
- command precedence 固定为 authenticate/protocol → existing command-ID lookup
  （same payload=`DUPLICATE`，different payload=`CommandIdentityConflict`）→
  immutable Run identity/terminal noop → current incident/admission gate；incident
  在 commit/reply 之间出现时，重试仍返回原 commit 的 `DUPLICATE`；new
  `CancelRun` bypass incident 且保持 monotonic，其他 matching existing-Run
  mutation 才返回 `IncidentFenced`，`inspect` 仍可用；
- command payload 若含 credential、token 或 secret field 必须拒绝；
- `ResolveRun` 与迟到 worker receipt 的 race 只允许一个 version/fence 获胜；
- wait record 持久化 pending pause/cancel/ordinary intent；resolution 只能进入与
  intent 一致的 `PAUSED/CANCELLED/RUNNING/FAILED`，不能把 pause 误恢复成 running；
- `apply(DriveRun)` 在 durable accept 后返回，不在 caller thread 执行 blocking
  Stage Adapter；
- `apply/inspect` 只通过 permission-checked local Unix socket 调一个 supervised
  control role；CLI/Web/executor 不直接打开 authoritative SQLite write
  transaction。Control handshake/response 在 accept 前不可用时返回 closed-union
  `RuntimeUnavailable`；该 error 不表示 accepted，caller 可用同 command ID 重试。
  Control commit 后 reply 前 crash，command replay 得到 `DUPLICATE`；
- `DriveRun` 在 accept 前持久化/验证 content-addressed workflow definition、
  continuation policy 和所需 Adapter-contract artifacts；spec 绑定 ref/version/
  digest，resolver 不得回退到 current deployed default；
- `CommandReceipt` 只表示 accepted/duplicate/noop，不包含或暗示 Activity result；
- `inspect(after_event_seq=n)` 返回同一 projection 和严格大于 `n` 的事件；
- Interface error 的封闭 v1 union 是 `RunIdentityConflict |
  CommandIdentityConflict | VersionConflict | InvalidTransition |
  CommitArbitrationBusy | ContractViolation | RunNotFound | AdmissionClosed | IncidentFenced |
  CursorAhead | InvalidQuery | RuntimeUnavailable`；LLM/tool/process 的预期失败
  进入 snapshot；
- public import 不产生文件、网络、模型、Chroma 或环境修改副作用；
- process-cold import p95 < 200ms：固定 CI runner 上至少 1,000 个 fresh Python
  processes，每个进程在计时前未 import project package；计时只含进程内第一次
  import（不含 interpreter spawn），不 flush OS page cache，并报告机器/Python、
  全部 raw samples 与 nearest-rank p95。

`CommandReceipt.disposition` 是闭合集合：`ACCEPTED | DUPLICATE |
TERMINAL_NOOP | PENDING_AFTER_ARBITRATION | TOO_LATE_COMMITTED`，并返回 `command_id`、payload digest、run ID、accepted version
和 event sequence。Identity/version/transition/contract conflicts 是 typed errors，
不伪装成 accepted receipt。`CancelRun` 是单调幂等的紧急控制命令：除下述 logical-
commit/unresolved-authorization 例外，run 尚非 terminal 时即使 UI observed version 已旧
也可原子进入 `CANCELLING` 并 revoke 当前 fence；terminal run 返回
`TERMINAL_NOOP`。singleton memory campaign 有
exact manifest 全部 Work Completion=`completed`、但 terminal barrier 尚未投影完成时，
CancelRun 直接返回 `TOO_LATE_COMMITTED`，不得进入 CANCELLING，并继续收敛到
`COMPLETED/ALL_COMPLETED`；若 independent non-work failure 已先 latch/applicable，Cancel
仅 closure-assist/no-op，最终是 `FAILED/RUNTIME_FAILURE_AFTER_WORK`。singleton memory campaign 有
unresolved `DistillationCommitAuthorization` 时，CancelRun 返回
`PENDING_AFTER_ARBITRATION` 并持久化 cancel intent，但保持 COMMITTING 且不 revoke
attempt；这里是 campaign Activity 保持 `COMMITTING`，Run 保持先前 non-terminal
lifecycle。Ledger success 后发布 `TOO_LATE_COMMITTED` resolution，NO_COMMIT_CONFLICT
则 retire authorization 并在任何 retry 前进入 CANCELLING。任一 unresolved
Intent admission authorization 或 `DecisionRecallCommitAuthorization` 也返回
`PENDING_AFTER_ARBITRATION`，保持当前 Intent `REGISTERING|*_COMMITTING`，待 exact
Intent/Context/Outcome success/no-commit reconcile 后应用
closure；其他控制命令仍要求
`expected_version`。

每个 `pending_control_id` 只追加一个 `PendingControlResolved`，不修改原 public
receipt。`pending_control_kind=COMMAND_CANCEL|SYSTEM_FAILURE`：前者绑定 original
command/payload，后者绑定 deterministic authenticated system-failure event/ref/digest；
两者都绑定 Run、target authorization ID/digest、resolution event seq 和 closed outcome `TOO_LATE_COMMITTED|CANCELLATION_APPLIED|
FAILURE_APPLIED|CLOSURE_ASSIST_NOOP`。`inspect` 支持 optional command-ID filter 并返回该
resolution；exact `apply` replay 始终返回原 command 的 deterministic `DUPLICATE`，不会
因后来 resolution 改 bytes。
同一 authorization 由 Run/control-event CAS 选恰一 `PRIMARY`，但允许多个 audited
`FOLLOWER`。failure-first 后来的 Cancel 创建自己的 command-backed follower，并可在同一
transaction 解析为 `CLOSURE_ASSIST_NOOP`；cancel-first 后来的独立 system failure 是
保留 source evidence 的 follower，待 authorization outcome 后按真实 failure 解析。每个
public `PENDING_AFTER_ARBITRATION` receipt 因而都有自己的 inspect join，followers 永不
改写 primary precedence。

`inspect()` 在一个 read transaction 中返回 `projection_version=v`、
`last_event_seq=m`，且 projection 声明 `applied_through_event_seq=m`；pagination
只返回 `cursor < event_seq ≤ m` 的有序 events，并含 `next_cursor`/`has_more`。
Run version `v` 与 event sequence `m` 独立，不能假设一 transition 只有一 event。
V1 不 prune authoritative events；cursor ahead of `m` 返回 typed `CursorAhead`，
limit 无效返回 `InvalidQuery`。

### 4.3 Dependency rule

用静态测试扫描 `run_infer_plan.py`、`run_infer_idea.py` 和
`web_ai_researcher.py`，并递归解析它们在 repository 内可达的 thin caller
Adapters/import graph；不能只检查三个 root files：

- 只允许 import `long_task.py` 中的公开 Interface/类型或 thin caller Adapter；
- 禁止直接 import `_journal.py`、`_effects.py`、`MasterRuntime`、Supervisor、
  heartbeat/state JSON writers；
- package `runtime/__init__.py` 不再 re-export Implementation helper；
- provided/reference workflow Adapter 必须通过同一 contract suite。
- 从任一 application root 到 `MasterRuntime`、Supervisor、legacy lifecycle writer
  或 `_journal/_effects/_control_server/worker/launcher` 的 transitive path 数量必须为 0；测试输出完整
  reachable-edge manifest，dynamic import 必须来自显式 allowlist 且解析到
  `long_task.py` public Interface。

`launcher.py` 是 supervisor-facing operational Interface；`worker.py` 与
`_control_server.py` 是 Long-Task Runtime Module 的私有 Implementation，可以
依赖 `_journal/_effects/_budget`。应用代码不得 import 它们或调用 coordinator。

## 5. Durable store contract

### 5.1 文件与职责

新增：

```text
research_agent/runtime/
  long_task.py
  stage_continuation.py
  _journal.py
  _effects.py
  _distillation_commit.py
  _artifacts.py
  _budget.py
  launcher.py
  _control_server.py
  worker.py
  adapters/
    stages.py
    process.py
    verification.py
deployment/
  ai-researcher-worker.service.example
  com.ai-researcher.worker.plist.example
```

不要新建 catch-all `models.py/state.py/status.py`。command/query/snapshot 类型
与 `long_task.py` 的 Seam 共置，Continuation 类型与
`stage_continuation.py` 共置。

### 5.2 SQLite settings

`SQLiteRuntimeStore` 初始化必须显式验证：

- `PRAGMA journal_mode=WAL`；
- `PRAGMA foreign_keys=ON`；
- authoritative transition 使用 `PRAGMA synchronous=FULL`；
- busy timeout 是有界值，并将耗尽分类为 typed transient failure；
- schema version 与 replay version 兼容；
- transaction 使用参数化 SQL，不依赖进程内锁保证正确性。
- 只有 supervised control role 可打开 authoritative write transaction；CLI/Web/
  executor 全部通过 authenticated local IPC；control 先取 process-shared advisory
  writer gate，并发布 owner marker（control ID、PID/start time、transaction ID/
  kind、monotonic acquisition）；SQLite 仍是 safety authority；
- write transaction 除 SQLite commit I/O 外禁止 IPC/artifact/external/model I/O，
  hard hold ceiling=2 秒。Marker 超界时 launcher 重验 exact control child，bounded
  TERM/KILL、等 kernel gate release、重启 control，再由同 command/transition ID
  重试；CLI/Web/executor 永远不会因 DB lock 被 signal。

`InMemoryRuntimeStore` 和 `SQLiteRuntimeStore` 跑完全相同的 store contract。
SQLite 独有的 WAL、busy、磁盘、进程 takeover 测试另列。

最小 schema 必须分别投影 `runtime_effects` 与 `runtime_invocations`，不能把多次
物理调用覆盖在一个 logical effect row 上；`runtime_timers` 也必须是可 claim 的
独立 durable row。每个 invocation row 记录 request/Adapter digests、worker
owner/epoch、reservation、dispatch state、receipt/ambiguity 与 settlement；每个
timer row 记录 stable identity、due time、claim owner/epoch/expiry 与
`SCHEDULED|CLAIMED|FIRED|CANCELLED`。
`runtime_runs`/snapshot projection 必须包含 durable
`admission_key TEXT NOT NULL` 与 `UNIQUE(run_kind, admission_key)`，以及 durable
`new_work_admission_closed BOOLEAN NOT NULL`、首次关闭它的 nullable source event/kind，
以及 nullable `terminal_barrier_epoch/terminal_barrier_state/
terminal_barrier_begin_event_seq/terminal_barrier_freeze_id/
terminal_barrier_freeze_event_seq/terminal_barrier_kind/
terminal_barrier_closure_projection_digest/terminal_barrier_payload_digest`；state 闭集
`CLOSING|FROZEN`，freeze identity 在 coverage/terminalization 时必须全非 null，epoch 单调。
所有 new-work predicate、proof
getter 与 replay validator 共同检查，不能只靠 coordinator 内存 flag；pending source
event 与 terminal freeze 是两个不同投影，普通成功允许前者为 null、后者必非 null。
`runtime_pending_controls` 投影 `pending_control_id PK, run_id,
target_authorization_id, target_authorization_digest, role CHECK(PRIMARY/FOLLOWER),
pending_control_kind CHECK(COMMAND_CANCEL/SYSTEM_FAILURE), nullable
command_id/command_payload_digest, nullable system_failure_event_ref/
system_failure_event_digest, status CHECK(OPEN/RESOLVED), event_seq, payload_digest`；两组
source fields iff/mutually-exclusive，`command_id` 非 null时 UNIQUE，并建立 partial
`UNIQUE(target_authorization_id) WHERE role='PRIMARY'`。pending event 与 row 同 transaction，
crash replay 可直接证明 primary cardinality，不靠全 journal 猜测。
`runtime_pending_control_resolutions` 投影 `resolution_id PK, pending_control_id UNIQUE FK,
pending_control_kind, nullable command_id/command_payload_digest, nullable
system_failure_event_ref/system_failure_event_digest, run_id, target_authorization_id,
target_authorization_digest, outcome, event_seq, payload_digest`；kind 的两组 source fields
iff/mutually-exclusive；outcome 闭集为
`TOO_LATE_COMMITTED|CANCELLATION_APPLIED|FAILURE_APPLIED|CLOSURE_ASSIST_NOOP`。它是
append-only event projection；public command subset 可由 `inspect(command_id=...)`
read-back；resolution transaction 同时 CAS pending control `OPEN -> RESOLVED`，same
pending control 不得出现第二 resolution。
`runtime_run_terminal_failure_receipts` 投影 `receipt_id PK, run_id UNIQUE,
spec_digest, manifest_digest, exact_settled_manifest_coverage_digest, control_event_seq,
cause_code, source_evidence_ref, source_evidence_digest, payload_digest`；cause 使用上列
closed union。Run projection 的 nullable `terminal_failure_receipt_ref/digest` 必须 iff
`lifecycle=FAILED && distillation_outcome in
{RUNTIME_FAILURE_AFTER_WORK,RUNTIME_FAILURE_AFTER_CLOSURE}` 非 null且由 getter
read-back exact equality；其他 outcome/lifecycle 禁止。same semantic cause exact replay
返回同 receipt，foreign/missing/tampered receipt 阻止 terminal transition。
`runtime_activities` 的 closed state 另含 campaign-only `AWAITING_ASSIGNMENT` 与
nonclaimable `CLOSING`；两状态
claim/lease/effect-preparation SQL predicate 一律排除。其 assignment ID/digest 初始
null，只有验证 manifest member + Ledger Assignment proof 的 system-control transition
可在同一 transaction 绑定两者。normal activation CAS 到 READY；若 pending cancel/fail
closure 已赢，system-control closure-bind CAS 直接
`AWAITING_ASSIGNMENT -> CLOSING` 并 grant closure authorization，绝不经过 READY。已有
`READY|WAITING_RETRY` 在 fence revoke 后也进 CLOSING。Ledger terminal Completion
read-back 后才可 `CLOSING -> CANCELLED|FAILED`；普通 worker/Adapter 无上述权限。
`runtime_decision_recall_phases` 至少投影 `intent_id PK, run_id, activity_id,
activity_generation, fence, phase, context_id, outcome_id, active_authorization_id,
pending_control_kind, last_event_seq, payload_digest`；phase 闭集为
`REGISTERING|REGISTRATION_RETIRED|OPEN|CONTEXT_COMMITTING|CONTEXT_COMMITTED|
OUTCOME_COMMITTING|OUTCOME_COMMITTED`；只有 Ledger Intent receipt 已 read-back 才可
`REGISTERING -> OPEN`，typed no-commit 只可到 `REGISTRATION_RETIRED`。
`runtime_decision_recall_append_authorizations` 是上述 closed tagged union 的唯一投影，
至少包含 `authorization_id PK, authorization_kind, intent_id, run_id, activity_id,
activity_generation, fence, transition_kind,
authority_kind, expected_record_id, expected_payload_digest, context_id,
proposal_ref, proposal_digest, planner_input_ref, planner_input_digest,
blocked_source_proof_ref, blocked_source_proof_digest,
closure_event_ref, closure_event_digest, terminal_evidence_kind,
terminal_evidence_ref, terminal_evidence_digest, status, ledger_receipt_ref,
ledger_receipt_digest, ledger_no_commit_ref, ledger_no_commit_digest, event_seq,
payload_digest`；`authorization_kind CHECK(ADMISSION/COMMIT)`，且 subtype CHECK 必须为
`ADMISSION -> APPEND_INTENT + authority_kind=ADMISSION`、
`COMMIT -> APPEND_CONTEXT + NORMAL | APPEND_OUTCOME + NORMAL|RUNTIME_CLOSURE`。
status 闭集 `GRANTED|COMMITTED|RETIRED_NO_COMMIT`，success receipt 与
no-commit receipt 两组 fields mutually exclusive。同一 Intent 只许一个 active authorization；
normal/closure grant、pending cancel/failure 与 phase update 均由单个 control-store CAS
校验。若 actor 已 invoked，Outcome authorization 必须从 model Effect request read-back
同一 `DecisionPlannerMemoryInputArtifact` ref/digest；未 invoked 时两字段必须 null。
`get_admission_authorization()` 只可返回 ADMISSION row 的
`DecisionIntentAdmissionProof`，`get_commit_authorization()` 只可返回 COMMIT row 的
`DecisionRecallCommitAuthorizationProof`；subtype 不符必须 fail closed。open/replay
validator 双向核对
phase、authorization event/projection、Ledger receipt 和 expected content IDs。
`blocked_source_proof_ref/digest` 必须 iff proposed Outcome source=`blocked` 同时非 null，
并由 Runtime Artifact getter read-back exact `DecisionRecallBlockedProof`；它们必须与
Outcome proposal/canonical Outcome 相等，且该分支 generic terminal-evidence triple 全
null。其他 source status 禁止 blocked proof fields。仅
`cancelled_before_recall|failed_before_recall` 允许 closure-event fields，且必须逐字节等于
terminal-evidence ref/digest，kind 分别为 `CANCEL_EVENT|RUNTIME_FAILURE`；其余 source
status closure-event fields 全 null。
`terminal_evidence_kind` 是 closed
`MODEL_EFFECT_FAILURE|POLICY_REJECTION|PREFLIGHT_REJECTION|CANCEL_EVENT|
RUNTIME_FAILURE`；Runtime 在 grant 前从 authoritative Effect/control/rejection record
read-back exact ref/digest。Outcome matrix 要求 evidence 时三字段同非 null，否则同 null；
memory Store 只接受 authorization proof 所绑 exact projection，无需也不得信 caller receipt。
`runtime_distillation_commit_authorizations` 至少投影
`authorization_id PK, assignment_id, run_id, activity_id, activity_generation,
fence, attempt_ordinal, logical_effect_id, proposal_ref, proposal_digest,
commit_plan_ref, commit_plan_digest,
expected_batch_id, expected_batch_digest, expected_report_id,
expected_report_digest, status, committed_batch_id, committed_batch_digest,
committed_report_id, committed_report_digest, work_disposition_id,
work_disposition_digest, completion_id, completion_digest, conflict_ref, conflict_digest, event_seq,
payload_digest`，status 闭集为 `GRANTED|COMMITTED|RETIRED_NO_COMMIT`，并以
`UNIQUE(activity_id,activity_generation,attempt_ordinal)` 防双 grant。`GRANTED` 两组
terminal fields 全 null；`COMMITTED` 必须且只能绑定可 read-back 的 exact multi-record
Batch/Report/Disposition/completed Completion IDs/digests，且 committed Batch/Report 必须
等于 expected IDs/digests；Runtime 分别通过 memory Store public getters
（`KnowledgeStore` 的 Batch/Report/Disposition 加 `VerifiedEvidenceStore` 的 Completion）read-back并重算
覆盖，不依赖不存在的聚合 receipt ref。`RETIRED_NO_COMMIT` 必须且只能绑定 conflict
ref/digest。两组互斥，replay validator 双向核对 Ledger。
`runtime_distillation_closure_authorizations` 投影 exact Run/Activity/generation/fence/
control-event、`dead_letter|cancelled`、terminal receipt ref/digest 与 payload digest；
同一 generation 的 commit/closure authorization 由 transition validator 强制互斥。
pending cancel/failure 是 append-only Runtime control event，并由 projection 绑定目标
Decision Recall 或 Distillation authorization；同一 Run-version/control-event CAS 只可
选择一个 pending kind，success/no-commit resolution 必须在同一 control-store CAS 中
消费它。open/replay validator 双向核对 authorization events、projections、Ledger
receipt/proposal artifact 和所有 ref/digest。
`runtime_artifact_staging` 记录 stable logical-output ID、owner Activity/
generation/fence、temp nonce/path、claim epoch/expiry/progress deadline、cleanup
epoch/operation nonce/exact gated cleanup-actor identity 与状态；
状态闭集为 `CLAIMED|DIGESTED|BOUND|CLEANUP_PREPARED|CONSUMED|RELEASED`，前四者
为 active，后两者为 terminal；
`runtime_artifacts` 记录 digest/size、monotonic object generation、materialization
claim 和 `MATERIALIZE_PREPARED|LIVE|MOVE_PREPARED|QUARANTINED|
MATERIALIZE_ABORT_PREPARED|RESTORE_PREPARED|DELETE_PREPARED|DELETED`
lifecycle，以及 filesystem-mutation operation/nonce/epoch、actor exact PID/
OS-start-time/session/process-group/executable identity 与 per-object-generation
advisory-lock identity。Artifact reference 只能
与 `MATERIALIZE_PREPARED → LIVE` 首次发布或已验证 `LIVE` 的 ref creation 在同一
writer transaction 建立。独立 `runtime_artifact_refs` 绑定 object digest/
generation、owner kind/ID、creating event seq、retention/export policy digest 与
`ACTIVE|RELEASED`；它是唯一 byte-GC-root relation。Journal 中的历史 digest 只有
在 active ref 存在时要求 bytes；retention release 必须提交
`ArtifactReferenceReleased` event，replay 才接受 `DELETED` tombstone。
`runtime_artifact_handoffs` 是 non-root coordination projection：
`handoff_id PK, experience_id, work_item_id UNIQUE, work_item_payload_digest,
work_item_projection_json,
artifact_ref_id UNIQUE FK,
object_digest, object_generation, campaign_profile_ref,
campaign_profile_digest, owner_kind, owner_id, state,
created_event_seq, current_event_seq, enqueue_attempt_id,
enqueue_attempt_generation, enqueue_attempt_state, enqueue_attempt_fence,
nullable ledger_enqueue_receipt_ref,
nullable ledger_enqueue_receipt_digest,
nullable ledger_enqueue_transaction_ref,
nullable ledger_enqueue_transaction_digest, nullable release_reason,
nullable release_evidence_ref, nullable release_evidence_digest,
payload_digest`。attempt columns 是 current-attempt projection，不覆盖历史。
`state CHECK(PENDING/BOUND/RELEASED)`；owner 必须是
`DISTILLATION_WORK_ITEM` + exact Work Item ID；`enqueue_attempt_state` 闭集
`NOT_STARTED|IN_FLIGHT|RETIRED|LEDGER_PRESENT|PROVED_ABSENT`，并由 monotonic attempt fence 防
stale coordinator；`NOT_STARTED` iff attempt ID/generation/fence 全 null，其他状态三者
全 non-null且匹配 attempt table。创建 handoff 与 verified-`LIVE` object 的
`ACTIVE` ref 在同一 Runtime writer transaction；`BOUND` 必须绑定 exact Ledger Work
Item/enqueue receipt 以及从 memory public getter 独立 read-back 的 enqueue-transaction
sidecar，逐字段核对 attempt ID/generation/fence、original proof digest 与 transaction
digest，并同时保存 receipt 与 enqueue-transaction 两组 ref/digest。空值矩阵固定为：
`PENDING` 时两组都 null；`BOUND` 时两组都 non-null；从 `BOUND` 进入 `RELEASED` 后保留
两组；`ORPHAN_ABSENT/RELEASED` 两组仍 null，release evidence 的 composite event payload
另绑定 abandonment proof 与 abandoned receipt ref/digest。`RELEASED` 必须与同 transaction 的
`ArtifactReferenceReleased`/ref release 一致。handoff row 永远不参与 reachability count，
GC 只数 `runtime_artifact_refs.state=ACTIVE`。
handoff creation 接受 frozen canonical Work Item projection，先重算 Work Item ID/payload
digest，并校验 Experience、namespace/scope、Distillation/Lifecycle policy 与 profile
lineage，再存 `experience_id/work_item_projection_json/work_item_payload_digest`；不可只信
调用方给的 hash。projection JSON 是 immutable canonical payload，不代表 Ledger Work Item
已经存在。

`runtime_artifact_handoff_attempts` 为每个 immutable attempt identity 保留一行，其 state
只可由 journal-backed CAS 单调推进：
`enqueue_attempt_id PK, handoff_id FK, attempt_generation, attempt_fence,
state, created_event_seq, current_state_event_seq, nullable recovery_request_id/digest,
nullable recovery_proof_ref/digest,
payload_digest, UNIQUE(handoff_id,attempt_generation),
UNIQUE(handoff_id,attempt_fence)`；state 闭集
`IN_FLIGHT|RETIRED|PROVED_ABSENT|LEDGER_PRESENT`；合法路径只有
`IN_FLIGHT -> RETIRED -> PROVED_ABSENT`、`IN_FLIGHT -> LEDGER_PRESENT` 或
`IN_FLIGHT -> RETIRED -> LEDGER_PRESENT`，每次 state CAS
同时 append event/update `current_state_event_seq`。recovery request/proof pairs iff
`PROVED_ABSENT` non-null；proof 必须回绑 byte-equal request ID/digest 和 attempt triple。
`RETIRED -> LEDGER_PRESENT` 不复活 enqueue authority；它必须由 old-fence drain 后 exact
request-bound `QUEUED_PRESENT` proof + Work Item/ingestion receipt/enqueue sidecar read-back授权，
transition event 记录该 recovery proof，handoff 则保存 receipt/sidecar refs/digests。
旧 attempt 永不重新激活；handoff 为
`PENDING`、ref 为 `ACTIVE`、current attempt 已 `PROVED_ABSENT` 且 source enqueue
obligation 仍 OPEN 时，显式 retry 可 append higher generation/fence 的新 `IN_FLIGHT`
attempt 并原子更新 current projection。
`runtime_distillation_enqueue_obligation_abandonments` schema 为
`proof_id PK, experience_id, work_item_id UNIQUE, work_item_payload_digest,
handoff_id UNIQUE FK, enqueue_attempt_id UNIQUE FK,
attempt_generation, attempt_fence, source_run_id, source_activity_id,
recovery_request_id, recovery_request_digest, absence_proof_ref,
absence_proof_digest, absence_frontier,
terminal_control_event_seq, terminal_cause, disposition, event_seq, payload_digest`；
`disposition CHECK(NO_FUTURE_RETRY)`，absence proof pair 必须 byte-equal 该 exact attempt
row 的 recovery proof pair；absence frontier、source Activity/control event 与 current
handoff projection 的 attempt ID/generation/fence 必须由同一 writer transaction validator
read-back exact equality。
`DistillationEnqueueObligationAbandonedProof` 是该 immutable Runtime row/event 的 strict
view；它逐字段暴露 frozen Work Item projection/digest，以及 handoff 创建时已验证的
Experience、namespace/scope、Distillation/Lifecycle policy、Campaign Profile semantic
lineage；只允许
source Activity 的 authenticated terminal control owner 在 current handoff=`PENDING`、
ref=`ACTIVE`、current attempt=`PROVED_ABSENT` 且重新 read-back exact later-frontier absence
proof 后写入。其 closed disposition 只有 `NO_FUTURE_RETRY`，same Work Item different proof
是 identity conflict；public getter 只返回该 canonical row 的 digest-bound strict view。
`ORPHAN_ABSENT/RELEASED` CAS 再次要求 current projection 仍是 proof 绑定的
`PROVED_ABSENT` attempt triple；任一 higher-generation retry 已出现时旧 proof 必须拒绝。

Campaign Admission Profile handoff 的 canonical order 是：publish content-addressed
bytes → compute Work Item ID from Experience/policies/profile ref+digest → one Runtime
transition creates deterministic ref/handoff (`PENDING`) → **同一个 Runtime writer
transaction** 将 `NOT_STARTED -> IN_FLIGHT`、分配 `enqueue_attempt_id/generation/fence` 后才返回
绑定该 active attempt 的 getter proof → Ledger queued enqueue → Ledger Work
Item/enqueue receipt + enqueue-transaction sidecar 独立 read-back（核对 attempt triple、
original proof/transaction digests）→ Runtime CAS `LEDGER_PRESENT/BOUND`。Ledger 首次 insert
只接受 exact、current、未 fenced 的 `IN_FLIGHT` proof；尚为 `NOT_STARTED` 的 handoff
不是 enqueue authority。artifact-ref
ID/handoff ID 从 Work Item ID、profile/object digest 与 versioned domain 派生；两者不进入
Work Item content-ID projection，避免 hash cycle。首次 proof 是
`handoff=PENDING + attempt_state=IN_FLIGHT`，reply-loss
exact replay 可为 `BOUND`；Runtime/Event payload identity 不依赖 wall clock。

Recovery 从 handoff 冻结并回传 canonical Work Item projection，绑定 Experience ID、Work
Item ID/payload digest、handoff/ref 与 current
attempt ID/generation/fence 的
`DistillationEnqueueRecoveryRequest`，再用它读取 memory Store 的 fixed-frontier
`DistillationEnqueueRecoveryProof`；proof 三臂都必须 echo request ID/digest、semantic
lineage 与 attempt triple，并按上表生成 deterministic proof ID/ref/digest。old-fence drain
后，`QUEUED_PRESENT` 且 Work
Item/receipt/sidecar exact 时允许该 attempt
`RETIRED -> LEDGER_PRESENT` 并 bind；这覆盖 retire 期间旧 transaction 已通过验证并最终
commit 的顺序。`ABANDONED_PRESENT` 只在 Work Item/sidecar absent 且该 Experience 的
exact abandoned receipt 回绑同一 Work Item payload digest/Runtime proof 时完成 release
reconciliation；`ABSENT` 只有同时证明不存在 in-flight enqueue
authorization/attempt、coordinator 已停止且旧 attempt 先被 Runtime higher-fence CAS
retire、并等待所有旧-fence Ledger transaction 不再运行后，才能在**后续 frontier**
取得 `ABSENT` proof、把该 attempt 投影成 `PROVED_ABSENT`。此时 handoff/ref 仍保持
`PENDING + ACTIVE`，normal retry 只可 append higher-generation/fence attempt。
`ORPHAN_ABSENT` release 还必须 read-back durable
`DistillationEnqueueObligationAbandonedProof`，它绑定同一 Work Item/source Activity、该
attempt-bound recovery request + later-frontier absence proof、terminal control cause 和
不可逆 no-future-retry disposition。memory Store 随后必须用该 strict proof append/read-
back source Experience 的唯一 `abandoned_before_enqueue` Distillation Receipt；release CAS
再通过 memory getter 核对 receipt 的 abandoned Work Item/payload digest/proof pair，缺失时保持
`PENDING + ACTIVE/WAITING_INPUT`。
不得在发出/仍可能使用 enqueue proof 的 transaction 中同时
证明 absent。timeout、普通 not-found、stale proof
或 concurrent enqueue 下 ref 保持 ACTIVE/PENDING。Ledger commit-before-bind 的 crash 用
same Work Item/enqueue receipt/sidecar IDs 收敛，不创建第二 ref/handoff。

`BOUND` release 的另一路只接受 Runtime read-back 的 terminal Work Completion，加上
campaign replay/audit retention 的独立 ACTIVE ref proof 或 retention-expired receipt；
同一 transition 写 `WORK_COMPLETED_RETENTION_SATISFIED`、handoff=`RELEASED`、ref release
和事件。source/campaign Run terminal、Assignment 或 projector scan 都不是 release
authority；Runtime Artifact Store 是唯一 byte-GC authority。
`runtime_checkpoints` 记录 Activity/generation/progress cursor、policy、input/
schema digests、content-addressed resume-token artifact ref/digest 与 producer
epoch；canonical event + checkpoint row + artifact reference 在同一 Durable
Transition，不能只靠 workspace 文件。
另建 `runtime_invocation_evidence` 作为 non-authoritative append-only inbox；它只
接受 authenticated Adapter/process 提交的 invocation/request/Adapter/evidence
digests 和 raw receipt reference，不能更新 projection、settle budget 或完成 Run。
`runtime_admission_incidents` 持久化 admission epoch/enabled、incident ID/scope/
reason 与 resolution；所有 new Drive、worker claim/commit 都在事务内检查其 epoch。

### 5.3 Atomic transition

一次 Durable Transition 在同一事务中：

1. 在 write transaction 中读取 current event sequence/projection；
2. worker path 检查其 `expected_event_seq`、current lease owner、current fencing
   epoch 且 lease 尚未过期；operator
   path 检查 authenticated command identity，非取消命令再检查
   `expected_version`，`CancelRun` 始终针对事务内 current non-terminal state；
   private watchdog path 不取 Run Lease，但必须检查 authenticated system
   identity、unexpired timer claim owner/epoch、due store time、Activity generation、
   unchanged progress cursor/deadline 和 expected event sequence；
   private incident path 必须检查 authenticated sweeper identity、active incident
   epoch/scope 与 per-Run expected event sequence；
3. 影响执行的 operator command 或 authorized watchdog/incident system-control
   transition revoke/increment fence；检查
   command/effect/invocation idempotency 与 payload/request digest；
4. append canonical event；
5. 更新 projection；
6. reserve/settle budget；
7. 发布 artifact/receipt references；
8. 写 outbox；
9. commit。

任一步失败，event sequence、projection、budget 和 outbox 均不前进。

### 5.4 Replay and corruption

新增 `tests/test_runtime/test_runtime_history_replay.py`：

- 删除 projection 后，从 event 0 replay 的 snapshot hash 与原值相同；
- 从每一个 event prefix 做 pure reducer/schema/invariant replay 均得到合法 state；
  historical prefix 不拿当前 filesystem 做 byte-presence validation，因为后续
  `ArtifactReferenceReleased/DELETED` 可能已合法删除当时的 bytes。只有 full/current
  projection replay 校验当前 active-ref/lifecycle 所要求的 bytes；
- unknown event version、sequence gap、payload digest mismatch、foreign-key
  break，以及被 `ACTIVE` ref/`LIVE` lifecycle 要求存在的 artifact missing/corrupt
  全部 fail closed；`RELEASED` ref + audited `DELETED` tombstone 必须可正向 replay，
  不要求已过 retention 的 bytes 仍存在；
- projection 与 event journal 不一致时不得选择“较新 JSON”；
- replay 不触发任何外部 effect；
- 删除/损坏 pinned workflow/policy/Adapter artifact 或移除所需 interpreter 时
  fail closed，不得用新部署的 default；artifact retention/GC 在非 terminal Run
  和保留的 replay history 存在时不能回收它们；v1 换版必须新建带 predecessor
  provenance 的 Research Run，且只能按普通 scope/governance 规则 import snapshot。

## 6. Lease、fencing 与 progress

### 6.1 Lease protocol

- acquisition 使用 store time，事务内递增 epoch；
- same-boot `store_time` 来自带 persisted boot identity 的 host monotonic clock；
  lease/timer 不用可调 wall clock。boot identity 改变时旧 lease 全部 expire，timer
  用 persisted UTC metadata 经 clock-sanity bound reconcile；超界进入 typed
  `ClockUncertain/WAITING_INPUT`，不猜 due state；
- initial defaults：renew every 10 秒、TTL 45 秒；
- v1 每个 Research Run 只允许一个 active Runtime Activity，parallelism=1；
- renewal 仅允许 same owner + same unexpired epoch；过期后同 owner 也必须重新
  acquire 并获得新 epoch；
- 每个 checkpoint、effect receipt、stage commit、budget settlement 携带 epoch；
- lease expiry 只允许 takeover，不自动证明 stage failed；
- takeover 后旧 epoch 的写操作全部返回 `LeaseLost`；
- Activity progress cursor 与 lease renewal 分开记录；
- stall policy 使用 last semantic progress，不使用单纯 background heartbeat。

### 6.2 Required tests

`tests/test_runtime/test_long_task_concurrency.py`：

- 100 application clients 并发同一 `DriveRun`，只建立一个 Research Run；
- 100 个 distinct Runs 并发 cold-miss 同一 snapshot content scope 且
  reuse-governance digest 相同，只允许一个有效 Snapshot Build Claim/commit；无
  fault 时真实 builder executor count=1，其余 Runs 各有 import receipt；
- content scope 相同但 tenant/export/privacy/locality/retention/isolation policy
  不兼容时必须分属不同 Build Claim；producer export + consumer admission 任一
  拒绝都不得 import，并记录 policy-digest authorization decision；
- snapshot producer kill 后 claim 可 takeover，旧 producer publish 被 fence；
- Snapshot Build Claim 记录 owner Activity/epoch/monotonic expiry/progress
  deadline/state；publish 同时要求 current Run Lease + Claim epoch。Claim renewal
  只能随 semantic build progress；producer pause/cancel/stall 会 abandon/revoke，
  consumer 由 durable Claim timer 唤醒；
- producer death/claim expiry 后 100 consumers race 只产生一个 higher-epoch owner；
  crash-after-publish-before-wakeup、abandon/reacquire、late stale publish、cancel vs
  publish races 均不重建或永久等待；
- 1,000 次 two-worker takeover race，stale commit 拒绝率 100%；
- current owner 但 epoch 过期、epoch 正确但 owner 错误、owner/epoch 正确但
  lease 已过期三种 commit 均 100% 拒绝；
- `SIGSTOP` worker 超过 TTL，新 worker takeover；旧 worker 恢复后所有写入失败；
- lease renewal 活跃但 progress cursor 超过 pinned deadline，独立 watchdog
  仍须提交 stall event、revoke fence、终止/隔离 work，并按 checkpoint policy
  自动 retry 或 `WAITING_INPUT`；不得永久挂起；
- watchdog 只凭 durable timer claim + exact progress/activity/event CAS 获得 private
  system-control authority，不取 Run Lease；semantic progress 与 watchdog 同时提交
  的 1,000 次 race 中只允许事务先到者获胜，progress 先到时 stale timer 必须取消
  且 false stall/preemption 为 0；
- progress 活跃但 lease 丢失，Activity 不得提交；
- same-boot wall clock 前跳/后跳 ±1 小时不改变 monotonic lease/timer 到期与 RTO；
  boot identity change 立即失效旧 lease，并测试 sane-UTC timer reconcile 与
  uncertain-UTC fail-closed；
- transaction busy 不会产生双 lease。
- 在每个 write-transaction phase（gate acquired、BEGIN、event append、projection、
  commit/fsync）`SIGSTOP` control owner；2 秒 ceiling 后 launcher 只 kill exact
  marker control child，SQLite recovery/restart 后 command/control CAS 成功，非
  owned PID kill=0；application/executor SIGSTOP 不会持 writer gate；
- operator `CancelRun/PauseRun` 不需 worker lease，并会在 command transaction
  内按下述仲裁规则处理；持 lease 的 stuck worker 无法阻塞控制命令；
- `PauseRun` 进入 `PAUSING`，在 semantic checkpoint/terminate + reconcile 后才
  `PAUSED`；旧 worker 在 fence revoked 后不能提交所谓 pause checkpoint；只有
  新 control owner 可请求 backend-native checkpoint，否则从最后一个已提交
  checkpoint 恢复；无法安全暂停的 effect 进入 `WAITING_INPUT`；
- Intent admission、Decision Recall 或 Distillation authorization 未决时，
  `PauseRun` 必须返回 `CommitArbitrationBusy`，state/pending-control/fence 全不变化；
  success/no-commit reconcile 后重试才可接受。授权未决时的 `RunQuarantined`/fatal
  incident 只关闭 new work 并持久化 secondary failure，不 revoke grandfathered fence；
  先解出 Ledger outcome，再进入 `WAITING_INPUT/FAILING`；
- safe pause 在同一 transaction 把 Activity 置为 `PAUSED_AT_CHECKPOINT`，绑定
  validated resume token 或 restart-from-last-committed disposition；`ResumeRun`
  将同一 Activity identity/generation 置回 `READY`，不新建 Attempt/effect；测试
  pause cleanup 后、`PAUSED` commit 前 crash 的 ownership reconcile 与重放；
- Runtime clock 先提交 `TimerFired/DeadlineReached/BudgetExpired`，planner 不读
  wall clock；相同 timer event 的 jitter/due decision 可重复。
- `ActivityStarted` 与初始 progress-deadline timer 在同一 transaction；每次
  semantic progress commit 同时取消旧 cursor timer 并创建绑定新 cursor/deadline
  的 timer，任一 crash prefix 都不存在 committed RUNNING Activity 无 watchdog
  timer 的状态；
- 进入任一 unresolved append/commit authorization phase（Decision Intent
  `REGISTERING`、Decision Recall `CONTEXT_COMMITTING|OUTCOME_COMMITTING`、Distillation
  `COMMITTING`）都在同一 transition 取消普通 progress timer、创建绑定
  authorization ID/digest 的 `COMMIT_RECONCILIATION_DEADLINE`；deadline fire 只能写
  typed overdue-review/pending-failure/new-work-closed，不得 revoke/retire authorization 或
  推进 fence，且 fire CAS 要求 exact authorization 仍 current+`GRANTED`。success/no-commit
  reconcile 在同一 Runtime transaction 取消 deadline；late timer claim no-op。若只有
  overdue-review，reconcile 后进入 `WAITING_INPUT/COMMIT_RECONCILIATION_OVERDUE`，由
  `ResolveRun` 显式 reopen/fail，绝不留下无 owner 的永久 closed gate。
  1,000 次 pause/quarantine/watchdog 与 commit-result race 中，必须先 success/no-commit
  reconcile，second authorization/semantic writer=0；
- Intent admission 在 proposal→`REGISTERING` 后注入 reply loss/control crash，必须由同一
  authorization-bound deadline 唤醒 reconciliation；success/no-commit 都取消原 deadline，
  overdue/reconcile race 不得产生 ghost OPEN、永久 REGISTERING 或第二 admission；
- 100 executor claim requests 同时竞争一个 due timer，control 只能 commit 一个
  `TimerFired`；executor 在所有 Runs 均 `WAITING_RETRY` 时仍会由 durable timer
  唤醒；
- executor 在 timer claim 后死亡，claim 可接管且 fired event 不丢不重；
- progress rearm 与旧 timer fire 的 1,000 次 race 中，旧 cursor timer 只能
  CAS-noop/cancel，不能产生 false stall；
- pause/cancel/terminal 或 superseding transition 会在同一 transition 持久化
  取消不再适用的 timers，重启后不会误 fire；
- 可能超过 progress deadline 的 Activity 必须 subprocess/container；
  in-process Activity 具有 enforced timeout 和 cooperative cancellation。
- in-process Adapter conformance：timeout/cancel 后 zero owned task/thread、
  zero post-fence new `DISPATCHED` authorization；non-cooperative blocking fake 必须在 registration
  失败或被强制路由到 subprocess，不能仅记录 timeout 后留在线程中运行。

### 6.3 Launcher/control/executor operational Interface

生产部署由 `systemd`、`launchd` 或 container service 启动同一个 long-lived
`python -m research_agent.runtime.launcher --root ABSOLUTE_RUN_ROOT` wrapper，不能
直接启动 `worker.py`。Wrapper 创建/消费 child readiness pipes，启动 exactly one
private control child 与 one-or-more executor children，解释 child exit codes，监控
writer-gate owner，并负责 bounded restart；因此不依赖 launchd/Docker 原生按 code
筛选或 pipe 能力。Root resolution、socket/status paths 与 file permissions 冻结。

Control child 完成 store open + replay validation + permission-checked Unix socket
bind 后，连同 minimum executors 向 launcher ready。Launcher 再 atomic-write +
directory-fsync status JSON，字段为 protocol、`READY|BLOCKED_OPERATOR|DRAINING`、
launcher/control PID+start identities、executor count、storage ID、runtime/schema
versions 与 generation；application 还须 socket handshake 同 generation。Child
`1/75` bounded-restart，`64/70/78` 令 launcher 留在 `BLOCKED_OPERATOR`；launcher
install-time `--check-config` 才返回 `64/70/78`，service mode 遇同类错误保持
blocked 而不退出。Launcher clean drain exit `0`，unexpected/transient exit
`1/75`，普通 systemd/launchd
on-failure 只监督 wrapper。

不能把 POSIX parent relationship 当 ownership。每个 control/executor child 都在
exec gate 后启动，并持有 dedicated parent-death guard pipe 的 read end；唯一 write
end 只在 launcher，其他 descriptor close-on-exec。Launcher 在 one-shot exec
authorization 前 atomic-write + directory-fsync cohort record：root/storage ID、
launcher generation/nonce、role、PID、OS process-start identity、executable digest。
Guard EOF 时 child 立即 close admission/claims，经其 ownership protocol 清理
descendants 后退出；Linux parent-death signal、service cgroup/container init 只作
额外 hardening，不是 portable correctness 前提。

每次启动先取得 per-root exclusive launcher gate，并在 spawn 新 control 前完成
role-reconciliation barrier：按 exact PID + start identity + role + executable +
storage/generation 验证 prior control/executor cohort，bounded TERM/KILL、等待 role
identity 消失并清算 stale socket/status/cohort。V1 不 adopt 旧 role；identity 无法
证明时绝不发 signal，任一旧 role 无法终止时保持 `BLOCKED_OPERATOR`，禁止新
control 启动。

独立 session/container 中的 persisted workload 不进入这道 pre-control barrier，
因为只有 Runtime journal 能授权 reconcile，launcher 不是 Run-state writer。旧 role
清除后，新 control 作为 sole writer 以 `RECOVERING` 启动、推进 control/fence
generation，再由 recovery executor 按 journal identity query/stop/reconcile。此时
application handshake not-ready 且 new external dispatch=0；owned workload 全部清算
后才能 publish `READY`。无法证明/终止的 workload 改为 `BLOCKED_OPERATOR`，control
只开放 authenticated recovery/inspection。Child 本身也走 persist-before-authorize
gate，所以 crash-between-spawn-and-cohort-fsync 只会令未授权 child 因 EOF 退出。
Launcher gate + two barriers 必须同时阻止双 control 与 journal-recovery deadlock。

Launcher 每 5 秒经 out-of-band channel 发 nonce ping，control 必须 15 秒内 echo；
control request/planning/read hard ceiling=5 秒，write gate ceiling=2 秒。missed ping
或 outstanding request 超界时，即使未持 SQLite gate，也只 TERM/KILL exact
control child 并重启。测试在 idle、inspect/read、planning、每个 write phase 分别
`SIGSTOP` control，均须在 RTO 内恢复；CLI/Web `SIGSTOP` 永不持 DB lock。

`SIGTERM/SIGINT` wrapper 停 admission/claims、bounded drain/reconcile children，
成功 exit `0`；无法安全完成则先 fence/留 durable evidence 再 exit `75`。验收分别
`SIGKILL` executor、control 与 launcher-only，并测到 first continuation 的端到端
RTO。Launcher-only case 必须包含 child guard monitor 正常退出、child 被
`SIGSTOP` 而存活、stale socket/status/cohort 与 overlapping restart；prior exact
role identities 未消失前新 control 不启动；随后 `RECOVERING` control 在 owned work
未 reconcile 前 readiness/new dispatch 必须为 false。
未配置外部 launcher 的 embedded mode 只能标为 durably resumable after manual
restart，不能计入 G3。

### 6.4 Admission/incident control tests

- 创建 integrity incident 与关闭 admissions 是一个 authenticated transaction；
  之后会创建新 Run 的 `DriveRun` 返回 typed `AdmissionClosed`；命中 active
  incident 的 previously-unseen existing-Run mutation 返回 public
  `IncidentFenced`，但 new monotonic `CancelRun` 仍可 revoke，`inspect` 仍可读；
  scope 外 existing Run 可继续 drive；worker claim/commit 只返回 private
  control-protocol fence rejection，不扩大 public Interface union；
- accepted command 的 same-ID/same-payload replay 与 different-payload conflict
  在 incident/admission gate 前解析；注入 incident 于 commit 后/reply 前，1,000 次
  replay 全为 `DUPLICATE`，不能漂成 `IncidentFenced`；active incident 下 new
  `CancelRun` 1,000/1,000 accepted/terminal-noop，其他 mutation 被 fence；
- incident create 与 1,000 个 worker commits race：匹配 scope 的 incident epoch
  commit 后 accepted worker commit=0，即使 per-Run sweep 尚未完成；
- idempotent sweeper 以 incident ID + per-Run event-sequence CAS retry 提交
  `RunQuarantined`、revoke fence 并进入 `WAITING_INPUT`；重复/崩溃恢复不漏不重；
- 不匹配 scope 的 healthy Run 不被 quarantine；incident clear/ResolveRun 需要
  独立认证、reason/evidence 和审计 event；
- rollback drill 同时验证 global、tenant/scope 与 single-Run incident；
- post-delete drill 在 current-journal copy 上验证 retained previous durable bundle
  的 ref/digest 与 Runtime/Adapter/schema replay compatibility；不兼容时必须保持
  `AdmissionClosed`，不得 downgrade schema 或调用 legacy benchmark harness。

## 7. Effect journal、artifact 与 process contract

### 7.1 Effect journal

稳定 effect key：

```text
run_id / scope_id / stage_generation / effect_name / effect_index
```

logical effect record 还必须绑定 canonical request digest、Adapter/version 和
operation identity；相同 key 不同 digest 100% 冲突。每次物理调用使用新的
`invocation_id`、独立 reservation 和 cost receipt。每次 dispatch 前必须在同一
事务创建 invocation、reserve worst-case budget、绑定 logical effect/request/
Adapter/worker epoch，并置为 `DISPATCHABLE`；调用返回或 reconcile 后再独立提交
`RECEIPT_KNOWN|AMBIGUOUS|CONFIRMED_NOT_EXECUTED`。Known receipt/non-execution
才 settle；`AMBIGUOUS` 保留 worst-case reservation，后续用 append-only
reconciliation record 转为 final known/not-executed 或 `UNRESOLVED`，不覆盖原
ambiguity。`UNRESOLVED` 不是 final；operator 只有在追加 reason/evidence、确认
zero owned local work 并把 worst-case reservation 全额计费后，才能推进到 final
`ABANDONED_WORST_CASE`。该状态不声称 remote side effect 未发生，并必须记录
abandonment class：`REEXECUTABLE_NO_COMMIT` 仅在当前 fence 证明 late bytes 不可
select/commit 时允许继续；`REMOTE_OUTCOME_UNKNOWN` 只允许 containing Run 进入
`FAILED` 且 scientific outcome 为空。resolution-state contract tests 必须拒绝
后者到 `CANCELLED|COMPLETED` 的任何 transition。第二、第三次调用必须新增 row，
不能覆盖第一次的 dispatch/ambiguity/cost history。在 logical
effect 前 durable `EffectPrepared`，成功后由至多一个 invocation receipt 形成
durable `EffectReceipt`。

跨 external call boundary 前必须先 guarded commit `DISPATCHED`；该 commit 后至
receipt 前的 crash 一律按 ambiguous reconcile，只有停在 `DISPATCHABLE` 才可证明
尚未调用。测试逐一覆盖 create/reserve、dispatchable、dispatched、provider
success、receipt、settlement 各 seam，并断言 invocation row/history 不被 retry
覆盖。

`DISPATCHED` 是 irrevocable authorization；若 Cancel/Pause 在它之后、physical
boundary 之前赢得 fence，Runtime 仍按可能已发出处理并 kill/query/reconcile/
account。Hard invariant 是 fence 后新 `DISPATCHED` commit=0，不是不可能保证的
provider packet=0。

Lease 已丢失或 Pause 已 revoke fence 的 Adapter 只能把迟到 receipt 幂等追加到
evidence inbox。当前 fenced owner 验证 provider identity/signature、request/
operation match 和冲突后，才可在正常 Durable Transition 中 promote receipt 与
settle；conflicting/unverifiable evidence 进入 `WAITING_INPUT`。测试覆盖自然
takeover、pause、cancel 与 receipt race，且 stale evidence append 永远不能直接
改变 lifecycle/scientific outcome。terminal transition 与 late reconcile 的 race
由同一 event-seq/fence CAS 串行化：receipt 先赢则必须纳入 settlement，abandon/
terminal 先赢则迟到 evidence 只进入 inbox/audit，不能重选 logical result 或退回
已计 worst-case cost。
Adapter contract 必须声明：

- `IDEMPOTENT`：相同 key 可重试；
- `QUERYABLE`：可按 key 查询最终状态；
- `REEXECUTABLE`：没有不可逆 remote side effect，可在保留旧 reservation 的
  前提下用新 invocation 重做，由 fence 选择一个 logical result；
- `NON_RECONCILABLE`：未知结果时只能 `WAITING_INPUT`。

LLM、browser/tool、Docker/training、verifier、experience ledger 全部登记。若
现有 provider 不提供原生 idempotency，Runtime 仍要缓存已确认 receipt，但不能
把“请求发出后连接断开”谎称为 exactly once。

### 7.2 Artifact contract

写任何 output bytes 前，control 先提交 durable staging claim，绑定 stable logical
output、owner Activity/generation/fence、claim epoch/expiry、target-filesystem temp
nonce/path。Executor 获授权后执行 temp write → flush → fsync → digest/size，
再由 control CAS `ABSENT → MATERIALIZE_PREPARED` generation 1，或 generation+1
的 `DELETED → MATERIALIZE_PREPARED`，并绑定 staging claim。Exact claimant 才能
atomic install 到 content-addressed path + destination-directory fsync；control 最后
重验 claim/object generation/digest/size，并在同一 transaction 做
`MATERIALIZE_PREPARED → LIVE` + first reference + consume staging claim。已
`LIVE` 对象也必须先验证 digest/size；verified-LIVE reuse branch 在同一 control
transaction 创建新 owner 的 `ACTIVE` ref 并 consume/release staging claim，executor
再删 redundant temp，不进入 materialization state。该 branch 的 ref/claim atomicity
和 crash replay 必须有独立 contract test。

Cancel/incident/abandoned producer 必须由 recovery owner 先 revoke staging install
authorization 并 terminate/wait exact Run-owned publisher task/process，再按下述
prior-actor protocol 终止/wait 已登记 materialization actor 并确认 object lock
release；未证明两类 actor 已退出前不得 CAS 新 operation。随后才以 exact object +
staging generation CAS 到 `MATERIALIZE_ABORT_PREPARED`，分配 fresh
`fs_mutation_epoch`，登记并授权 abort actor。该 actor 删除 temp；若 rename 已发生，
则把 zero-ref live path atomic-move 到 quarantine + directory fsync。Control 最后把 object 置为
`QUARANTINED`（保留 grace）或 `DELETED`（未 install），同时 release/clean staging
claim 并写 abort event。任一 crash 从 abort-prepared + temp/live/quarantine paths
roll forward；publisher exit、prior mutation-actor exit/lock release、ownership 或
bytes 无法证明则 Run 保持 non-terminal。
若 verified-`LIVE` reuse 尚未取得 materialization generation，则只 CAS staging 到
`CLEANUP_PREPARED`，publisher 退出后删 redundant temp 并 release claim，不改已有
object/ref set；该 cancel/incident race 也必须覆盖。

任何 shared content path mutation（materialize install、abort-to-quarantine、GC
move、restore、final delete）都必须由 dedicated killable gated filesystem-mutation
actor 执行，不得在 control process 或普通 executor 内直接执行。Control 先用
transaction reserve exact object generation、operation kind/nonce 与 monotonic
`fs_mutation_epoch`；launcher 创建尚未获授权的 actor，再以 CAS 持久化其 exact
PID、OS process start time、session/process-group、executable 与
per-object-generation kernel advisory-lock identity，最后才发 one-shot
authorization。Actor 在 path mutation 和 file/directory fsync 全程持有该
process-shared lock；finalize CAS 必须重验 generation/operation/nonce/epoch。V1 不
adopt 未登记 actor。Actor 还必须在每个 rename/unlink/fsync 前即时重验 durable
operation/epoch 与 one-shot authorization；失败就不触碰路径并退出。

任何 higher-epoch takeover 在 CAS 新 epoch 或授权新 actor **之前**，必须重验并以
bounded TERM/KILL 终止旧 row 记录的 exact actor，wait process exit，再确认 kernel
lock 已释放；任一条件无法证明即 fail closed，旧 claim 保持 active。这样旧 actor
即使在 content move 前或 move 后/finalize 前被 `SIGSTOP`，也不能在新 owner
reconcile、restore 或 publish ref 后恢复并再次移动 shared bytes。Verified-`LIVE`
reuse 的 redundant temp 是 unique nonce path，只走 staging-only cleanup；它仍需
publisher exit + claim ownership，并使用 durable staging-cleanup epoch、operation
nonce 与 exact gated cleanup-actor identity，在每个 unlink/directory-fsync 前重验；
但不分配 object mutation epoch，也不拿 shared-content lock。

Staging cleanup 只能先以 expired/revoked claim epoch CAS 获权；live paused claim
不能按文件 age 当 orphan。Fenced publisher 即使迟到留下 unreferenced bytes，也
不能通过 finalize CAS。Recovery 根据 staging/lifecycle state 与 temp/live paths
roll forward；SQLite write transaction 内不做 filesystem I/O。测试覆盖：

- staging claim 前 kill：无 bytes/ref；claim 后、temp write 各 seam kill：claim
  takeover/cleanup 后无 published reference；
- digest report 后、`MATERIALIZE_PREPARED` 前 kill，以及 prepare 后/rename 前、
  rename 后/finalize 前 kill：recovery 只由 exact claim/generation 完成一次；
- publisher 在 rename 前或 rename 后 `SIGSTOP`，同时 GC/staging cleanup/recovery
  race 1,000 次：live claim 不被删，revoked publisher finalize=0，published
  dangling ref=0；
- cancel 与 incident 分别在 materialize prepare 后/rename 前、rename 后/finalize 前
  race 1,000 次：abort owner 先终止 publisher，再 cleanup；first ref=0，最终 object
  为 audited `QUARANTINED|DELETED`、staging claim non-active，Run 才可 terminal；
- 专门覆盖旧 abort actor 在 content move 前，以及 move 后/finalize 前 `SIGSTOP`：
  新 control 必须 exact terminate/wait 旧 actor 并等 kernel lock release，方可 CAS
  higher epoch；随后 reconcile、restore/publish `ACTIVE` ref，再尝试恢复旧 actor，
  证明旧 actor 已不存在、shared bytes 仍 `LIVE`、dangling ref=0。Materialize、GC、
  restore、delete actor 对同一 ownership/epoch/lock contract 各做等价 seam test；
- cancel/incident 与 verified-`LIVE` reuse ref+claim transaction race：transaction
  先赢则新 ref 可由后续 Run policy release，fence 先赢则 staging-only cleanup 且新
  ref=0；两种顺序都无 active staging claim/dangling ref；
- DB commit 后文件截断：recovery fail closed；
- 相同 digest 重放：复用同一对象；
- 相同 logical output 不同 bytes：content identity 不相等；
- workspace 文件存在但没有 committed event：不可复用；
- producer Run retention 删除后，只要 consumer import event 仍可达，artifact
  仍可读取；
- non-terminal Run 和 retained replay history 引用的 workflow/policy/Adapter-
  contract artifacts 始终是 GC roots；
- zero reachability 的精确定义是 exact object digest/generation 的
  `runtime_artifact_refs.state=ACTIVE` row count 为 0；non-terminal Run、retained
  replay history、workflow/policy/Adapter bundle、checkpoint、provenance/evidence
  与每个 snapshot consumer 都必须各自有 ref。Journal 历史行本身不作隐式 root；
  producer release 前 consumer import transaction 必须先创建 consumer ref；
- Campaign Admission Profile 在 bytes publish、Work Item ID compute、Work-Item-owned
  `ACTIVE` ref + `PENDING` handoff commit、enqueue-attempt fence、Ledger enqueue、Ledger
  receipt read-back、`BOUND` CAS 每个 seam crash/restart；始终恰一 deterministic
  ref/handoff，Ledger commit-before-bind 可收敛，PENDING/BOUND ref 期间 aggressive GC
  无法删除 bytes；
- pre-enqueue orphan 在 fixed-frontier Ledger `ABSENT` proof、exact stopped/fenced
  coordinator 令 current projection `IN_FLIGHT -> RETIRED`（保留 attempt triple），drain+
  attempt-bound frozen recovery request 的 later-frontier proof 后，若 exact
  `QUEUED_PRESENT`
  则必须以相同 Work Item/receipt/sidecar 收敛 `RETIRED -> LEDGER_PRESENT/BOUND`；若 exact
  `ABSENT` 才可 `RETIRED -> PROVED_ABSENT`，handoff 仍保持 `PENDING + ACTIVE`。专门覆盖
  first not-found → retire → old transaction commits/drains → `QUEUED_PRESENT`。同一 Work Item
  source retry 必须 append higher-generation/fence attempt 并可最终 `BOUND`。只有另有 exact
  `DistillationEnqueueObligationAbandonedProof` 且 memory Store 已 append/read-back exact
  `abandoned_before_enqueue` Ledger receipt 才可 `ORPHAN_ABSENT/RELEASED`；receipt 缺失、
  timeout、
  stale/foreign/older-attempt proof、still-IN_FLIGHT、open obligation 或 concurrent enqueue
  下 release=0；旧 attempt abandon proof 与 higher-generation current attempt 交换的
  1,000-race 中 release=0；
  abandoned receipt commit/reply-loss 由 exact `ABANDONED_PRESENT` 收敛；foreign
  Experience、Work Item payload digest、policy/profile lineage 或 abandonment proof swap
  均 append/release=0；
- source `SCIENTIFIC` Run terminal 与 projector 延迟期间 profile bytes 保持可读；
  missing/PENDING/foreign/inactive ref 阻止 record-closure，source-owned ref release 不影响
  Work-Item root；
- foreign owner、wrong Work Item/profile/object generation、tampered proof、`RELEASED`
  ref 的 queued enqueue 均拒绝；same Work Item/ref with `BOUND` proof 是 exact replay；
- source/campaign terminal 本身 release=0；terminal Work Completion 之后，campaign
  replay/audit independent ref 先 commit 或 retention-expired receipt 先 read-back，再允许
  `BOUND -> RELEASED`。保留期 replay 始终读到 bytes，所有 independent root 后续显式
  release 后 GC 才可删除；
- GC 使用 authoritative lifecycle CAS：`LIVE → MOVE_PREPARED →
  QUARANTINED → DELETE_PREPARED → DELETED`；publication/import 只能在同一
  writer transaction 观察 `LIVE` 并创建 ref。Import 先 commit 则 GC CAS 失败；
  GC 先 commit 则 import 等待 `QUARANTINED → RESTORE_PREPARED → LIVE`
  完成后再 publish，绝不在 moving state 创建 dangling ref；
- materialize/abort/GC/restore/delete DB prepare 与 filesystem rename/fsync 分开，
  且 filesystem work 只由已登记并获 one-shot authorization 的 mutation actor
  执行；逐一测试 prepare
  前、prepare 后/rename 前、rename 后/finalize 前、finalize 后 crash，recovery
  根据 lifecycle + live/quarantine paths 确定性 roll forward，未知或缺 bytes
  fail closed；
- 专门 race post-recheck/pre-move import 1,000 次，assert ref 要么先赢并阻止 move，
  要么等待 restore 后发布；restore claim 与 delete claim 不可同时获胜；
- tombstone 保留 monotonic object generation；delete 后重新产出相同 digest 必须走
  generation-CAS `DELETED → MATERIALIZE_PREPARED → LIVE`，在 publish 前重新
  校验 fsynced bytes 的 digest/size；覆盖 delete-then-reproduce 及其每个 crash seam；
- process/OS crash 后 DB published reference 不指向消失的 directory entry。

RPO=0 的故障域是 supported local filesystem 上的 process/OS/power-loss model，
依赖 SQLite `FULL`、file+directory fsync 和诚实的 storage flush。物理介质损坏、
控制器谎报 flush、全盘丢失需要备份/复制，超出 v1 RPO 声明。

### 7.3 Process ownership and cancellation

`LocalSubprocessAdapter` 先有 durable invocation，再在新 session/process group
创建 gated shim；真实任务只能在完整 ownership identity（PID、process-group/
session ID、OS process start time、executable 与 run/Activity/effect/invocation
markers）持久化后启动，并在 signal 前重新验证以防 PID reuse。V1 支持 macOS/Linux POSIX
process sessions；Windows Job Objects 不在
本次范围。普通 `CancelRun` 的顺序是 durable cancel intent → revoke fence → TERM
process group → bounded grace → KILL process group → reconcile → terminal transition。
若存在 unresolved Intent/Recall/Distillation authorization，则第一步改为 durable
`PENDING_AFTER_ARBITRATION` + close-new-work gate，**不** revoke exact attempt fence、也不
进入这条 TERM 顺序；先 reconcile its success/no-commit。只有 resolution 真正进入
`CANCELLING` 时才 revoke execution fence 并开始 TERM/KILL；若
`TOO_LATE_COMMITTED`，不得用 cancellation path 杀掉已提交 work 的 terminalization。

`run_owned_execution_cancellation_latency` 从 client 调用 `apply(CancelRun)` 前一刻的
monotonic timestamp 开始，到 ownership registry/backend query 证明
全部 Run-owned task/thread/process-group/container 已停止且对应 reconcile event
commit 为止，必须 ≤10 秒；它包含
command acceptance、fence、TERM grace、KILL 和 commit。Local-only case 的
`CANCELLED` transition 随后必须在 inspect visibility SLO 内可见。无法查询的
remote effect 正确进入 `WAITING_INPUT`，不得拿它当已完成 cancellation sample。
`PENDING_AFTER_ARBITRATION` case 单独报告 arbitration latency；10 秒 local cleanup SLO
从 resolution 进入 `CANCELLING` 的 event commit 开始，不能把 pending 当已取消或用它
规避最终 cleanup SLO。

In-process Adapter 只允许 short/bounded/cooperative work，并有 enforced timeout；
可能阻塞超过 progress deadline 的 Activity 必须在 owned subprocess/container
隔离。Subprocess 使用 create-gated launcher shim：durable invocation 已存在后，
shim 以 run/Activity/effect/invocation markers 启动但在 parent 持久化 PID/PGID/
start time 并发出 one-shot authorization 前不得 exec；parent crash/EOF/timeout 时
shim 自行退出。Docker 使用 `create → persist ownership → start`，持久化 container
ID、engine identity、run/Activity/effect/invocation labels、nonce 与 creation time；
crash after create 通过 unique labels discover/reconcile，控制前也按 labels 重验
ownership，并实现 query/checkpoint-if-native/stop/kill/reconcile；只杀 `docker
run` CLI 不算取消 container。

Artifact filesystem-mutation actor 复用同一 exact-process ownership primitive，
但另有 object generation + operation nonce + mutation epoch 和
per-object-generation kernel lock。Higher-epoch takeover 必须先 kill/wait prior
exact actor 并观察 lock release，不能只靠数据库 fencing token 假设已暂停的旧
进程不会继续做 filesystem I/O。

验收：

- child 产生 grandchild 且两者忽略 TERM，10 秒内均不存在；
- cancel 与 Activity commit race 由 SQLite transaction order 决定；Cancel 若先
  commit 会 revoke fence，Activity 若先 commit 则 Cancel 针对新的 current state；
- `CANCELLED` 后任何迟到 receipt/commit 都被拒绝；
- non-queryable remote effect 未解决时保持 `WAITING_INPUT`，不得伪造
  `CANCELLED`；typed operator abandon 必须进入
  `FAILED(remote_outcome=UNKNOWN_ABANDONED)`，不得进入 `CANCELLED|COMPLETED`
  或生成 scientific outcome；side-effect-free `REEXECUTABLE` abandon 仅在当前
  fence 证明 late bytes 不可 select/commit 时允许标 `REEXECUTABLE_NO_COMMIT`；
- 非本 Run 拥有的 PID/process group 绝不发送信号；
- executor crash 后新 executor 可重建 process ownership 或进入安全 reconcile；
- subprocess 在 shim spawn、ownership persist、start authorization、exec 各 seam
  crash 后都不留下 unowned real workload；
- Docker 在 create、ID persist、start、stop/kill 各 seam crash 后能按 invocation
  labels 唯一 reconcile；同 Activity 多次 invocation 不串容器；非 owned/label
  mismatch container 绝不 stop/kill；cancel 后 container 不再运行。

### 7.4 Checkpoint-policy conformance

每个 Activity 必须声明且只声明 `RESUMABLE | RESTARTABLE | RECONCILE_ONLY |
NON_RESUMABLE` 之一：

- `RESUMABLE` 的 content-addressed resume token 绑定 Activity/input/checkpoint
  schema digest；缺失、截断、错 scope/token 时 fail closed，绝不从伪 cursor 继续；
- `RESTARTABLE` 必须经 review 证明所有 Effects 使用稳定 identity 且没有不可重做
  的 unresolved side effect；
- `RECONCILE_ONLY` 在 outcome ambiguous 时只能 query/reconcile，不能 redispatch；
- `NON_RESUMABLE` 在中断后进入 `WAITING_INPUT`，不能伪装自动恢复。

预计超过 5 分钟的 Activity 必须有 semantic progress cursor，并且为
`RESUMABLE` 或显式 reviewed `RESTARTABLE`；contract loader 对不满足者拒绝启动。
测试覆盖 valid/corrupt/cross-Activity resume token、checkpoint 前后 crash、pause/
stall resume、reconcile-only 禁止重发，以及一个 >5 分钟 non-cooperative fake 被
拒绝/隔离。

## 8. Retry 与 Budget Envelope

### 8.1 One retry owner

所有 retry policy 位于 Long-Task Runtime Module。Stage Adapter 可以返回 typed
error 和 provider `retry_after`，但不能有不可见的无限 retry。第三方 client 的
自动 retry 必须关闭；只有 SDK hook 能在每次物理请求前回调 Runtime、先建立独立
invocation row 与 reservation 时才可启用。事后只给 aggregate retry/cost
accounting 不满足契约。

### 8.2 Classification tests

| 注入 | 预期 |
| --- | --- |
| LLM 429 / 5xx / timeout | 同 Activity/logical effect key、新 invocation/reservation、bounded backoff + deterministic jitter |
| auth/permission | `WAITING_INPUT` 或 policy failure；不消耗全部重试 |
| invalid Intervention schema | contract failure；不开 infrastructure retry |
| training non-zero exit | 按 exit taxonomy retry 或完成失败 Observation |
| failed scientific metric | 保留 Observation；policy 决定是否新建 Attempt |
| evaluator timeout | 进入 bounded retry/wait；不得转为 `COMPLETED` |
| evaluator invalid output | 不生成 valid Verification Record；不得转为 `COMPLETED` |
| ambiguous non-queryable effect | `WAITING_INPUT` |

### 8.3 Reservation tests

- dispatch 前必须 reserve，receipt 后 settle；
- 同一 logical effect 的每个 physical `invocation_id` 都单独 reserve/account；
- ambiguous/fenced-out invocation 保留 worst-case reservation，只有
  confirmed-not-executed 或 final usage 才释放/结算；
- typed operator abandon 对 unresolved invocation 必须把 held worst case 幂等
  settle 为已消耗，绝不释放；在 abandon commit 前后 crash/replay 均只 charge 一次；
- crash between reserve/effect/receipt/settle 的重放不重复收费或漏收费；
- attempts、calls、tokens、wall、GPU 的 settled + open reservations 不可突破
  admission cap；external-spend cap 只对有 enforceable request limit 的 Adapter
  声明；
- attempt-scoped invocation 必须同时通过 Run effective cap 与其 immutable
  Attempt allocation；reserve/settle 在两个 ledgers 原子记账，retry/takeover
  不得借用另一 Attempt 的 allocation，run-scoped snapshot/decision work 只记 Run
  ledger 但仍进入 campaign total；
- budget amend 需要 optimistic version，作为 append-only effective-cap overlay；
- 减少后的 cap 低于 settled usage 时拒绝；
- 减少后的 cap 低于 settled + open reservation 时也拒绝；
- 已创建 Experiment Attempt 的 allocation 不可修改；
- `max_attempts=3` 允许 1 或 2 次后 early stop；
- budget exhausted 的 terminal/wait behavior 由 frozen policy 决定。

## 9. Stage Continuation contract

### 9.1 Pure planning tests

`tests/test_runtime/test_stage_continuation.py` 使用 table/property tests：

- 相同 canonical request 重放 10,000 次，plan bytes/digest 完全相同；
- canonical request 必含 immutable spec 中的 workflow 和 continuation-policy
  artifact ref/version/digest；resolver 交付 digest-verified bytes，部署新 policy
  不改变 in-flight Research Run；
- planner 无 clock、random、filesystem、network、model 或 store access；
- 每个 non-terminal state 恰好得到一个合法 next action；
- action dependency digest 完整包含 scope inputs；
- workflow/continuation-policy digest pinning 后，部署新版本不改变 in-flight
  Research Run；
- 非法历史或 impossible state 返回 `ContractViolation`，不猜测下一步；
- budget、pause、cancel、retry time、operator input 都能产生 `Wait/Terminal`；
- 等待时间经过但无新 durable timer event 时 plan 不变；提交
  `TimerFired/DeadlineReached/BudgetExpired` 后才允许推进；
- backoff jitter 只由 stable identity + policy version 派生；
- planner 本身不 dispatch，也不修改 snapshot。

### 9.2 Stage scopes

V1 stage graph：

```text
run scope:
prepare → survey → method_review → freeze_context

run decision scope（尚不创建新 Hypothesis/Attempt）:
diagnose → intervention_plan（包含 Hypothesis/Intervention validation）

attempt scope（仅在 Intervention/seed/allocation/contract 固定后打开）:
materialize → execute → verify → reflect → record → distillation_receipt
```

Contract suite 同时跑 `ProvidedIdeaStagesAdapter` 和
`ReferenceIdeationStagesAdapter`。在无 fault、三次 actual Attempts 场景：

- `prepare`、`survey`、`method_review`、`freeze_context` executor count 各为 1；
- hypothesis decision cost 在 admission/settlement 上只进 Run ledger，因为当时
  Attempt 尚不存在；报告时可归因到它最终打开的 Attempt path，但不消耗或改写
  immutable Attempt allocation。未打开 Attempt 的 proposal cost 仍计入 Research
  Run/campaign 总成本，不能隐藏；
- 新 Hypothesis 与其首个 Attempt 在同一 transition 创建；validation/cancel 在此
  之前不会留下 zero-Attempt Hypothesis 或 partial Attempt；
- `OpenExperimentAttempt` 携带完整 immutable AttemptSpec：Attempt ID、Run/spec
  digest、exact snapshot generation/ref/digest、source/dataset identities、
  Hypothesis ref/payload、Intervention、seed、allocation、Evaluation Contract、
  content-addressed decision-input/Recall Context artifact ref/digest/citations、
  environment/code/container/model/tool config 与 Intervention
  Catalog digests；缺一项即 contract failure；snapshot supersede 后旧 Attempt
  仍绑定旧 generation，新 Attempt 必须显式绑定新 generation；
- materialize/execute receipt 与 Trial Provenance 必须逐字段匹配 AttemptSpec 的
  canonical AttemptSpec digest，并覆盖 Run/snapshot、Hypothesis、Intervention、
  seed、allocation、Evaluation Contract、decision-input/Recall/citations、source/
  dataset、environment/code/container/model/tool 与 Intervention Catalog digests；
  任一 mismatch 使该 Attempt contract-invalid，不能生成 valid Observation 或
  `COMPLETED`，改变执行条件只能新建 Attempt；
- attempt-scoped executor count 与 actual Attempts 一致；
- infrastructure retry 不增加 Experiment Attempt count；
- 每个 committed Attempt 恰好一个 Intervention、Trial Provenance、Observation；
- execution receipt 后 Trial Provenance 与 Observation 必须原子 commit；Verifier
  同时校验二者与 AttemptSpec，任何 crash prefix 都不能看到/验证无 provenance
  的 Observation；
- valid Verification Record 的 `passed=true/false` 都绑定精确 Observation 和
  contract digest；invalid evaluator output 不生成 valid record；
- Attempt 一旦打开，执行前取消也产生 typed cancelled Observation 和完整 Trial
  Provenance；若在打开前取消，则不创建伪 Attempt；
- Experience Record、每个 Run-owned Intent 的 Recall Decision Outcome 和每个
  completion-required Experience 的 Experience Distillation Receipt 重放不重复；
  receipt 可 queued/deferred/not-required，或 proof-authorized
  `abandoned_before_enqueue`。后者必须覆盖 frozen Work Item/Experience/policy/profile
  lineage、abandonment proof、Ledger receipt independent read-back、reply-loss
  `ABANDONED_PRESENT` reconciliation 和 release=0 mismatch matrix；它不创建 Work Item。

### 9.3 Snapshot content test

Research Context Snapshot digest 必须包含：

- normalized task request；
- input references 和 source identity；
- dataset/split identity；
- method review；
- workflow/model/tool configuration digests；
- sanitized actor-visible `DecisionContractView` ref/digest。

必须排除：

- Recall Context；
- treatment/control arm identity（除非它本身是合法 task input）；
- full/private Evaluation Contract digest、evaluator identity；
- private evaluator label/answer；
- prior Attempt mutable workspace；
- process path、PID、timestamps、retry counters。

Snapshot content digest 保持内容寻址；另算 `reuse_governance_digest`，包含 tenant/
security boundary、data classification、source export、evaluator privacy、storage
locality、retention 与 execution-isolation policy。Build Claim 使用两者组合；import
同时验证 producer export 与 consumer admission，不能因为 content digest 相同而
越权。

用 secret canary 分别放入 private evaluator data、Recall Context 和旧 workspace；
snapshot bytes、digest、引用图中 canary 出现次数必须为 0。

Reuse-governance matrix 必须证明：same content + same governance 只建一次；不同
tenant/isolation domain 不共享 Claim；producer `no-export` 时 consumer import=0；
consumer 更长 retention 只能延长引用寿命，不能放宽 producer restriction；
cross-arm import 只有 actor-visible DecisionContractView 完全相同，且由 full
Evaluation Contract 派生的两侧 reuse-governance policy 都显式允许时成功。每个
import/denial event 均绑定 producer/consumer policy digests，policy race 以事务内
版本为准。

### 9.4 Invalidation tests

| 变更 | 预期 executor 变化 |
| --- | --- |
| task/references/source/dataset/workflow/model-tool config | 新 Research Run；旧 spec/snapshot 不变 |
| retention/export/privacy/locality/isolation policy | 新 Research Run；content digest 可相同，但 governance compatibility 未通过时必须另建 Claim 且不得 import |
| full Evaluation Contract version/semantics/evaluator identity | 新 Research Run；v1 不原地 re-verify completed run；只有 actor-visible DecisionContractView 相同且 governance 允许时才可复用 actor snapshot |
| corrupt/invalid derived snapshot under the same pinned spec | 新 snapshot generation；按 stage input digest 复用仍有效上游 |
| method family / main Hypothesis under same request | 新 decision 与 Hypothesis；只有 frozen snapshot scope（含 source/method-review inputs）仍 exact 才可复用，若新 source/contract 必需则新 Research Run |
| Recall Context / proposed Intervention before Attempt open | snapshot 不变；Hypothesis decision 重算 |
| Intervention after Attempt open | 新 Experiment Attempt；旧 Attempt 不变 |
| seed / Attempt allocation | 新 Experiment Attempt |
| reflection/Experience-ingestion/distillation policy | v1 新 Research Run；old records/Attempt evidence 不变，不得把 deployed default 应用于 in-flight Run |

每格至少包含正例、反例和 digest assertion。不能只检查目录是否存在。

每个 stage contract 还必须通过 reuse-policy 测试：只有
`prepare/survey/method_review/freeze_context` 可声明 `SNAPSHOT_IMPORTABLE`；
`diagnose/intervention_plan` 必须是 `RUN_LOCAL_REPLAY_ONLY`，只在同一 Run/
generation 且 Recall/decision-input digest 相同时 replay，变更即重算；
Attempt-scoped materialize/execute/verify/reflect/record/distillation-receipt 一律
`NEVER_REUSE_AS_NEW_ATTEMPT_EVIDENCE`。即使 bytes/input digest 相同，也不能把
旧 Observation、Verification 或 Experience Record 绑定到新 Attempt。

### 9.5 Crash continuation assertions

- prepare 后 crash：从 survey 开始；
- survey 后 crash：从 method review 开始；
- snapshot artifact `MATERIALIZE_PREPARED` 后、install/finalize 前 crash：按 exact
  staging/object generation 只发布一次；
- execute success、receipt 前 crash：按 effect capability reconcile；
- Trial Provenance + Observation atomic commit 后 crash：只 verify；
- Verification Record 后 crash：只补 Experience、缺失的 per-Intent Recall Outcome 和
  per-Experience receipt；
- Experience Record 后 crash：只补缺失的 per-Intent Recall Outcome、对应 receipt 和
  terminal；
- 最后一个 required Experience Distillation Receipt 后、operational settlement barrier
  前 crash：先清算 invocation、
  reservation、owned work、artifact staging/materialization、Run-owned artifact
  filesystem-mutation actor 与 Snapshot Build Claims，再 terminal；
- terminal CAS 与 late receipt/reconcile/abandon race：只有一个 event-seq/fence
  顺序；另与 artifact finalize/staging cleanup/Build Claim publish race，terminal
  snapshot 绝不含 open reservation、未 final invocation 或 active Run-owned claim；
- terminal 后 crash/restart：零新 Activity。

## 10. Fault-injection matrix

### 10.1 Semantic kill points

每个 semantic stage 和其中每个 effect occurrence 覆盖所有适用 kill seams：

1. Activity claim 前；
2. claim commit 后、Activity start 前；
3. `ActivityStarted` 后；
4. `EffectPrepared` 后；
5. invocation create/reserve/`DISPATCHABLE` commit 后、`DISPATCHED` 前；
6. `DISPATCHED` commit 后、external call boundary 前；
7. remote success 后、evidence/receipt 前；
8. evidence inbox append 后、canonical receipt/settlement 前；
9. canonical receipt 后、artifact staging claim 前；
10. staging claim 后、temp write/digest report 前后；
11. `MATERIALIZE_PREPARED` 后、content-addressed install rename 前后；
12. install fsync 后、`LIVE` + first-ref finalize 前；
13. transition commit 后、next plan 前；
14. materialize/abort/GC/restore/delete lifecycle prepare、mutation-actor identity
    persist、one-shot authorization、filesystem rename/fsync 与 finalize 各 seam；
15. terminal settlement check 与 late evidence/reconcile/abandon/artifact
    finalize/staging cleanup/Build Claim publish 并发。

CI 从 machine-readable coverage manifest 生成
`stage × effect occurrence × applicable seam × capability × seed`。Manifest 必须
列出每个 N/A seam 的理由；multi-effect stage 逐 effect 注入，不能每 stage 只
测第一个。总 scripted cases 不少于 9,600；这个数字是 coverage floor，不是假设
每个 stage 都适用上列全部 15 个 seams。

所有 cases 的 hard safety assertions：

- lost confirmed stage = 0；
- duplicate logical commit = 0；provider-side physical invocations 可因
  at-least-once 出现多个，但每个必须有 invocation identity 和预算记录；
- duplicate Experiment Attempt = 0；
- duplicate Verification/Experience/Recall-Decision-Outcome/
  Experience-Distillation-Receipt record = 0；
- false `COMPLETED` = 0；
- stale fencing commit accepted = 0；
- terminal Run 的 open reservation、non-final invocation、Run-owned task/thread、
  process group、container、未释放 Run-scoped role assignment 数量均为 0；共享
  service role 不计；in-process cooperative fake 覆盖
  takeover/timeout → terminal race；
- terminal Run 的 active artifact staging/materialization claim 与 active Snapshot
  Build Claim 数量均为 0，Run-owned artifact filesystem-mutation actor 数量为 0；
- committed artifact ref 指向 non-`LIVE`/missing bytes 的数量为 0；
- higher-epoch artifact takeover 未先 exact terminate/wait prior actor 或未观察
  per-object-generation kernel lock release 就获权的数量为 0；
- artifact actor 未在每个 rename/unlink/fsync 前重验 durable operation/epoch 与
  one-shot authorization 却执行路径变更的数量为 0。

对 manifest 标为 eligible-recoverable 的 case，fault-free 与 recovered 的
`scientific_outcome_digest` 必须相同。该 digest 只包含 frozen spec、snapshot
content、ordered Hypothesis/AttemptSpec IDs+digests、Trial Provenance、scientific
artifacts、Observation、effective Verification、Experience Record、ordered per-Intent
Recall Decision Outcome 与 ordered per-Experience Experience Distillation Receipt
digests；不包含 event sequence、
lease epoch、retry count、timestamps 或
fault overhead。恢复历史反而必须包含预期 fault/retry evidence。对
`NON_RECONCILABLE`/permanent faults 使用 `correctly waited/failed` oracle，不要求
terminal projection 与 fault-free 相同。

永久错误和 `NON_RECONCILABLE` ambiguous effect 的正确结果是
`FAILED/WAITING_INPUT`，不是强行“自动恢复成功”。

### 10.2 Process/storage/provider faults

Nightly/acceptance 追加：

- real `SIGKILL`、`SIGSTOP`、two-recoverer race；
- SQLite busy、forced rollback、disk full、WAL recovery、schema mismatch；
- artifact truncation、checksum mismatch、read-only filesystem；
- LLM/tool 429、5xx、timeout、auth error、connection lost after success；
- Docker/training checkpoint corruption and preemption；
- cancel at every commit seam；
- store clock shift and worker scheduling pause；
- duplicate/out-of-order notification delivery。

### 10.3 Statistical recovery claim

Deterministic canonical suite 只证明 conformance，不计算总体置信区间。另冻结
`recoverable-fault-profile-v1`：明确 fault classes、stage/effect/seam sampling
frame、类别权重、seed 和 eligibility rule。权重优先来自 Phase 0 telemetry；若
数据不足而采用 equal-weight stress profile，对外结论必须限定在该 benchmark
profile，不能外推“一般故障”。

V1 的 60 秒 RTO/automatic-recovery profile 只纳入同一 OS boot 内、monotonic
clock 连续的 worker/process/provider transient faults。OS reboot/power-loss 仍必须
通过 RPO/replay safety；只有 startup UTC sanity 在 manifest bound 内的 timer 才
可自动 reconcile，`ClockUncertain` 正确等待不计 automatic recovery，也不得从
all-fault disposition 分母删除。

从冻结 profile 独立随机抽取 100 个 real-process runs。发布要求 100/100 的
scientific outcome 与 terminal disposition 正确；其 two-sided 95% Wilson lower
bound 约为 96.3%。允许的公开表述仅是：“在预注册
recoverable-fault-profile-v1 中，自动恢复率至少 95%（95% confidence）”。

同时对全部 fault cases 报告 `automatic recovered / correctly waited /
correctly failed / unsafe`，以 all-fault 为分母；需要人工的 effect 不得从该分母
删除。`unsafe` 必须为 0。

## 11. Reliability and performance gates

在固定本地 SSD runner 上记录原始样本、p50/p95/p99 和 bootstrap CI：

| Metric | Hard gate |
| --- | ---: |
| committed Durable Transition RPO | 0 |
| fault timestamp → loss detected，TTD p95 | ≤ 45 秒 |
| detected → valid takeover lease p95 | ≤ 10 秒 |
| fault timestamp → first new semantic continuation event，RTO p95 | ≤ 60 秒 |
| checkpoint/transition commit p95 | ≤ 50ms |
| checkpoint/transition commit p99 | ≤ 100ms |
| inspect event visibility p95 | ≤ 1 秒 |
| runtime metadata / 1,000 transitions | ≤ 5 MiB |
| runtime-only no-fault wall overhead median | each-stratum UCB95 ≤ 3% |
| runtime-only no-fault wall overhead p95 | each-stratum UCB95 ≤ 5% |
| Run-owned execution cancellation（API call → stopped + reconcile commit） | every eligible sample ≤ 10 秒 |

除 overhead bootstrap 另有规定外，quantile 一律使用全部预注册样本排序后的
nearest-rank `x[ceil(q·n)]`（1-based），同时报告 p50/p95/p99 与 percentile
bootstrap CI；Hard gate 看 empirical nearest-rank，不允许删除 warmup 后的 timeout、
retry 或慢样本。Sample order、stratum weights、warmup count、poll interval、runner
identity 和 raw monotonic timestamps 在运行前进入 manifest。具体最小 frame：

- TTD/takeover/RTO 使用 §10.3 冻结 profile 的全部 100 个 randomized real-process
  Runs；正确等待/失败仍进入 all-fault report，但只有预注册 recoverable cases 进入
  RTO quantile；
- commit p95/p99 使用 1,000 次不计入结果的 warmup 后至少 10,000 个 measured
  Durable Transitions，按 Phase 0 production trace 的 command/stage/effect/timer
  strata 冻结权重；无 telemetry 时四类 equal-weight，并披露该 stress profile；
- inspect visibility 使用同一 measured transitions 中至少 10,000 个 commit-return
  points，以固定 20ms interval 从独立 authenticated client 轮询，到首次返回包含
  target event sequence 为止；poll/IPC error 和 deadline 都保留为慢/失败样本；
- cancellation 至少 300 个 local eligible cases：cooperative in-process task、
  POSIX subprocess group、Docker container 各至少 100，且均衡覆盖预注册 cancel
  seams；从 §7.3 的 API 前 timestamp 到 zero Run-owned execution + reconcile commit，
  每一个样本都必须 ≤10 秒。不可查询 remote ambiguity 不混入该 local latency
  distribution，而按 `WAITING_INPUT` 单列且不能声称 completed cancellation；
- process-cold import 使用 §4.2 的 1,000-process frame；
- metadata gate 从 fresh initialized/READY store 的基线开始，执行 manifest 中固定
  mix 的恰好 1,000 个 transitions；前后都成功执行
  `PRAGMA wal_checkpoint(TRUNCATE)`。Byte value 是 main DB、`-wal`、`-shm`、
  status/cohort/writer-marker 等 manifest-enumerated Runtime metadata files 的
  `stat.st_size` 总和之差；包含 event/projection/index/artifact-metadata rows，排除
  content-addressed payload bytes、workspace 和 logs。Checkpoint busy、文件漏列或
  final delta >5 MiB 都失败。

RTO 从注入 fault timestamp（真实故障则从最后一次可证明存活的边界）开始，
包含 launcher restart、检测、takeover 和第一条新 semantic continuation event；
它不伪装成“长训练已瞬间完成”。TTD 和 takeover latency 也单独报告。

Runtime overhead 的 paired comparator 固定为 `legacy-minimal-harness`：它不写
durable journal/lease，但执行与 durable Runtime 完全相同的 frozen
Activity/effect sequence、scripted Adapter calls，并写出 byte-identical artifacts；
durable arm 关闭 continuation reuse。artifact strata 固定为 4 KiB、1 MiB、64
MiB，concurrency=1。每个 stratum 先跑 100 pairs warm-up，再跑至少 1,000
measured pairs；每 pair 使用同一 trace/seed，按预注册、平衡随机的 AB/BA 顺序
交错，不能并发。

每个 pair 使用由同一 fixture 预创建的 fresh arm directories；schema migration、
launcher/control/executor startup/readiness、fixture copy 与 pair teardown 在计时外，且另行
报告 startup 指标。单个 `duration_ns` 的起点是 harness 把同一 ready Activity/
effect sequence 交给 arm 的前一刻；终点是 artifact bytes/file+directory fsync
完成，并且该 arm 的 completion bookkeeping 返回。Durable arm 的计时因此包含
claim/lease/fence、invocation reserve/dispatch/receipt/settle、event/projection/
outbox commit 和 SQLite `FULL` sync；legacy comparator 包含同一 Adapter calls 与
artifact fsync，但没有 durable journal。DB checkpoint、process teardown 不在
quantum gate 内，必须单独报告，不能在计时前预提交任何被测 transition。

对 pair `i` 定义 `h_i = (durable_ns_i - legacy_ns_i) / legacy_ns_i`。每个
stratum 分别计算 `median(h)` 与 empirical `p95(h)`，再用 paired bootstrap
（bootstrap statistic 的 95th percentile，固定 10,000 replicates 和 manifest
seed）得到各自 one-sided 95% upper confidence bound。三个 strata 必须各自
满足 `UCB95(median) ≤ 3%` 且 `UCB95(p95) ≤ 5%`；不得 pooled，也不得只用点估计
过 gate。计时边界、trace digests、artifact bytes、order assignments、raw `ns`
样本与 bootstrap seed 全部写入 manifest。端到端 continuation 节省只计入 G7，
不能掩盖 journal/lease 本身的开销。

24 小时 soak 使用写入 manifest 的固定 seed 和持续 scripted workload；至少每
30 分钟执行一次 role kill（≥48 次，executor/control/launcher-only 各≥16），并按冻结 schedule 注入 SQLite busy、
provider delay、短时网络和磁盘压力。每 30 秒采样 RSS、open FD、owned process
count、WAL bytes、unreachable/quarantined artifacts。warm baseline 固定为
第 30–60 分钟的样本，final window 固定为最后 30 分钟；slope window 固定为第
60 分钟至 24 小时结束。GC 配置固定为 unreachable mark grace 10 分钟、
quarantine grace 10 分钟，并写入 manifest。必须做到：

Workload 不能空转：24 小时内至少接受 100,000 个 Durable Transitions、形成至少
1,000 个 terminal scripted Research Runs，并完成全部 ≥48 次 role-kill recovery；
除预注册 fault 后的 60 秒 recovery window 外，每个 rolling 5-minute window 至少
commit 100 个 semantic transitions，生成器持续补充 ready Runs。任一 worker kill
未在 RTO gate 内产生新 semantic continuation，或最低 workload 未达到，G9 失败。

资源由独立于被杀 role 的 monitor 按 launcher + control + current executors +
owned children/containers 的 lineage 采样；确认该集合为空时记 0 并标注 restart
gap。缺失样本
不能插值：连续缺失 >2 个 intervals 或总缺失 >1% 直接失败，其他缺失仍从 raw
series 排除并报告 denominator。所有 slope 使用前述 60-sample moving-block 方案。

- 无人工修数据库或删除文件；
- false completion、duplicate logical commit、corrupt committed history 均为 0；
- store 可 replay；
- 每个 `COMPLETED` Research Run 均有完整 completion-required
  Verification/Experience、per-Intent Recall-Decision-Outcome、per-Experience
  Experience-Distillation-Receipt 证据链；`FAILED/CANCELLED`
  有完整 typed failure/control provenance；
- slope window 内 RSS Theil–Sen slope 的 one-sided moving-block bootstrap
  （30 秒采样、60-sample block、10,000 replicates、manifest seed）95% upper bound
  ≤1 MiB/hour，且 final-window p95 ≤ warm-baseline p95 ×1.15；
- open FD 和 owned process count 各自的 Theil–Sen slope 同口径 one-sided
  moving-block bootstrap
  95% upper bound ≤0.05 count/hour，且 final-window p95 ≤对应 warm-baseline
  p95 +2；
- 在固定 soak elapsed hour 1/6/12/18/24，launcher 暂停新 claims、给正在提交的
  transaction 最多 5 秒 drain（该 gap 仍计入 soak），随后由 control 执行
  `PRAGMA wal_checkpoint(RESTART)`；`SQLITE_BUSY`/timeout 直接失败。Checkpoint
  返回后、新 transaction admission 前立即读取 main SQLite file 与 `-wal` 的
  `stat.st_size`；这里 `database bytes` 专指该时刻 main DB apparent file bytes，
  每个 checkpoint sample 都要求 WAL bytes ≤ max(64 MiB, 2×database bytes)，
  原始返回 tuple/bytes/timestamps 全部归档；
- final window 内，mark age >10 分钟或 quarantine age >10 分钟的 artifact
  count 均为 0；
- 非恢复 fault 停在预期 typed state。

## 12. Efficiency acceptance

### 12.1 Hard campaign gate

输入：一个 campaign 内 10 个 distinct Research Runs（V2 报告把该单位标为
`trial`），其 Research Context Snapshot scope 完全相同。每 Run
`max_attempts=3`，模型、工具、contract、dataset 和输出上限冻结；从 cold
shared cache 开始，producer Run 的全部 snapshot cost 计入 campaign。十个 Runs
还必须具有同一、允许 import 的 `reuse_governance_digest`；不得靠放宽
security/retention/isolation policy 通过效率 gate。

Phase 0 baseline manifest 冻结 call/token normalizer。一个 call 是一次 outbound
physical model invocation，不因 price、cache、local execution 或 retry 变成 0。
`total_llm_tokens` 对每次调用相加 normalized input 与 normalized output；cached/
uncached input、visible/reasoning output 各自形成不重叠 partition，每个 token 只
计一次。保留 provider 原始 cache-read/cache-write/reasoning 字段用于成本分析但
禁止重复相加。Local Adapter 使用
manifest 固定 tokenizer；usage 缺失或无法按同一 normalizer 重建则 G7 失败。

Benchmark 的 campaign 全局 Research Run concurrency 固定为 1：第一个
producer Run terminal 后立即提交第二个，依次直到第十个；per-Run Activity
parallelism 也固定为 1。`campaign_serial_wall_minutes` 从第一次
`apply(DriveRun)` 调用前的 monotonic timestamp 开始，到第十个 Run terminal
transition commit 后结束。它包含 command acceptance、snapshot build/import、
全部 model/tool、retry/backoff、training、verification、record/distillation-receipt、worker
启动或重启及队列空隙；自动 benchmark 不允许 operator pause。任一 Run 进入
`FAILED`、`CANCELLED`、`WAITING_INPUT`，或未在 90 分钟内 terminal，G7 直接失败，
不得从分母删除。吞吐唯一公式为
`throughput_runs_per_hour = 10 × 60 / campaign_serial_wall_minutes`。

必须同时满足：

- 每个 actual Attempt 对应的 decision+execution path 的所有 outbound physical
  model invocations ≤ 7，包括 generation、repair、verify、reflect、client/provider
  retry、zero-price、cache-hit 和 local-model invocation；未打开 Attempt 的
  proposal calls 仍计入 campaign。Billing status 只作为独立成本字段，不能改变
  call count；
- snapshot build calls ≤ 45，单独记账且 campaign 只真实执行一次；其余 9 个
  Runs 各提交一个 `StageReused`/snapshot-import receipt；
- 首个 unamortized Research Run：calls ≤ 66、tokens ≤ 650k、serial wall ≤23 分钟；
- total LLM calls ≤ 255；
- total LLM tokens ≤ 2.5M；
- serial wall time ≤ 90 分钟；
- `throughput_runs_per_hour ≥ 6.5`；
- 相对旧 1,335 calls 减少 ≥ 80%；
- 无 fault cell 的 run-scoped stage logical commit 各 Run 恰好一次、真实
  executor 全 campaign 各为 1；
- no hidden provider/client retries outside accounting；
- G8 scientific noninferiority 必须由其独立、powered corpus 通过；不能用这
  10 个 same-scope Runs 估计 2 pp CI。

255 calls 来自保守预算 `45 snapshot + 10 × 3 × 7 attempt calls`。它不是通过
删 trace、截断 evidence 或降低 evaluator 标准实现。

### 12.2 Required reporting

同一报告必须展示：

- 第一个 Research Run 的 unamortized calls/tokens/wall；
- 10 个 Research Runs 的 amortized totals 和 per-Run mean；
- snapshot 和 attempt work 各自成本；
- actual Attempts 分布与 early-stop reason；
- calls、tokens、tool time、training/GPU time、verification time；
- provider 报告的 input、output、reasoning、cache-read/cache-write tokens，及
  每个 physical invocation；normalized total 按冻结的 non-overlap token
  partition 计算，货币 billing 另表报告；
- cache hit/reuse 的 scope digest 与 artifact IDs；
- invalidated work 和原因。

只报告 amortized 数字或只报告“cache hit rate”均不通过。

### 12.3 Stretch gate

- campaign calls ≤ 133（相对 1,335 至少下降 90%）；
- campaign tokens ≤ 1M（即 mean ≤100k/Run）；
- snapshot build ≤ 12 calls，且 attempt ≤ 4 calls；或预注册的 early-stop 分布
  数学上满足同一上限；
- 若使用 12 snapshot + 5 calls/Attempt，则 total Attempts ≤24、mean ≤2.4；
- 若用满 133 calls，平均 tokens/call 还必须 ≤7,519，因此必须另有 context/output
  compression，不能只靠 early stop；
- Hard scientific gate 不退化。

Stretch 未通过时，对外表述为“达到 ≥80% call reduction hard gate”，不能四舍五入
成“数量级下降”。

## 13. Scientific noninferiority and capability experiment

### 13.1 Runtime/Continuation release experiment

采用 2 × 2：

```text
legacy vs durable Runtime
  ×
no injected fault vs pre-registered recoverable faults
```

先用至少 30 个隐藏任务 × 3 seeds 做 blinded pilot，覆盖至少三个 task
families，以估计 paired discordance、task 内相关性和成本。Pilot tasks 与正式
corpus 完全不相交，且不能通过正式 2 pp gate；正式 task-family quotas 在 pilot
unblinding 前冻结。Primary endpoint 是预注册 primary seed 上 Run-level
`scientific_outcome == VALID_PASS` 的 paired risk difference；`FAILED`、
`CANCELLED`、`WAITING_INPUT`、missing 和 invalid 均按 intention-to-treat 计为 0。
terminal-valid rate 和另外 seeds 是 secondary endpoints。

正式 corpus 是新的 hidden task set，且与 pilot、G7 efficiency campaign 完全
不相交。N 个 task-primary-seed pairs 每个都运行全部四个 cells，并在 task block
内以 manifest 预生成的平衡随机顺序执行。Fault cells 的 legacy/durable pair
使用相同 `fault_case_id`、normalized semantic seam 和 injection trigger；trigger
以 committed semantic event/effect ordinal 定义，再由预注册 mapping 映射到两个
workflow，禁止按任意 wall-clock timing 注入。无 fault cells 使用配对的
`NO_FAULT` assignment。task pair set、family quota、cell order、fault assignment
和 semantic mapping 都在结果 unblinding 前冻结。

每个 task × cell 使用 fresh isolated runtime root、journal、workspace、shared-work
namespace 和 model/tool cache namespace，从同一个 read-only cold-cache fixture
克隆；cell 间禁止 snapshot import、artifact/workspace reuse 或 provider cache
carry-over。`reuse_governance_digest` 包含 experiment/cell isolation identity。
Fault cell 必须实际到达并触发其 assigned seam；若因流程未到达则该 pair 按 ITT
失败并单独报告，不能换 seam 或借前一 cell 的 work。

样本量由冻结 pilot 的 discordance 做 paired noninferiority power simulation
决定，power ≥80%、one-sided alpha=0.025。即使 pilot 零 discordance，仍至少
使用 183 个独立 task pairs；这是在理想零 durable-only loss 下，two-sided 95%
bound 排除 2 pp harm 的最低量级，出现 discordance 时 N 必须更大。Primary CI
使用预注册、不会在零差异时退化的 paired score/exact risk-difference method；
additional seeds 用 task-cluster-aware secondary analysis。固定 model、tools、
temperature、Evaluation Contract、Attempt budget 和输入 digests，并报告：

- Run-level `VALID_PASS` rate / terminal-valid rate；
- primary paired absolute delta 和 score/exact 95% CI；additional-seed
  secondary cluster-aware CI；
- infrastructure-loss rate、automatic recovery、RTO；
- calls、tokens、wall/GPU time；
- invalid/ambiguous/needs-operator 分层结果。

无 fault cell 的 noninferiority gate：durable − legacy 的 paired pass delta 95%
CI 下界 > -2 percentage points。这个实验验证“没有为了恢复/复用破坏结果”，
不是 Experience Gain。

故障 cell 的 recovery gate：全部已分配的正式 fault pairs 都必须实际到达并触发
其 assigned eligible-recoverable seam；任一未到达/未触发仍按 ITT=0 计入 paired
analysis，且使 G8 失败。每个 durable fault cell 必须无需 operator 介入而自动恢复，
其 `scientific_outcome_digest` 和 terminal disposition 必须与同一 task/seed 的
durable 无 fault cell 完全相同。任一 `unsafe`、需人工介入、`FAILED`、
`CANCELLED`、`WAITING_INPUT`、invalid 或 outcome/disposition 不同都使 G8 失败，
不得只作为单独报告的 ITT 零值继续发布。legacy fault cell 仍按预注册 ITT 规则
报告，用于比较故障损失，但不构成 durable recovery 成功的替代证据。

### 13.2 Equal-budget capability experiment

只有 release gates 全过后才运行。先以至少 30 个隐藏 tasks × 3 seeds 做独立的
blinded capability pilot；正式 capability corpus 与该 pilot、release corpus 和
G7 campaign 全部不相交。比较：

- `legacy-equal-budget`：Phase 0 冻结、content-addressed、可重放的 legacy
  benchmark container/harness；它不是生产 fallback。其外层 Budget Adapter 在每次
  model/tool/process dispatch 前执行与 durable 相同的 cap/reservation normalizer；
  无法在 external boundary 前强制 calls/tokens/wall/GPU cap 的 legacy harness
  不能参加实验；
- `durable-fixed-attempts`：与 legacy 相同的冻结 Attempt decisions；
- `durable-reinvested`：把节省的 calls/tokens/wall 预算投入更多 verifier-backed
  candidate Attempts；
- 三个 arms 的 calls、tokens、wall、GPU cap 向量相同，并预先指定唯一 primary
  binding resource 和停止规则。`≤5% actual-usage tolerance` 只比较
  `legacy-equal-budget` 与 `durable-reinvested` 在该 binding resource 上的实际
  usage；`durable-fixed-attempts` 预期因 continuation 少用资源，不受该 tolerance
  下限约束。其他资源报告 actual use 和 cost-normalized effect，但不能事后改
  binding resource。

每个 arm 的 wall boundary 从 budget wrapper 接受该 task/seed 前开始，到 terminal
transition 或预注册 deadline；包含 decision cost、queue/backoff/retry、model/tool、
training 和 verification。GPU 用 device-active milliseconds，calls/tokens 用 G7
normalizer；所有值使用 settled actual usage，open reservation 在 deadline 按
worst-case settle。Legacy wrapper 与 durable stores 跑同一 enforcement contract。

每个 task/seed 在运行前生成内容寻址的 `DecisionManifest`，冻结 base
Hypothesis、ordered immutable AttemptSpecs、Intervention、seed、Attempt
allocation、Evaluation Contract，以及精确的 open order 与 `stop_after` decision。
这些 decision 与 arm 内 Observation 独立，不能在运行中再调用模型或依据 arm
outcome 改写。Legacy 与 `durable-fixed-attempts` 重放同一 manifest；它们只比较
orchestration parity。
`durable-reinvested` 先重放同一 base manifest，再按预注册 candidate policy 使用
节省的 binding budget 打开额外 verifier-backed Attempts。三个 arms 使用同一
task/seed pair，arm execution order 在 task block 内平衡随机化，且 workspace、
snapshot import 和 private evaluator data 隔离。

DecisionManifest generator 的 model/policy/version、task inputs、random seed、
prompts、physical invocation trace 和输出 digest 在 randomization/unblinding 前
冻结；它看不到 arm identity、private evaluator 或 arm outcome。其完整 calls/
tokens/wall/GPU cost 作为相同 `common_decision_cost` 计入每个 arm，并在 arm cap
中先扣除，不能跨三 arms 摊薄或排除。Manifest invalid/missing 的正式 task 不得
删除：三个 arms 的 ITT outcome 都为 0，已花 generator cost 仍计入 usage。

正式 Primary endpoint 是 Run-level `VALID_PASS` 的 paired intention-to-treat
risk difference；invalid/missing/waiting/failed/cancelled 均为 0。正式 N 由
capability pilot 的 paired discordance 和预注册最小有意义优势 `+3 pp` 做 superiority
power simulation，power ≥80%、one-sided alpha=0.025，且不少于 183 个独立
task pairs。CI 使用冻结的 paired score/exact method；additional seeds 用
task-cluster-aware secondary analysis。按 serial gatekeeping 先要求
`durable-fixed-attempts − legacy-equal-budget` 的 95% CI 下界 > -2 pp，再检验
`durable-reinvested − legacy-equal-budget` 的 primary 95% CI 下界 > 0；只有两步
都过才能主张等预算 capability gain。`durable-reinvested −
durable-fixed-attempts` 仅作“节省预算被更多 Attempts 利用”的机制分析。还要求
至少三个 task families 通过下述方向 guardrail 且无下述 validity 退化；不能把
单纯增加实际资源的收益写成 Runtime 本身“变聪明”。

Actual-usage tolerance 的唯一公式是
`abs(U_reinvested - U_legacy) / U_legacy ≤ 0.05`，其中 `U_legacy > 0`，`U` 是全部
formal ITT task pairs（含 failed/missing/cutoff 和 full common-decision cost）在
冻结 binding resource 上的 aggregate settled actual usage，不是 per-pair mean、
reservation 或只看成功 Run。Family consistency 要求预注册的至少
三个 family 各自 `VALID_PASS` paired point delta > 0；任一 durable arm 的 invalid
Verification rate 不得高于 legacy point rate。两项是 claim guardrail，不替代
overall primary CI，也不作额外显著性检验；任一不满足即禁止 capability claim。

## 14. 分阶段实施

### Phase 0 — baseline instrumentation and characterization

**修改**

- 给现有 stage/LLM/tool/training/evaluator 增加统一 read-only trace；
- 生成 frozen baseline manifest 和 real-writer fixtures；
- 生成 content-addressed legacy benchmark container/harness，并给所有 external
  dispatch 加与 durable 同 contract 的 Budget Adapter；
- 记录当前 infrastructure fault rate `f`。

**退出条件**

- 两个 entry flows 均可 replay 比较输入/输出 digests；
- V2 cost numbers 能从 raw trace 自动重算；
- 不改变现有 stage ordering 或 success semantics。

### Phase 1 — Interface and store

**新增**

- `long_task.py` 的 command/query/snapshot Interface；
- `_journal.py` 的 InMemory/SQLite store；
- event schema、projection、idempotent command receipts、migrations；
- store/interface/replay contract tests。

**退出条件**

- G1 的 import/contract tests；
- atomic transition、replay、corruption tests 全过；
- 尚不接真实 InnoFlow。

### Phase 2 — coordinator safety

**新增**

- Run Lease、fencing、separate progress cursor；
- effect journal/reconcile；
- independent physical-invocation lifecycle and durable timers；
- artifact atomic commit；
- Budget Envelope reserve/settle；
- typed retry/cancel/process group；
- bounded worker loop；
- launcher operational entrypoint、private control/executor roles、test launcher
  与 systemd/launchd/container 部署模板；
- admission circuit breaker、integrity incident epoch 与 per-Run quarantine sweeper；
- kind-specific Run projection、campaign `AWAITING_ASSIGNMENT`/proof activation CAS、
  exact-manifest terminal closure 与 distillation outcome mapping；

**退出条件**

- 1,000 takeover races stale rejection 100%；
- cancellation/process tree tests；
- executor/control/launcher-only kill、guard EOF、surviving-child startup
  reconciliation、overlapping restart 与 RTO tests；
- artifact lifecycle CAS 的 import-vs-GC 与 crash-seam tests；
- terminal-settlement barrier 与 late-reconcile race tests；
- ambiguous effect behavior；
- budget crash-seam tests。

### Phase 3 — pure legacy continuation

**新增**

- `stage_continuation.py`；
- pinned workflow and continuation-policy versions/digests；
- 先把当前七-stage linear order 表达为纯 plan；
- `LegacyFlowStageAdapter` 作为迁移桥。

**退出条件**

- current completed/failure fixtures 的 stage order、final artifacts、verified
  outcome 与 baseline 相同；
- planner determinism/property tests 全过；
- coarse recovery 不能被标注为完整 Stage Continuation。

### Phase 4 — Research Context Snapshot extraction

**修改**

- 把 `prepare/survey/method_review` 提升到 run scope；
- 把当前 `plan` 拆成 method review 与 run-decision intervention plan；
- 建立 immutable snapshot、scope digest、copy-on-write Attempt workspace；
- Recall Context 只进入 snapshot 冻结后的 decision point。

**退出条件**

- content canary 和 invalidation matrix 全过；
- 三 Attempts 下 run-scoped executor count 精确为 1；
- cross-attempt/cross-arm file leakage = 0。

### Phase 5 — native stage Adapters and verified completion

**修改**

- provided/reference flows 拆为真实 Stage Adapters；
- 保留 `AdaptiveExperimentRunner` 为 attempt-scoped deep Module；
- 对接 Experience Loop 的 immutable IDs 和 idempotent receipts；
- completion-required Verification/Experience、per-Intent Recall Decision Outcome、
  per-Experience Experience Distillation Receipt 写入 terminal ordering。

**退出条件**

- 两个 workflow contract suite 全过；
- 无 valid Verification Record 的 `COMPLETED` = 0；valid negative 仍可完成；
- crash after execute/verify/record 只补缺失 suffix。

### Phase 6 — entrypoint migration

**修改**

- CLI 和 Web 通过 thin Adapter 调 `apply/inspect`；
- Web stop 接 `CancelRun`；
- new journal authoritative；legacy JSON 仅从 outbox 投影；
- feature flag `legacy | durable`。

**退出条件**

- dependency rule G1 全过；
- legacy/durable parity suite 通过；
- 不存在双写双 authority。

### Phase 7 — acceptance and rollout

**执行**

- ≥9,600 scripted fault matrix；
- recoverable-fault-profile-v1 的 100-run randomized recovery claim；
- 24-hour soak；
- 10-Run efficiency gate；
- 2 × 2 scientific noninferiority experiment；
- shadow → canary → default rollout。

**退出条件**

- G1–G9 全过；
- acceptance manifest、raw results、digests、CI analysis 归档；
- rollback drill 在 canary 数据上成功。

### Phase 8 — preserve control, optional capability experiment, then deletion

Phase 0 已生成 sealed legacy benchmark container/harness；Phase 8 先验证其 digest、
Budget Adapter 和 replay fixture。随后运行 optional equal-budget capability
experiment，或显式记录 `NOT_RUN` 并放弃 capability-gain claim。只有实验完成/放弃
后才删除 production legacy responsibilities；sealed benchmark artifact 与 raw
evidence 保留作复现，但不得被生产代码 import。

**删除/收敛**

- `MasterRuntime` 旧职责；
- independent Supervisor state machine；
- manual heartbeat/progress/stage completion lifecycle；
- 重复 retry owners 和 authoritative JSON writers；
- 迁移期 `LegacyFlowStageAdapter`。
- production `legacy | durable` flag 与 legacy admission routing；post-delete 只
  支持 pinned current/previous durable releases。

删除前用 `rg` 和 import tests 证明无生产 caller；不得因为新路径“看起来稳定”
就留下永久双实现，也不得把 sealed benchmark harness 当 production fallback。

## 15. Rollout and rollback

1. `legacy` 默认，durable 只跑 shadow metadata，不执行重复 external effects；
2. synthetic/fault benchmark 使用 durable；
3. internal canary 运行小任务，legacy 保留为独立 fallback；
4. 10% new Research Runs 使用 durable；in-flight run 永不换 workflow/store
   version；
5. 50% → 100%，每一档至少覆盖预注册 task count 和 fault-free period；
6. default 后观察一个完整 soak/benchmark 周期再删除旧职责。

Performance 或 scientific-regression trigger 用一个 operational transaction
关闭新的 durable admissions；健康的 in-flight Research Runs 继续由 pinned
runtime/workflow/policy version 完成。Phase 8 删除前，可把新 admissions 路由到
仍受支持的 legacy release；删除后 `legacy | durable` flag 被移除，rollback 部署
上一份 manifest-approved、retained content-addressed durable deployment bundle；
它必须先在 current-journal copy 上通过 Runtime/Adapter/schema replay compatibility，
且不得 downgrade journal。若没有这种 previous durable release，
新 Run 明确返回 `AdmissionClosed`/排队等待 operator，sealed benchmark harness
绝不成为 production fallback。

Integrity/security trigger（包括 false completion、duplicate logical commit、
accepted stale commit、journal/projection 无法 replay、ownership 误判或 private
canary 泄漏）在同一 transaction 关闭 admissions 并创建带 scope 的 active
incident epoch。每个 worker claim/commit 立即检查该 epoch，因此匹配 scope 在
per-Run event 前已 fail closed；idempotent sweeper 随后以 incident ID + per-Run
event-sequence CAS retry 提交 `RunQuarantined`、revoke fence 并进入
`WAITING_INPUT`。它不是虚假的 cross-Run atomic transition。两类 rollback 都绝不
把 durable state 逆向猜成旧 JSON 后继续。

自动 rollback triggers：

- 任一 false completion、duplicate logical commit 或 accepted stale commit；
- projection 无法 replay；
- G8 primary Run-level `VALID_PASS` paired delta 的 95% CI 下界 ≤ -2 pp；
- 任一 artifact stratum 的 `UCB95(median overhead) > 3%` 或
  `UCB95(p95 overhead) > 5%`；
- cancellation 误杀非 owned process；
- private evaluator/Recall canary 进入 snapshot。

## 16. Acceptance manifest

每次 release candidate 生成机器可读 manifest，至少包含：

```text
git_revision
runner_fingerprint_os_cpu_disk_python_sqlite
runtime_schema_version
research_run_kind_and_kind_specific_contract_digest
distillation_campaign_profile_manifest_assignment_authorization_conflict_completion_digest
workflow_artifact_refs_versions_and_digests
continuation_policy_artifact_refs_versions_and_digests
runtime_adapter_interpreter_contract_bundle_refs_versions_and_digests
launcher_control_executor_readiness_liveness_parent_death_cohort_reconciliation_exit_restart_clock_config_digest
terminal_settlement_and_resolution_state_digest
artifact_lifecycle_gc_restore_delete_fault_digest
artifact_staging_claim_and_reference_root_digest
admission_incident_schema_and_rollback_drill_digest
current_previous_durable_bundle_refs_digests_and_compatibility_digest
model_tool_config_digests
evaluation_contract_digests
baseline_manifest_digest
call_token_normalizer_digest
reuse_governance_policy_matrix_digest
test_suite_revision
fault_matrix_seed_set
applicable_seam_coverage_manifest_digest
recoverable_fault_profile_digest_and_sampling_weights
recovery_sampler_version_and_digest
recovery_realized_100_draws_digest
fault_results_by_class
recovery_wilson_interval
replay_projection_hashes
scientific_outcome_digest_set
distillation_outcome_and_exact_manifest_coverage_digest_set
efficiency_raw_totals
unamortized_and_amortized_costs
runtime_overhead_benchmark_digest
runtime_overhead_trace_order_raw_ns_and_bootstrap_digests
latency_raw_samples_ttd_rto_commit_visibility_cancel_digest
latency_analysis_code_and_bootstrap_seed_digest
latency_sample_frames_quantile_convention_and_selection_digest
metadata_byte_boundary_and_samples_digest
release_pilot_corpus_and_results_digest
release_power_simulation_digest
release_formal_task_pairs_and_family_quotas_digest
release_fault_assignment_semantic_mapping_and_cell_order_digest
release_cell_isolation_and_cold_cache_fixture_digest
release_preregistered_analysis_plan_digest
noninferiority_analysis_digest
soak_start_end_and_fault_log
soak_resource_series_and_threshold_results
soak_window_gc_grace_and_estimator_config_digest
soak_wal_checkpoint_schedule_mode_and_size_samples_digest
known_waiting_input_cases
capability_extension_status_and_reason
```

`capability_extension_status` 是 `NOT_RUN | PILOT_ONLY | COMPLETE`。Core release
允许 `NOT_RUN`，且 `NOT_RUN/PILOT_ONLY` 都禁止 capability-gain claim。
`PILOT_ONLY/COMPLETE` 要求 extension 提供并解析：

```text
legacy_benchmark_container_budget_adapter_digest
capability_pilot_corpus_and_results_digest
capability_preregistered_analysis_plan_digest
capability_pilot_decision_manifests_and_common_cost_digest
```

只有 `COMPLETE` 再强制：

```text
capability_power_simulation_digest
capability_formal_task_pairs_family_quotas_and_arm_order_digest
capability_formal_decision_manifests_and_common_cost_digest
capability_raw_usage_outcomes_and_analysis_digest
```

上述 `*_digest` 都必须解析到随 release candidate 归档的 immutable raw artifact；
只记录一个无法取回内容的 hash 不算提交证据。100 个 realized recovery draws、
全部 latency/overhead raw samples、randomization assignments 与预注册 analysis
plan 必须先归档再计算发布结论。

任何手工删除失败 run、修数据库、替换 artifact 或重分类 fault 都必须写为
manifest deviation，并使 automatic-recovery gate 失败。

## 17. Definition of Done

- [ ] 两个应用 Interface 入口、一个 pure continuation 入口稳定；
- [ ] CLI/Web 不直接依赖旧 Runtime Implementation；私有 worker 不暴露给应用；
- [ ] SQLite event journal 是唯一 authoritative runtime source；
- [ ] Durable Transition 具备 event-seq CAS 和 fencing；
- [ ] stable logical effect 与 independent physical invocation lifecycle、
  receipt、reconcile 和 `WAITING_INPUT` 语义完整；
- [ ] terminal settlement barrier 保证所有 terminal Run 的 invocation final、
  reservation settled、Run-owned task/thread/process-group/container reconciled、
  Run-scoped lease/role assignment released、artifact staging/materialization 与
  filesystem-mutation actor、Snapshot Build Claims non-active；
- [ ] durable timer claim/firing/cancellation 与 private CAS-authorized
  live-but-stalled watchdog preemption 可验证；
- [ ] artifact atomic commit、digest validation、orphan GC 可验证；
- [ ] queued Work Item 的 Campaign Admission Profile 在 Ledger enqueue 前已有
  Work-Item-owned `ACTIVE` ref + `PENDING` handoff，enqueue receipt + independently
  read-back sidecar exact-match 后 BOUND；source
  terminal 不释放，pre-enqueue absence recovery 与 terminal Completion/replay-retention
  显式 release 的 crash matrix 全过；
- [ ] artifact lifecycle CAS/restore/delete recovery 消除 import-vs-GC TOCTOU；
- [ ] 所有 shared content-path mutation 由 exact-identity gated actor 执行；takeover
  先 terminate/wait prior actor 并等待 per-object-generation kernel lock release，
  `SIGSTOP` 旧 actor 不可在新 ref 发布后恢复破坏 bytes；
- [ ] 四种 checkpoint policy、resume-token corruption/scope 与 >5-minute
  enforcement contract 全过；
- [ ] worker authority heartbeat 与 Activity progress 已分离；
- [ ] pause/resume/cancel/budget/retry 均为 durable command/state；
- [ ] run-scoped snapshot 与 attempt-scoped work 已拆开；
- [ ] reuse-governance Claim isolation、producer export、consumer admission 与
  retention matrix 全过；
- [ ] content-addressed workflow/continuation-policy retention/resolution、complete
  AttemptSpec 与 stage reuse policy 已通过 determinism/invalidation tests；
- [ ] Recall/private/mutable workspace canary 泄漏为 0；
- [ ] infrastructure retry 不伪造新 Experiment Attempt；
- [ ] 每个 `SCIENTIFIC + COMPLETED` 有 completion-required valid Verification/Experience、每个
  Run-owned Intent 的 Recall Decision Outcome、每个 completion-required Experience
  的 Experience Distillation Receipt 完整链；
- [ ] 每个 `FAILED/CANCELLED` 也关闭全部已预分配 Intent，并为已存在的
  completion-required Experience 写唯一 Receipt；不会伪造不存在的科学记录；
- [ ] `MEMORY_DISTILLATION` admission/AWAITING_ASSIGNMENT proof-CAS/completion
  contract 全过；terminal source Run 不创建 deferred Activity，campaign Run 对 exact
  manifest 每项一个 Assignment/Activity/Completion、foreign=0、terminal 下
  assigned-incomplete=0；scientific/distillation outcome kind-discriminated mapping 正确；
- [ ] Work Item-pinned Campaign Admission Profile + canonical Work-Item `DriveRun`
      admission/run/initial-command identities 消除 config-
  skew duplicate Run；executor proposal-only，commit/closure authorization、atomic Ledger
  success、NO_COMMIT_CONFLICT retirement/reproposal、pending cancel/failure arbitration 和
  same-scope concurrent CAS liveness 全过；
- [ ] applicable-seam coverage manifest 完整、scripted injections ≥9,600，
  safety violations 为 0；
- [ ] recoverable-fault-profile-v1 的随机 real-process runs 100/100 正确恢复，
  且公开 claim 限定到该 profile；
- [ ] RPO/RTO/commit/visibility/cancel/overhead SLO 全过；
- [ ] launcher operational Interface、control/executor readiness/liveness/exit/
  parent-death guard、startup reconciliation、signal/restart contract 全过；
- [ ] 24-hour soak 全过；
- [ ] 10-Run efficiency Hard gate 全过；
- [ ] 2 × 2 scientific noninferiority gate 全过；
- [ ] rollback drill 与 acceptance manifest 完成；
- [ ] admission breaker/incident epoch/commit check/quarantine sweep 与 post-delete
  previous-durable-or-closed rollback contract 全过；
- [ ] 旧 authority/retry/lifecycle responsibilities 已删除。

只有上述全部完成，才可将治理设计从 `Proposed` 改为 `Accepted`，把本计划从
`Ready for implementation` 改为 `Implemented`。

## 18. 实施中的明确非目标

- 不引入 Redis、Temporal、Kubernetes、Postgres 或远程队列作为 v1 前置；
- 不实现任意 Python/GPU/browser 内存快照；
- 不承诺 non-queryable external effect 的 physical exactly once；
- 不增加只有一个假想 Implementation 的 distributed Adapter；
- 不在 v1 开放并行 candidate DAG 或 `ForkRun`；
- 不把任务运行天数写成模型 cognitive time horizon；
- 不用降低 evaluator 标准换效率；
- 不把 Runtime recovery 与 Experience Gain 混为一个统计结论。
