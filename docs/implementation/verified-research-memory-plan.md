# Verified Research Memory 实施计划

**Status:** Ready for phased implementation after Phase 0 contract freeze

**Scope:** 将比较式知识提炼、知识生命周期、Decision-Point Retrieval、Recall
Decision Outcome、Evidence/Knowledge/Recall Input Snapshots、Procedure Record、Reference Retrieval 和 legacy
隔离落实为可迁移、可测试、可回滚的代码

**Owner:** AI-Researcher maintainers

**Last updated:** 2026-07-31

**Governing design:**
[Verified Research Memory](../design/verified-research-memory.md)

**Validation contract:**
[Memory effectiveness evaluation protocol](memory-effectiveness-evaluation.md)

**Related authority:**
[Experience-Driven Research Loop](../design/experience-driven-research-loop.md)、
[Durable Research Runtime](../design/durable-research-runtime.md)、
[Context-Aware Tool Use](../design/context-aware-tool-use.md)、
[Experience Gain next-round plan](experience-gain-next-round-plan.md) 和
[Phase A specification](experience-gain-v3-phase-a-spec.md)

本文中的 **MUST / MUST NOT / SHOULD / MAY** 是规范性要求。

## 1. 交付结论

本计划不是“换一个向量库”，而是完成三个有 Depth 的 Module：

1. `KnowledgeDistiller`：把可比较、可验证的 Experience 编译为条件—动作—效应
   Knowledge/Procedure，并治理冲突和生命周期；
2. `DecisionPointRetriever`：在明确决策点按 scope、状态、动作和证据质量返回有界
   Evidence Cards；
3. `MemoryAcceptanceHarness`：由 `benchmark/memory/harness.py` 统一装配 offline、
   causal、artifact assembly 和 validator Interfaces，从 writer、retrieval、
   utilization 一直验证到真实执行和 Experience Gain。

第一条 vertical slice 只激活 `intervention` Decision Point，并复用 Phase A 已有的
Intervention Catalog、PreviousAttemptFeedback、Manipulation Check 和 Trial
Provenance。其他 Decision Point 在同一 Interface 稳定后逐步开启。

交付完成后可以声称：

> 系统能从可比较的 verified Experience 生成受治理知识，在一个明确决策点精确
> 召回，记录采用/拒绝，并证明被采用的 citation 映射到实际执行配置。

只有通过配套确认性协议后才可以进一步声称：

> Verified Research Memory 在预注册 evaluation pairs 上、按冻结的
> `transfer_scope` 提高了 AI Researcher 的最终科研结果；只有
> `held_out_evaluation_task` 结果可称“未见任务”。

## 2. 当前基线与必须保留的事实

实施基线是 `main@5cd60ec`，Phase A 位于 `f585de4`。

当前代码事实：

- `SQLiteExperimentLedger` schema revision 是 `2`；schema 0 可以迁移到 2，其他
  版本 fail closed；
- 原有 `KnowledgeRecord`、`PromotionDecision`、`RecallRequest` 和
  `RecallContext` 都是 `schema_version="1"` 的 frozen Pydantic payload；
- 给旧 model 增加默认字段会改变重新序列化字节，违反 ledger idempotence；
- `ImprovementCycleRunner` 在迭代前调用 `ExperienceRunAdapter.before_run()`，但
  RecallRequest 没有 PreviousAttemptFeedback、Evaluation Contract Decision Point
  或 Intervention Catalog；
- `ExperienceRunAdapter` 生产装配硬编码 `KeywordExperienceRetriever`，并在提交
  前修改共享 `KnowledgeGate` 的 domain/model；
- `ExperienceLoop.after_run()` 逐步 append Experience、Knowledge、Promotion
  Decision，Knowledge batch 不是原子提交；
- 当前 ledger-wide `snapshot_id()` 对所有 raw Experience/Intervention/Provenance
  敏感，不是 Knowledge Snapshot；
- Phase A 已能把 proposal citation、Intervention、effective config、runner
  manifest 和 Verification 串起来，但没有逐 Recall Item 的采用/拒绝记录；
- `memory/store.py`、`consolidation.py` 和 `meta_chain_wrapper.py` 不在可信
  production closed-loop 路径中；paper/code/tool RAG 仍被部分工具使用。

以下行为必须保持：

- 旧 ledger payload byte identity；
- Phase A Attempt/Intervention/Trial Provenance ID 和 dry-run 可重放性；
- Evaluation Contract 和 private evaluator isolation；
- memory-off、record-only、现有 legacy 路径的显式兼容模式；
- InMemory 与 SQLite Adapter 的共同 contract suite；
- Durable Runtime 对 Run/Activity/Effect/Artifact/Budget 的唯一所有权。

## 3. 依赖和并行关系

### 3.1 已满足依赖

- Governed Intervention 和合法 knob surface；
- effective config/no-op Manipulation Check；
- source/config/dataset/environment/contract/evidence digests；
- verified feedback 回到下一轮；
- SQLite immutable ledger 和 sidecar migration 模式。

### 3.2 可并行依赖

- Phase B response-surface calibration 可以和 memory schema/writer 开发并行；
- Durable Runtime 可以和 memory data-plane 开发并行；
- offline writer/retrieval acceptance 不依赖 Durable Runtime 全部 release gates。

### 3.3 发布依赖

- Memory mechanism Pilot 只要求冻结预算、workspace/arm 隔离、完整 lineage、
  失败保留和可重放 evidence；
- production 集成发布必须同时通过 Memory gates 和 Durable Runtime release gates；
- 正式 Experience Gain 必须先通过 task response-surface/sensitivity gate；
- 若 power analysis 所需样本超过预算，结论是“证据不足”，不得截断样本后 claim。

## 4. 新代码布局

### 4.1 新增文件

| 文件 | Module / 责任 |
| --- | --- |
| `research_agent/inno/experience/memory_models.py` | 所有新 immutable memory models 和 canonical ID helpers |
| `research_agent/inno/experience/policies.py` | Distillation/Lifecycle/Snapshot Selection/Retrieval policy schemas、load 和 digest validation |
| `research_agent/inno/experience/distillation.py` | `KnowledgeDistiller` 深 Module；比较、support、candidate、promotion/procedure proposal；executor 不写 Ledger |
| `research_agent/inno/experience/distillation_outbox.py` | queued enqueue 前的 Work-Item-owned Campaign Admission Profile artifact handoff、durable Work Item 扫描、immutable campaign manifest、独立 `MEMORY_DISTILLATION` Run admission、AWAITING_ASSIGNMENT proof/CAS、Runtime-authorized atomic commit/no-commit-conflict/closure reconciliation；artifact bytes/GC、handoff、claim lease 均归 Runtime |
| `research_agent/inno/experience/lifecycle.py` | lifecycle reducer、transition validator、active-view projector；只供 distiller/snapshot 使用 |
| `research_agent/inno/experience/retention.py` | authorized retraction/tombstone、separately stored payload/artifact erasure receipt 与 index invalidation；保留 non-private canonical audit projection |
| `research_agent/inno/experience/indexes.py` | lexical 与 real-embedding Candidate Index Adapters；禁止 production hash semantics |
| `research_agent/inno/experience/snapshot.py` | `EvidenceSnapshotBuilder`、`KnowledgeSnapshotBuilder`、`RecallInputSnapshotBuilder`；分别拥有 evidence capture、active-view freeze、ready-index composition |
| `research_agent/inno/experience/ledger_migrations.py` | schema declaration、0→2→3 / 2→3 migration 和结构验证 |
| `research_agent/inno/reference_index/{models.py,retrieval.py,indexes.py}` | Source/Reference Retrieval Module、typed Reference Cards 和 rebuildable source indexes |
| `research_agent/inno/experience/procedure_binding.py` | 校验 Procedure step 只引用 pinned Capability Catalog 中既有 capability ID/version；不授予 authorization |
| `benchmark/memory/schemas.py` | claim/shared/stage/root、signed registry/partition/exposure、Pilot Gate、terminal-status、report 和 final validation receipt schemas |
| `benchmark/memory/requirements-v1.yaml` | 每个 VRM/MEM ID 唯一 owner、exact pytest node、check name、stage 和 blocking artifact；validator 的 expected-ID registry |
| `benchmark/memory/campaign_registry.py` | configured Registry Authority trust anchor/signatures、append-only Admission/Closure/Exposure/No-Visibility atomic CAS、hash-chained lineage/global frontiers 与 exact/cross-lineage enumeration；任意 SQLite 只是 storage client |
| `benchmark/memory/hidden_partition_authority.py` | evaluator-only opaque/keyed member commitments、all-hidden-stage non-overlap、deterministic reserve-prefix selection 与 signed receipts；actor 不可读 members/key |
| `benchmark/memory/validation_authority.py` | configured signing/verification Adapter for final acceptance receipts；trust anchor 必须由 Claim Plan/root pin，禁止 validator 自签临时 key |
| `benchmark/memory/harness.py` | `MemoryAcceptanceHarness` public Interface；协调三个 runner、assembly 和独立 validator，不重实现指标 |
| `benchmark/memory/run_offline_acceptance.py` | writer/retrieval/utilization/robustness/scale runner |
| `benchmark/memory/run_ideation_acceptance.py` | paired fresh-start vs memory-shadow ideation quality/diversity runner；产出 `ideation_diversity_report.json` |
| `benchmark/memory/run_causal_acceptance.py` | paired ITT causal runner 和审计 |
| `benchmark/memory/select_retrieval_adapter.py` | 仅在 visible development corpus 按冻结 rule 选择唯一 release Adapter，写 immutable `RetrievalAdapterSelectionReceipt`；不得读取 hidden |
| `benchmark/memory/legacy_baseline.py` | benchmark-only read-only `LegacyBaselineAdapter`；只服务隔离 C2 arm，冻结 legacy algorithm/record-set/budget identity |
| `benchmark/memory/freeze_manifests.py` | pre-visibility 冻结 ScientificClaimPlan/lineage/decision rules、partition/shared/stage identities；Pilot 只按 frozen rule 决定 N，authority 冻结 confirmatory selection；正常 closure 就绪后生成无 hash-cycle root，或对 signed frontier 中 open/invalid admission set 生成 claim=none 的 audit-only invalid root |
| `benchmark/memory/validate_pilot_gate.py` | 独立枚举 signed registry frontier，绑定 offline/selected ideation/A/A/Pilot exact closures、all-stage overlap 和排除最终 CA003 row/root provenance 的 L0–L2 `PilotPrerequisiteAssessment`，对 pass/fail/invalid 均签发 terminal `PilotGateReceipt` |
| `benchmark/memory/assemble_acceptance.py` | read-back stage shards，按 manifest digest 聚合 release-root artifacts；拒绝 mixed campaign |
| `benchmark/memory/validate_acceptance.py` | 独立 read-back validator、requirement/claim gate、mixed-campaign 检测，并由 pinned Validation Authority 签发 final receipt |
| `benchmark/memory/artifact_store.py` | `AcceptanceArtifactStore` 的唯一 immutable receipt/object/report read-back 与 exact-once write owner；Harness 不接受裸 manifest object/path |
| `benchmark/memory/policies/{distillation-v1,lifecycle-v1,snapshot-selection-v1,retrieval-v1}.yaml` | 四种冻结 policy fixtures、各自 canonical content ID/digest vectors |
| `benchmark/memory/registry-authority-v1.json` | Registry/Validation public trust anchors、service/signing epochs 与 signed genesis；private keys 不进仓库 |
| `benchmark/memory/corpus/v1/manifest.json` | development/hidden split schema 和 evaluator-only artifact commitments |
| `benchmark/memory/corpus/v1/development/{writer_cases,retrieval_queries,adversarial_cases,annotations}.jsonl` | 可见开发 fixtures；不得进入 formal release denominator |
| `benchmark/memory/corpus/v1/hidden-manifest.json` | 仅 evaluator-only refs/digests、keyed commitment roots/counts 和 authority identity；仓库不存 cases/gold、raw fingerprints 或 key/salt |
| `benchmark/memory/manifests/v1/objects/sha256-<digest>.json` | `ScientificClaimPlan`、shared/stage/root 等 canonical content-addressed objects；永不覆盖 |
| `benchmark/memory/manifests/v1/lineages/<lineage-id>/*.json` | immutable receipt/ref files，绑定 object ref/digest；固定友好文件名不得作为权威 identity |
| `benchmark/memory/manifests/v1/lineages/<lineage-id>/stages/*.json` | 独立 Stage Manifest receipts；同 lineage/shared/claim plan，不同 campaign IDs |
| `benchmark/memory/manifests/v1/lineages/<lineage-id>/roots/release-<ceiling>-<claim-kind>.json` | claim-scoped immutable receipt，绑定 content-addressed root object/digest；L5 绑定并 supersede base root |
| `benchmark/memory/preregistration/v1/{decision-contract,families,offline,ideation,aa,pilot,confirmatory}.yaml` | pre-Pilot endpoints/margins/alpha/decision rules、family/transfer plan 与各 stage arms、完整资源边界、随机化、failure utility、power/stopping rule |
| `benchmark/memory/preregistration/v1/retrieval-candidates.yaml` | development selector 可比较的 Adapter/policy identity 闭集、schema version 与每个 content digest；禁止 runtime/hidden 动态 candidate |
| `benchmark/memory/preregistration/v1/retrieval-selection-rule.yaml` | visible-development selection estimand、threshold、deterministic tie-break、N/A/failure rule、schema/code digest；hidden result 不得成为输入 |

`distillation.py` 和 `retrieval.py` 是对调用方有 Depth 的 Module。不要把 comparison、
filter、rank、lifecycle 或 token budgeting 拆成由调用方排序的一串 shallow helper。
纯函数可以存在于 Implementation 内部，但外部测试通过 Module Interface 驱动。

### 4.2 修改文件

| 文件 | 改动 |
| --- | --- |
| `research_agent/inno/experience/models.py` | 保留 raw Experience model 和 legacy v1 memory model；加清晰 deprecation 注释，不改字段 |
| `research_agent/inno/experience/knowledge.py` | legacy `KnowledgeGate` 仅供 `legacy_recall`；新入口 re-export/装配 `KnowledgeDistiller` |
| `research_agent/inno/experience/retrieval.py` | 保留 legacy baseline；实现 `DecisionPointRetriever` 与统一 deterministic final ranker |
| `research_agent/inno/experience/ledger.py` | 拆分窄 store Protocol、schema v3 append/query/transaction；新 append 和 Verified Evidence Bundle 都交叉验证 nested/canonical rows；不再内嵌全部 migration 常量 |
| `research_agent/inno/experience/loop.py` | 从外部 coordinator 收窄为 Runtime Activity 内部 Adapter；after-run 允许 `defer`，调用幂等 distiller |
| `research_agent/inno/experience/intervention.py` | 增加每 Recall Item 的 disposition 和 citation-to-action mapping model |
| `research_agent/runtime/experience_adapter.py` | 依赖注入 Retriever/Distiller/Snapshot；新增 REQUIRED-only `prepare_required_decision` + `commit_required_decision_context` 与 explicit no-decision-memory branch；移除硬编码和共享 gate mutation |
| `research_agent/runtime/improvement_cycle.py` | 每轮在 exact Decision Point 构造 recall；下一轮使用自己的 PreviousAttemptFeedback |
| `research_agent/runtime/adaptive_experiment.py` | 验证 Recall disposition 全覆盖、adopted rule/action 匹配并持久化 Recall Decision Outcome |
| `research_agent/runtime/research_pipeline.py` | 移除将同一 Recall Context 注入多个阶段；按 profile 渲染 Evidence Cards |
| `research_agent/run_infer_plan.py` | 只在当前启用 Decision Point 取对应 context；不再复用全局 prose guidance |
| `research_agent/run_infer_idea.py` | 同上；ideation 新路径先 shadow 并保留 fresh-start branch |
| `research_agent/inno_common.py` | 新增 policy/snapshot/rollout CLI 引用；具体 index 参数放在 policy 文件 |
| `research_agent/inno/experience/__init__.py` | 导出稳定新 Interface 和 models；legacy 名称显式标记 |
| `research_agent/inno/memory/*.py` | 按第 13 节隔离/重命名，不再向 trusted knowledge path 暴露写入 |
| `README.md` | 移除 episode→summary→fact 即科研 Knowledge 的陈述，标识 legacy primitives |

### 4.3 新测试文件

```text
tests/test_experience/
  factories.py
  test_memory_models.py
  test_knowledge_store_contract.py
  test_distillation_outbox.py
  test_knowledge_distillation.py
  test_knowledge_lifecycle.py
  test_memory_retention.py
  test_evidence_snapshot.py
  test_knowledge_snapshot.py
  test_recall_input_snapshot.py
  test_decision_intent.py
  test_decision_point_retrieval.py
  test_recall_utilization.py
  test_reference_memory.py
  test_procedures.py
  test_legacy_memory_isolation.py

tests/test_runtime/
  test_decision_recall_integration.py

tests/test_benchmark/
  test_memory_acceptance_report.py
  test_memory_claim_gate.py
  test_ideation_fresh_start.py
```

现有测试不得继续从另一个 test module 导入 `build_records`；共同 fixture 移到
`tests/test_experience/factories.py`。

## 5. Public Interfaces

### 5.1 Store seams

当前巨型 `ExperimentLedger` Protocol 保留兼容入口，但新 Module 只依赖窄
Interface：

```python
class VerifiedEvidenceStore(Protocol):
    def capture_verified_evidence(
        self, request: FreezeEvidenceRequest
    ) -> EvidenceSnapshotCommitReceipt: ...
    def get_evidence_snapshot(self, snapshot_id: str) -> EvidenceSnapshot: ...
    def get_evidence_capture_receipt(
        self, capture_operation_id: str
    ) -> EvidenceSnapshotCommitReceipt: ...
    def get_verified_evidence_bundle(
        self, snapshot_id: str, experience_id: str
    ) -> VerifiedEvidenceBundle: ...
    def enqueue_distillation(
        self,
        receipt: ExperienceDistillationReceipt,
        work_item: DistillationWorkItem | None,
        abandoned_work_item: DistillationWorkItem | None,
        profile_artifact_proof: WorkItemProfileArtifactProof | None,
        abandonment_proof: DistillationEnqueueObligationAbandonedProof | None,
    ) -> DistillationEnqueueReceipt: ...
    def list_unassigned_distillation(
        self, *, namespace: str, page_after_position: int | None, limit: int
    ) -> PositionedDistillationPage[DistillationWorkItem]: ...
    def append_distillation_assignment(
        self,
        assignment: DistillationWorkAssignment,
        runtime_proof: DistillationCampaignRuntimeProof,
    ) -> LedgerAppendReceipt: ...
    def list_assigned_incomplete_distillation(
        self, *, campaign_run_id: str, page_after_position: int | None, limit: int
    ) -> PositionedDistillationPage[DistillationWorkAssignment]: ...
    def get_distillation_campaign_coverage(
        self, campaign_run_id: str, barrier_proof: CampaignBarrierReadProof
    ) -> DistillationCampaignCoverageProof: ...
    def append_distillation_closure(
        self,
        completion: DistillationWorkCompletion,
        authorization: DistillationClosureAuthorizationProof,
    ) -> LedgerAppendReceipt: ...
    def get_distillation_work_item(self, work_item_id: str) -> DistillationWorkItem: ...
    def get_experience_distillation_receipt(
        self, experience_id: str
    ) -> ExperienceDistillationReceipt: ...
    def get_distillation_enqueue_receipt(
        self, experience_id: str
    ) -> DistillationEnqueueReceipt: ...
    def get_distillation_enqueue_transaction(
        self, work_item_id: str
    ) -> DistillationEnqueueTransaction: ...
    def get_distillation_enqueue_recovery_proof(
        self, request: DistillationEnqueueRecoveryRequest
    ) -> DistillationEnqueueRecoveryProof: ...
    def get_distillation_assignment(
        self, work_item_id: str
    ) -> DistillationWorkAssignment | None: ...
    def get_distillation_assignment_proof(
        self, work_item_id: str
    ) -> DistillationAssignmentProof: ...
    def get_distillation_completion(
        self, work_item_id: str
    ) -> DistillationWorkCompletion | None: ...


class KnowledgeStore(Protocol):
    def commit_distillation(
        self,
        plan: DistillationCommitPlan,
        completion: DistillationWorkCompletion,
        authorization: DistillationCommitAuthorizationProof,
    ) -> DistillationCommitReceipt | DistillationNoCommitReceipt: ...
    def get_distillation_batch(self, batch_id: str) -> DistillationBatch: ...
    def get_distillation_report(self, report_id: str) -> DistillationReport: ...
    def get_distillation_commit_conflict(
        self, conflict_id: str
    ) -> DistillationCommitConflict: ...
    def get_distillation_work_disposition(
        self, work_item_id: str
    ) -> DistillationWorkDisposition: ...
    def load_memory_state(self, position: int) -> ImmutableMemoryState: ...
    def commit_knowledge_snapshot(
        self, snapshot: KnowledgeSnapshot
    ) -> SnapshotCommitReceipt: ...
    def get_knowledge_snapshot(self, snapshot_id: str) -> KnowledgeSnapshot: ...
    def get_memory_record(
        self, memory_id: str
    ) -> SemanticKnowledgeRecord | ProcedureRecord: ...


class RecallStore(Protocol):
    def append_contract_view(
        self, view: DecisionContractView
    ) -> LedgerAppendReceipt: ...
    def append_decision_intent(
        self, intent: DecisionIntent, admission_proof: DecisionIntentAdmissionProof
    ) -> DecisionRecallAppendReceipt | DecisionRecallNoCommitReceipt: ...
    def append_recall_input(
        self, snapshot: RecallInputSnapshot
    ) -> LedgerAppendReceipt: ...
    def append_decision_recall(
        self,
        context: DecisionRecallContext,
        authorization: DecisionRecallCommitAuthorizationProof,
    ) -> DecisionRecallAppendReceipt | DecisionRecallNoCommitReceipt: ...
    def append_recall_outcome(
        self,
        record: RecallDecisionOutcome,
        authorization: DecisionRecallCommitAuthorizationProof,
    ) -> DecisionRecallAppendReceipt | DecisionRecallNoCommitReceipt: ...
    def append_outcome_attempt_link(
        self, link: RecallOutcomeAttemptLink
    ) -> LedgerAppendReceipt: ...
    def get_contract_view(self, view_id: str) -> DecisionContractView: ...
    def get_decision_intent(self, intent_id: str) -> DecisionIntent: ...
    def get_decision_intent_coverage(
        self, run_id: str, barrier_proof: DecisionIntentBarrierReadProof
    ) -> DecisionIntentCoverageProof: ...
    def get_recall_input(self, snapshot_id: str) -> RecallInputSnapshot: ...
    def get_decision_recall(self, context_id: str) -> DecisionRecallContext: ...
    def get_recall_outcome_by_intent(
        self, intent_id: str
    ) -> RecallDecisionOutcome: ...
    def get_decision_recall_no_commit(
        self, authorization_id: str
    ) -> DecisionRecallNoCommitReceipt: ...
    def get_decision_recall_append_receipt(
        self, authorization_id: str
    ) -> DecisionRecallAppendReceipt: ...
    def get_outcome_attempt_link(
        self, outcome_id: str
    ) -> RecallOutcomeAttemptLink | None: ...


class DecisionRecallArtifactRead(Protocol):
    def get_decision_recall_blocked_proof(
        self, blocked_source_proof_ref: str
    ) -> DecisionRecallBlockedProof: ...


class IndexStore(Protocol):
    def append_ready_index(
        self, receipt: DerivedIndexBuildReceipt
    ) -> LedgerAppendReceipt: ...
    def append_index_failure(
        self, failure: DerivedIndexBuildFailure
    ) -> LedgerAppendReceipt: ...
    def get_ready_index(self, build_id: str) -> DerivedIndexBuildReceipt: ...
    def get_index_failure(self, failure_id: str) -> DerivedIndexBuildFailure: ...


class RetentionStore(Protocol):
    def begin_erasure(
        self,
        intent: RetentionErasureIntent,
        retraction_event: KnowledgeLifecycleEvent | None,
    ) -> RetentionIntentCommitReceipt: ...
    def get_erasure_intent(
        self, incident_id: str
    ) -> RetentionErasureIntent | None: ...
    def list_open_erasure_intents(
        self, *, namespace: str, page_after_position: int | None, limit: int
    ) -> PositionedRetentionPage[RetentionErasureIntent]: ...
    def append_tombstone(
        self,
        tombstone: MemoryRetentionTombstone,
        proof: RetentionReconciliationProof,
    ) -> LedgerAppendReceipt: ...
    def get_tombstone(
        self, target_kind: str, target_id: str
    ) -> MemoryRetentionTombstone | None: ...
    def check_recall_input(
        self, recall_input_id: str
    ) -> RetentionCheck: ...


class RetentionRuntimeRead(Protocol):
    def get_artifact_erasure_receipt(
        self, receipt_ref: str
    ) -> ArtifactErasureReceiptProof: ...
    def get_index_invalidation_receipt(
        self, receipt_ref: str
    ) -> IndexInvalidationReceiptProof: ...
```

每个 `LedgerAppendReceipt` 返回 logical ID、canonical payload digest、namespace 和
原始 commit position；exact retry 返回相同 receipt。
`DecisionRecallArtifactRead` 由 Runtime Artifact Store 实现，并注入 Runtime issuer 与
`RecallStore` Outcome transaction validator。getter 必须从 immutable content-addressed
artifact 独立读取、重算 object/proposal digest，再逐字段返回 typed
`DecisionRecallBlockedProof`；调用方自带的对象、ref 或 digest 都不能替代该 read-back。
`append_distillation_assignment()` 必须先按 deterministic Assignment ID 查询 canonical
row+journal：若 exact payload/manifest/Run/Activity 相同，直接返回原 receipt，即使
Runtime Activity 已从 `AWAITING_ASSIGNMENT` 进入 READY/terminal；same ID/different
payload fail closed。只有 row 不存在的首次 insert 才要求 fresh
`DistillationCampaignRuntimeProof` 显示 nonterminal Run、owned Activity 和当前
`AWAITING_ASSIGNMENT`。这样 reply-loss retry 不依赖不可逆的旧 Runtime phase。
`DecisionRecallAppendReceipt` 另返回 transition kind 与 exact admission/commit
authorization ID/digest，并可按 authorization ID 从 Store getter read-back。Intent/
Context/Outcome success 后 Runtime 必须同时 read-back canonical record 与该 receipt，再
推进 phase；same record/same authorization exact retry 返回原 position，same record/
different authorization 或 same authorization/different record 是 identity conflict，不能
把 foreign/orphan record 洗成已授权成功。
`EvidenceSnapshotCommitReceipt` 包含完整 Evidence Snapshot 和其唯一
`LedgerAppendReceipt`，以及 capture-operation receipt/position；调用方必须再通过
`get_evidence_snapshot()` 与 `get_evidence_capture_receipt()` read-back 并复算 snapshot
ID、payload/request digests 与原始 positions。same capture operation/same request exact
retry 先返回原 mapping，即使 current Evidence frontier 已推进；same key/different request
是 identity conflict。`DistillationEnqueueReceipt`
包含 ingestion receipt、nullable Work Item receipt，以及对二者有序 projection 的
transaction digest；queued 时还包含 immutable
`enqueue_transaction_id/digest`、handoff/ref ID、首次成功 enqueue attempt
ID/generation/fence 与原 proof digest，且两项 Ledger receipt 必须
同时存在；`abandoned_before_enqueue` 只含 ingestion receipt、abandoned Work Item ID、
frozen Work Item payload digest 与 Runtime abandonment proof ref/digest，并禁止 committed
Work Item/profile proof；deferred/not-required
只含 ingestion。它可按
Experience ID 从 getter read-back，供 Runtime 完成 handoff bind。
Runtime 必须通过上列对应 getter
read-back 并重算 digest 后才能提交 cross-store Activity result。getter 缺失、
payload mismatch 或 intent/context/outcome lineage mismatch 进入 reconciliation，
不能仅凭 append 无异常就认为已提交。multi-record
`DistillationCommitReceipt` 同理返回可 read-back 的 canonical
`DistillationBatch`、`DistillationReport`，并列出 batch 内每个 canonical logical
append receipt（包括 Batch、Report 和 successful Completion 自身）；normalized child
projections 由 parent getter read-back。`append_distillation_closure()` 只接受
`dead_letter/cancelled`，successful Completion 只能由 `commit_distillation()` 与
Knowledge/Batch/Report 在同一 Ledger transaction 写入。

跨 Store 调用拓扑是显式的：Runtime control transaction 只负责 grant 并提交 immutable
authorization/proof；它不在 control thread 内同步调用 Ledger。独立、system-owned
Commit Coordinator 在**没有任何 Runtime 或 Ledger write transaction**时通过 read-only
Runtime service 取得并验证 proof/proposal/plan，关闭该 read request 后才打开 Ledger
transaction。Ledger commit 完成后 Coordinator 再把 receipt/ref 交给 Runtime reconcile。
Runtime control 因此可以并发服务 proof getter，不会产生 control→Ledger→control
self-deadlock。GRANTED proof 在 arbitration 结束前不可撤销；Pause/Cancel/failure 只能按
规定 busy/pending，因此 Store 在本地 transaction 中验证已 read-back 的 immutable
digest-bound proof 不存在 revoke TOCTOU。禁止持任一 SQLite write transaction 做
跨-store IPC；process-kill/restart/deadlock contract test 必须覆盖该拓扑。
若 lifecycle expected-head 已失效，helper 必须在任何 Batch/Knowledge write 前走
`DistillationNoCommitReceipt` 分支：semantic transaction 写入为 0，只追加并 read-back
一个 typed `DistillationCommitConflict`。Runtime 只有验证该 conflict 后才能 retire
authorization、递增 generation/fence 并重新 propose；旧 authorization 随后不可再用。

两个 terminal-coverage getter 都要求 Runtime-authored barrier proof：它内嵌 exact
`TerminalBarrierFreezeProof`，绑定 Run/spec/manifest（campaign 时）、freeze ID/递增 epoch/
candidate terminal kind、`new_work_admission_closed=true`、无 unresolved relevant
authorization、current control event/fence 和 proof digest。pending cancel/failure 的早期
gate-close event 不可冒充 terminal freeze；normal success 也必须产生 freeze。Store 验证
proof 后在**一个**
read transaction 固定 ledger frontier，并返回该 frontier 下按 canonical IDs 排序的完整
集合与 coverage digest：

- `DistillationCampaignCoverageProof` 枚举所有引用 campaign Run 的 Assignment、
  Completion、Work Item 和 Activity ID，不分 terminal/incomplete；Runtime 与 exact
  manifest 比较，能证明 missing/duplicate/foreign=0；
- `DecisionIntentCoverageProof` 枚举该 Run 的每个 Ledger Intent、admission metadata、
  optional Context/Outcome IDs/digests；Runtime 与全部 REGISTERING/OPEN+ phase 双向比较，
  能发现 Ledger-only orphan 与 Runtime-only ghost。

terminal CAS 必须重验 barrier proof freeze ID/epoch/terminal kind/control event/fence 并绑定
coverage frontier/digest；
旧 proof 不能完成 Run。getter 不得用 `list_assigned_incomplete_distillation()` 或 Runtime
自身 phase 代替，因为二者都无法证明不存在已完成 foreign row。

`InMemoryExperimentLedger` 和 `SQLiteExperimentLedger` 是两个真实 Adapters，均
满足相同 contract suite。`capture_verified_evidence()` 在一个 Store lock / SQLite
`BEGIN IMMEDIATE` transaction 内先按 `capture_operation_id` 查询 mapping；exact
request 立即返回原 snapshot/journal receipts，different request conflict。只有 mapping
缺失才确定当前单调 Evidence frontier、选择 exact members、
交叉验证 canonical Hypothesis/Attempt/Observation/Verification/Intervention/
Trial Provenance，再原子提交 snapshot/members、capture-operation mapping 及各 canonical
journal rows。调用方不能先拿 timestamp/cutoff 再单独 query。

`KnowledgeSnapshotBuilder` 唯一拥有 lifecycle fold 与 member selection；Store
只加载 immutable state 并提交预计算 snapshot，不能再实现第二套 `freeze` 规则。

以上公开 Interface 中出现的 request/state/receipt 类型都定义在
`memory_models.py`：`FreezeEvidenceRequest`、`FreezeKnowledgeRequest`、
`ComposeRecallInputRequest`、`DistillationRequest`、`DistillationProposal`、
`DistillationBatch`、`DistillationReport`、`DistillationCommitReceipt`、
`DistillationNoCommitReceipt`、`DistillationCommitConflict`、
`DistillationWorkDisposition`、
`DistillationCommitAuthorizationProof`、`DistillationClosureAuthorizationProof`、
`DistillationTerminalReceiptRef`、`DistillationCampaignAdmissionProfileRef`、
`WorkItemProfileArtifactProof`、`DistillationEnqueueRecoveryRequest`、
`DistillationEnqueueRecoveryProof`、
`DistillationEnqueueObligationAbandonedProof`、
`CampaignBarrierReadProof`、
`DistillationCampaignCoverageProof`、`DecisionIntentBarrierReadProof`、
`DecisionIntentCoverageProof`、
`RetentionReconciliationProof`、
`ImmutableMemoryState`、
`EvidenceSnapshotCommitReceipt`、`SnapshotCommitReceipt` 和
`LedgerAppendReceipt`。名称
`DistillationReceipt` 禁用，避免与每个 Experience 的
`ExperienceDistillationReceipt` 混淆；不存在泛化的 `MemoryRecord` persisted model，
读取 Interface 返回明确 union。

`enqueue_distillation()` 的 contract 是：`queued_for_comparison` 必须与一个唯一 Work
Item 同事务写入，且 Store 必须 read-back Work Item 所指的 content-addressed Campaign
Admission Profile。queued 调用必须携带 Runtime getter 返回的
`WorkItemProfileArtifactProof`；proof 绑定 handoff/ref ID、object digest/generation、
owner=`DISTILLATION_WORK_ITEM:<work_item_id>`、profile ref/digest、Artifact Store event
seq、`ACTIVE` ref state、`PENDING` handoff state，以及 current
`enqueue_attempt_id/generation/fence/state=IN_FLIGHT`。Store 重算 Work Item ID 和
deterministic ref/handoff IDs、验证 proof digest 与所有字段 exact equality，并把
`campaign_profile_artifact_ref_id` 作为 immutable append metadata 写入 Work Item row，
并把 handoff/ref、attempt ID/generation/fence、proof digest 与 ordered transaction digest
写入专用 `distillation_enqueue_transactions_v1` sidecar/enqueue receipt。因 immediate
FK，物理 insert/journal 顺序固定为 Work Item → queued ingestion receipt → enqueue
sidecar；三条 canonical rows 在同一 Ledger transaction 内提交。Store 先按
deterministic Work Item/Experience 查询已提交 transaction：
same payload/ref 的 replay 按原 proof/receipt digest 返回原 transaction（即使 Runtime
随后已经 `BOUND`），different payload/ref conflict。首次 insert 只接受 exact current、
未 fenced 的 `IN_FLIGHT` proof；reply-loss exact retry 可接受 `BOUND` read-back 并返回原
transaction/original proof digest，不以当前 handoff-state proof 重写 canonical receipt；
`NOT_STARTED`/retired attempt、`RELEASED`、inactive、foreign、stale object generation
或任一 mismatch 均
fail closed。`deferred_ineligible|not_required` 必须给 `work_item=None`、
`abandoned_work_item=None` 且两个 proof 都为 null；queued 要求 committed `work_item`，
并禁止 `abandoned_work_item/abandonment_proof`。`abandoned_before_enqueue` 给
`work_item=None/profile_artifact_proof=None`，但必须携带 frozen
`abandoned_work_item` 和经 Runtime getter 独立 read-back 的 exact abandonment proof。
Store 重算 frozen payload digest 与 Work Item ID，逐字段核对其 Experience、namespace/
scope、Distillation/Lifecycle policy、Campaign Admission Profile lineage 与 proof/receipt，
只把 abandoned Work Item ID/payload digest/proof ref+digest 写入 receipt，绝不插入 Work
Item row。unassigned scan 只返回既无
Assignment 又无 Completion 的 item；assigned-incomplete scan 只返回指定 campaign
Run 已分配但无 Completion 的 item，均返回 `(entry, commit_position)`、稳定排序和
`next_cursor`，禁止调用方从裸 payload 猜 position。
`page_after_position` 只是一次 sweep 内的无状态分页 cursor，不是 durable ack；每次
进程启动/恢复和每轮 sweep 都从 `None`（最老 pending item）开始，只有成功 read-back
Completion 才让 item 从 pending 集合消失。Runtime
负责 Activity claim/lease/fencing；Store 不创建第二套 scheduler。

`abandoned_before_enqueue` 只用于 profile handoff 已建立、但 queued Ledger transaction
从未提交且 source control 已永久放弃该 exact attempt 的 terminal recovery。Memory Store
验证 abandonment proof 的 Work Item/handoff/current attempt/recovery request+ABSENT proof/
source Activity 后，还要用调用方携带的 frozen Work Item payload 重算 ID/digest，并核对
proof 内的 Experience 与完整 semantic lineage，才原子追加该 Experience 的唯一 receipt；
Runtime 必须 read-back receipt
ID/digest 后才可 `ORPHAN_ABSENT/RELEASED`。它不能用于已存在 Work Item、不能伪装
eligibility decision，也不创建 distillation work。
该分支的调用形状固定为

```python
enqueue_distillation(
    receipt,
    work_item=None,
    abandoned_work_item=frozen_work_item,
    profile_artifact_proof=None,
    abandonment_proof=proof,
)
```

queued builder 的顺序固定且不可合并成“先写 Ledger、稍后 pin bytes”：

1. 向 Runtime Artifact Store 发布 Campaign Admission Profile content-addressed bytes；
2. 用 Experience、两套 policy identity 和 profile ref/digest 计算 Work Item ID；
3. 在一个 Runtime Durable Transition 中创建由
   `DISTILLATION_WORK_ITEM:<work_item_id>` 拥有的 deterministic `ACTIVE`
   `runtime_artifact_ref` 与 `PENDING` handoff；再由同一个 Runtime writer transaction
   CAS `NOT_STARTED -> IN_FLIGHT` 并分配 attempt ID/generation/fence，之后 getter 才返回绑定该
   active attempt 的 proof；
4. 调用并 read-back `enqueue_distillation()`；
5. Runtime 独立读取 exact Work Item、enqueue receipt 和
   `get_distillation_enqueue_transaction()` sidecar，逐字段核对 attempt
   ID/generation/fence、original proof/transaction digests 后，才以 receipt+sidecar
   refs/digests CAS handoff `IN_FLIGHT/PENDING -> LEDGER_PRESENT/BOUND`；若 recovery 已
   retire 同一 attempt，old-fence drain 后的 exact request-bound `QUEUED_PRESENT` proof 加同一组
   rows/sidecar 允许 `RETIRED/PENDING -> LEDGER_PRESENT/BOUND`。

orphan recovery 必须先停止 coordinator，以 higher-fence Runtime CAS retire 旧 attempt，
等待所有旧-fence Ledger transaction 结束，再读取**后续 Ledger frontier**。
`DistillationEnqueueRecoveryProof=QUEUED_PRESENT` 加 exact Work Item/receipt/enqueue sidecar 时，
必须把该 attempt 从 `RETIRED` 置为 `LEDGER_PRESENT` 并 bind；这覆盖旧 transaction 在
retire/drain 期间最终 commit。只有 request-bound `ABSENT` 才可把该 attempt 的
journal-backed state 从 `RETIRED` 置为 `PROVED_ABSENT`。absence 分支的 handoff/ref 仍
保持 `PENDING + ACTIVE`；普通 source retry 必须在同一
handoff 下 append higher-generation/higher-fence `IN_FLIGHT` attempt。只有 Runtime 另行
read-back `DistillationEnqueueObligationAbandonedProof`，绑定相同 Work Item/source
Activity/handoff/current attempt ID/generation/fence、该 attempt row byte-equal 的
later-frontier recovery-proof pair、terminal control cause 与不可逆
no-future-retry disposition，且 Memory Store 已 append/read-back exact
`abandoned_before_enqueue` receipt，才可 `ORPHAN_ABSENT/RELEASED`。不能在发出/仍可消费 proof
的同一时刻宣称 absent，普通 timeout/not-found 永不释放 ref。

Work Item ID projection 包含 profile ref/digest，但排除从它确定性派生的
`campaign_profile_artifact_ref_id`；该字段是 immutable append metadata，避免
Work Item ID ↔ artifact-ref ID hash cycle。source Run record-closure 对每个 queued
receipt 还必须 read-back `BOUND` handoff 与 `ACTIVE` ref，之后才可释放 source-owned
staging/profile ref；Work-Item-owned ref 不属于 source Run 的 operational-settlement
denominator。

恢复器逐 seam 收敛：Runtime ref/handoff 已 commit 而 Ledger enqueue 未知时，用
deterministic Work Item ID 调 `get_distillation_work_item()` 和
`get_distillation_enqueue_receipt()`；exact row/receipt/sidecar 存在就 bind，即使同一
attempt 已在 recovery 中进入 `RETIRED`，也可在 old-fence drain 后经 exact
`QUEUED_PRESENT`
proof 单调进入 `LEDGER_PRESENT`。只有在一个固定
Ledger frontier 上得到 Work Item/receipt absence proof，且 Runtime 证明没有 in-flight
enqueue authorization/attempt 时，才把该 attempt 标为 `PROVED_ABSENT` 并保持 handoff/ref
为 `PENDING + ACTIVE`；后续 normal retry 创建 higher-generation/fence attempt。只有再有
exact `DistillationEnqueueObligationAbandonedProof` 和 independently read-back matching
abandoned receipt 才能显式释放 pre-enqueue orphan ref；
普通 not-found/timeout 不能释放。Ledger commit 已完成但 bind reply 丢失时，同一 read-back
直接完成 bind。恢复不得重发不同 Work Item/profile，也不得让 `PENDING` bytes 参与 GC。
Runtime 必须先从 handoff 冻结 canonical Work Item projection，并将其放入
`DistillationEnqueueRecoveryRequest`；request 绑定 request ID/digest、Experience ID、
Work Item ID/payload digest、handoff/ref 与 exact attempt
ID/generation/fence；Store getter 接受该 request 而非裸 Work Item ID。
`DistillationEnqueueRecoveryProof` 是同一 fixed-frontier read 的三臂 typed union，三臂都
回绑 request ID/digest、Experience/Work Item lineage 和 attempt triple：
`QUEUED_PRESENT` 携带 exact Work Item、queued ingestion/enqueue receipt、sidecar
IDs/digests 和 artifact ref ID；`ABANDONED_PRESENT` 携带 Work Item/sidecar absence、exact
`abandoned_before_enqueue` receipt ID/digest、abandoned Work Item payload digest 与 Runtime
abandonment-proof ref/digest；`ABSENT` 携带 Ledger frontier 与 Work Item row、enqueue
sidecar 以及该 Experience 的任意 Distillation Receipt 均不存在的 coverage digest。
任一 deferred/not-required receipt、partial queued rows 或 lineage mismatch 是 integrity
error，getter fail closed 而不伪造某个 union arm。
Runtime 只接受 Store 单 read transaction 产生并可复算的 proof。
每个 enqueue attempt 另有 append-only Runtime identity/history；handoff row 只投影 current
attempt ID/generation/fence/state。`PROVED_ABSENT` attempt 永不重新激活，retry 必须创建
新 attempt。`DistillationEnqueueObligationAbandonedProof` 是 Runtime control-owned strict
record；release 必须重验其 attempt triple 仍是 current `PROVED_ABSENT`。不可由 memory
caller、timeout、旧 attempt 或裸 absence proof自行构造。

source Run terminal、Assignment、campaign Run admission 都不释放此 root。只有 source
barrier 的 `BOUND + ACTIVE` acknowledgement 已 durable read-back、exact Work Item 已有
terminal `DistillationWorkCompletion`，并且 campaign Run replay/audit retention 已建立其
独立 `ACTIVE` ref 或其 retention 已过期，Runtime 才可提交/read-back
`BOUND -> RELEASED` 和 `ArtifactReferenceReleased`。Experiment Ledger 从不直接改变
artifact ref state；Runtime Artifact Store 是唯一 byte-GC authority。

`DistillationCampaignManifest` 由 Runtime 的 content-addressed Artifact Store/RunSpec
owner 持久化，不进入 memory canonical tables。admission projector 必须先通过 Runtime
public read Interface 得到 `DistillationCampaignRuntimeProof`，证明 manifest ref/digest
可 read-back、Run kind 是 `MEMORY_DISTILLATION`、Run 非 terminal、expected Run
version/Activity generation，以及 Activity 归该 Run且处于 `AWAITING_ASSIGNMENT`；
Experiment Ledger 只保存 proof projection 和 refs。两 Store 无分布式事务，
projector 用 shared helper 从 Work Item ID 派生 Runtime `DriveRun` admission key、Run ID
和 initial command ID 来重建/查找 campaign Run（manifest digest 是 spec input，不是
admission key），再以 stable assignment ID
reconcile。

manifest publish 后先在 Runtime transaction 中创建由 deterministic initial command/
admission-attempt ID 拥有的 temporary `ACTIVE` artifact ref；`DriveRun` admission 在同一
Runtime authority 内验证 staged bytes/digest，并原子创建 Run-owned ref 后才释放
temporary ref。reply loss 以同 command/ref ID reconcile；GC、orphan cleanup 与 admission
并发不能删除这两个 handoff state 的 bytes。

`get_distillation_assignment_proof()` 是 campaign Runtime Stage Adapter 唯一允许读取
Experiment Ledger assignment 的窄 read-only Seam；proof 绑定 assignment payload
digest、manifest member ordinal/digest、campaign Run/Activity、ledger commit position
和 proof-schema digest。Runtime 必须重新 read-back 后以 Run version + Activity
generation CAS 激活 Activity，不能信任 projector 传入的 bool 或旧 proof。
Run version、current generation/fence 只是 append/activation 时的 mutable validation
input，不进入 immutable Assignment payload 或 Assignment ID；Assignment 只保存创建时
稳定的 Run/Activity identity 与 manifest membership，避免 Runtime 版本前进后 exact
retry 变成 same ID/different payload。

### 5.2 Knowledge Distiller

```python
class KnowledgeDistiller:
    def propose(self, request: DistillationRequest) -> DistillationProposal: ...

class DistillationCommitCoordinator:
    def prepare(
        self,
        proposal: DistillationProposal,
        attempt: DistillationCommitAttemptIdentity,
    ) -> DistillationCommitPlan: ...
    def commit(
        self,
        plan: DistillationCommitPlan,
        authorization: DistillationCommitAuthorizationProof,
    ) -> DistillationCommitReceipt | DistillationNoCommitReceipt: ...
```

硬性 Interface 语义：

- request 必须绑定 exact Evidence Snapshot、trusted ledger position、scope 和
  Distillation + Lifecycle policy digests；
- caller 不得传入自行挑选的 `related: list[ExperienceRecord]` 作为真相；显式
  source IDs 也必须由 Store 重新校验；
- executor/LLM worker 只能返回 immutable、content-addressed proposal artifact，不能
  写 Knowledge、Batch、Report 或 Completion；
- proposal 必须冻结它读取的每个 affected `scope_variant_id -> expected lifecycle head`
  以及 singleton Work Item 的 typed Work Disposition proposal；
- shared helper 先由 Assignment/Run/Activity/generation/attempt ordinal/logical Effect
  派生不依赖 outputs 的 authorization ID；Coordinator 的纯 `prepare()` 再从 proposal
  和该 attempt identity 计算 exact Candidate/Decision/Memory/Event/Batch/Disposition/
  Report canonical bytes、IDs/digests 与 affected-head projection，发布 immutable
  `DistillationCommitPlan` Runtime artifact；此步不写 Ledger；
- Runtime read-back plan/proposal 后，在 current Run version + Activity generation/fence
  上以单次 CAS 赢得 `RUNNING -> COMMITTING` 并持久化唯一 authorization。authorization
  payload pins plan/proposal refs/digests 和 expected Batch/Report IDs/digests；其 ID 本身
  排除 outputs，避免 hash cycle；
- grant 后 Coordinator 才以已知 authorization payload digest 构造 Completion，并把
  exact plan + Completion + proof 交给 Store。Store 重算全部 bytes/IDs/digests，Report
  虽已在 plan 中预计算但只在 successful atomic transaction 内首次持久化；
- `DistillationReport` 在 atomic commit 成功前不得报告 promoted；
- canonical `DistillationReport` 只含确定性语义结果、coverage 和
  affected-active-view digest；后者只覆盖 proposal 中 sorted affected scope-variant 的
  final memory/head/disposition，不是 namespace-global view；
  invocation cost、transient errors、timing/logs 属于 Runtime Effect telemetry/sidecar，
  不进入 Report immutable payload 或 ID；
- crash/replay 使用 content-derived batch/candidate/record/event IDs；
- typed no-commit conflict 只 retire 当前 authorization attempt；Coordinator 必须
  read-back conflict、递增 generation/fence 后重新 propose，不能把它报告为
  dead-letter、cancelled 或成功；
- 一个 batch 内 candidate、decision、record、evidence links 和 lifecycle event
  要么全部 commit，要么全部不可见；
- `defer` 是正常决策，Research Run completion 不要求单次 Experience 立即变成
  active Knowledge。

### 5.3 Memory Acceptance Harness

```python
class AcceptanceArtifactStore(Protocol):
    def get_shared_manifest(
        self, proof: SharedManifestReceiptProof
    ) -> MemorySharedIdentityManifest: ...
    def get_stage_manifest(
        self, proof: StageManifestReceiptProof
    ) -> MemoryStageManifest: ...
    def get_acceptance_root(
        self, proof: AcceptanceRootReceiptProof
    ) -> MemoryAcceptanceManifest: ...
    def get_release_artifact_set(
        self, proof: AcceptanceReleaseArtifactSetProof
    ) -> PreValidationArtifactSet: ...
    def put_validation_receipt(
        self, receipt: AcceptanceValidationReceipt
    ) -> AcceptanceValidationReceiptProof: ...


class MemoryAcceptanceHarness:
    def __init__(
        self,
        registry: StageCampaignRegistry,
        artifacts: AcceptanceArtifactStore,
    ) -> None: ...
    def run_offline(
        self, shared: SharedManifestReceiptProof, stage: StageManifestReceiptProof
    ) -> StageArtifactSet: ...
    def run_ideation(
        self, shared: SharedManifestReceiptProof, stage: StageManifestReceiptProof
    ) -> StageArtifactSet: ...
    def run_causal(
        self, shared: SharedManifestReceiptProof, stage: StageManifestReceiptProof
    ) -> StageArtifactSet: ...
    def assemble(
        self, root: AcceptanceRootReceiptProof
    ) -> MemoryAcceptanceReport: ...
    def validate(
        self, release: AcceptanceReleaseArtifactSetProof
    ) -> AcceptanceValidationReceiptProof: ...
```

它只是验收 orchestration Module：指标实现仍分别归 writer/retrieval/utilization/
causal runners。每个 public method 必须先由 `AcceptanceArtifactStore` read-back proof 的
canonical object/ref/digest；裸 Pydantic object、path 或 caller ClaimReport 不构成 authority。
`ClaimReport` 只是 validation 的中间产物，只有 exact-once 写入并再次 read-back 的 signed
`AcceptanceValidationReceipt` 是 terminal result。每个 `run_*` 再经 registry
admission/read-back 取得 hidden-data token，
退出前写 terminal closure；`assemble` 从 root 的 registry frontier 枚举 exact lineage，
再对 stage root 做 digest read-back、完整 sibling/overlap/applicability 校验和 requirement
join，不能把调用方传入的成功 shard 列表当权威。生产 memory 包不依赖 benchmark 包。

### 5.4 Decision-Point Retrieval

```python
DecisionRecallPreparationResult = (
    DecisionRecallContextProposal | DecisionRecallBlockedProposal
)


class DecisionPointRetriever:
    def propose(
        self, intent: DecisionIntent, request: DecisionRecallRequest
    ) -> DecisionRecallPreparationResult: ...
```

硬性 Interface 语义：

- request 缺 Decision Intent、Recall Input Snapshot、policy digest、scope 或
  allowed action 时返回 `DecisionRecallBlockedProposal`，不能抛出一个未持久化的宽泛
  error、退化为宽泛 query 或 abstain；
- current Observation/failure signature 是 typed nullable；没有 prior Attempt 时必须
  携带 `no_prior_observation` reason，缺字段和合法 null 不得混同；
- hard filter 在 candidate 文本进入 actor 之前执行；
- `status=empty` 只表示健康检索没有 eligible evidence；`status=degraded` 只表示
  policy 允许的基础设施/Adapter fallback；request/private/corruption/
  contamination/identity 问题一律 blocked；
- result 默认最多 3 cards、完整 rendered section 的 1,200 exact tokenizer tokens；
- retriever 只构造 closed preparation result：成功为 immutable
  `DecisionRecallContextProposal`，阻塞为 immutable `DecisionRecallBlockedProposal`；两者
  都先发布到 Runtime Artifact Store，不直接写 Experiment Ledger；
- Blocked proposal 必须绑定 authoritative Intent ID/digest、request/retrieval-policy
  digest、nullable exact Recall Input ID/digest、closed blocked reason，以及按 reason
  discriminated 的 typed evidence，禁止 free-form dict、exception text 或 private bytes。
  canonical Recall Input 已 read-back 时 ID/digest 必须 exact non-null；尚未形成或因损坏
  无法 read-back 时两者必须同时为 null，并由对应 evidence 携带 attempted expected ref；
- reason-specific evidence union 至少封闭为：request-invalid 的 canonical field
  violations/request-schema digest；identity/policy-mismatch 的 expected/observed IDs/digests；
  corrupt-input 的 attempted ref/integrity evidence；contamination/private-exposure 的 violated
  rule 与 redacted member/field identities；retention-revoked 的 exact `RetentionCheck`。
  retention branch 必须逐字节绑定同一 non-null Recall Input ID/digest、frontier、
  tombstone-set digest 和 canonical sorted blocked targets；
- Runtime 必须先持久化并 read-back Blocked proposal，再由 strict
  `get_decision_recall_blocked_proof()` 解析 producer/object/proposal identity 和全部字段；
  只有该 proof 可进入 blocked Outcome proposal/authorization。Context proposal 则经 Runtime
  read-back、digest-bound authorization 和 Store exact append/read-back 后，已提交 Context
  才可交给 actor；
- 相同 request/snapshot/policy 的最终排序和 card IDs 稳定；
- online path 不调用生成式模型。

### 5.5 Runtime Decision Recall

`ExperienceRunAdapter` 新增：

```python
def prepare_required_decision(
    self,
    *,
    intent: DecisionIntent,
    contract_view: DecisionContractViewRef,
    intervention_catalog: InterventionCatalog | None,
    previous_feedback: PreviousAttemptFeedback | None,
    recall_input_snapshot_id: str,
) -> DecisionRecallPreparationResult:
    ...

def commit_required_decision_context(
    self,
    *,
    proposal: DecisionRecallContextProposal,
    authorization: DecisionRecallCommitAuthorizationProof,
) -> DecisionRecallContext:
    ...
```

两个 Interface 只接受 read-back `recall_requirement=REQUIRED` 的 Intent；registered
not-requested path 不调用它，也不创建 Recall Input/Context。首版只允许
`decision_point="intervention"` 进入 active rollout。`DecisionIntent`
在调用前预分配 run/activity/iteration/generation/arm/pair、Research Context ref、
logical decision slot/artifact kind、allowed-action digest，以及从 admitted Run/arm
manifest 复制的 pinned planned actor model/config/template/policy refs/digests 和
`MemoryGovernanceBinding`：exact `memory_profile_ref/digest`、
`memory_assignment_manifest_ref/digest` 与 closed
`recall_requirement=REQUIRED | REGISTERED_NOT_REQUESTED`。`append_decision_intent`
必须用 `DecisionIntentAdmissionProof` 经 Runtime read Interface read-back 相同 Run spec/
manifest/profile bytes 后才提交；proof/Intent mismatch fail closed。实际 artifact ID/digest
在 terminal outcome 绑定。`DecisionContractViewRef` 是
Evaluation Contract 的内容寻址 actor-visible projection，MUST 排除 entrypoint、
evaluator files、`private_data_dir`、private labels/answers/secrets。Request 从该
view、Intervention Catalog、PreviousAttemptFeedback 和 frozen snapshots 结构化
生成，而不是从 CLI query 拼 prose。

`prepare_required_decision()` 返回 closed `DecisionRecallPreparationResult`。Context
proposal 先作为 scoped content-addressed Runtime artifact 发布；Runtime read-back 后才能按
expected Context ID/payload digest/proposal ref/digest 发 `APPEND_CONTEXT` authorization，
`commit_required_decision_context()` 也只接受该分支的 exact bytes。Blocked proposal 同样
必须先发布/read-back，但绝不申请 Context authorization；Runtime 以 strict getter 再读出
`DecisionRecallBlockedProof`，并把同一 proof ref/digest 绑定到 blocked Outcome proposal、
`APPEND_OUTCOME/NORMAL` authorization 与最终 Outcome。不允许“先授权空槽，再由 retriever
决定内容”，也不允许把内存中的 error 直接翻译成 blocked Outcome。

`DecisionContractView` v1 只包含 contract ID/version/public digest、
`evaluation_task_id`、public `task_scope_id`、
Decision Point、primary metric name/direction/public baseline、public guardrails、
Budget class、Intervention Catalog/allowed-action digest 和公开 validity summary。
构造器使用 allowlist serialization，不能靠删除少数字段的 denylist。

### 5.6 Recall utilization

保留 Phase A 的 `InterventionProposal` / `InterventionRecord` v1 和
`ai-researcher/proposal/v1` digest，不向 frozen payload 加字段。Planner 新增外层
sidecar envelope：

```python
class RecallDispositionDraft(MemoryPayloadV1):
    citation_id: str
    disposition: Literal["adopted", "rejected", "not_considered"]
    reason_code: RecallDispositionReason
    mapped_target: str | None = None


class RequiredDecisionMemoryBinding(MemoryPayloadV1):
    binding_kind: Literal["required"] = "required"
    recall_input_id: str
    recall_context_id: str
    rendered_card_count: int
    rendered_token_count: int


class NoDecisionMemoryBinding(MemoryPayloadV1):
    binding_kind: Literal["registered_not_requested"] = "registered_not_requested"
    recall_input_id: None = None
    recall_context_id: None = None
    rendered_card_count: Literal[0] = 0
    rendered_token_count: Literal[0] = 0
    governance_binding_digest: str


class RecalledInterventionDecision(MemoryPayloadV1):
    decision_intent_id: str
    decision_memory: RequiredDecisionMemoryBinding | NoDecisionMemoryBinding
    proposal: InterventionProposal  # unchanged v1 payload
    recall_dispositions: list[RecallDispositionDraft]
```

规则：

- 非空 context 的每个 item 必须且只能出现一次；
- `RequiredDecisionMemoryBinding` 的 IDs/counts 必须逐项等于 read-back Input/Context；
  `NoDecisionMemoryBinding` 只接受 read-back
  `recall_requirement=REGISTERED_NOT_REQUESTED` 的 Intent，IDs 必须 null、counts/dispositions
  必须为 0，且 `governance_binding_digest` 必须逐字节等于该 Intent 持久化
  `MemoryGovernanceBinding` digest；
- adopted item 必须填写 mapped target；
- mapped target 必须在该 Evidence Card 和 Intervention Catalog 允许范围内；
- envelope 使用独立 `ai-researcher/recalled-intervention-decision/v1` digest；
- inner proposal 仍按 `ai-researcher/proposal/v1` 计算并写原 InterventionRecord；
- required binding 的新 context ID 作为原 `recall_snapshot_id` 的值；registered
  not-requested binding 对 InterventionRecord 与 ExperimentAttempt 都保留并验证既有
  canonical `"off"` sentinel，Outcome sidecar 绑定 `NoDecisionMemoryBinding`；两者都不
  改字段或 hash domain；
- system-resolved effective config 后生成 `RecallDecisionOutcome` sidecar；
- blocked/not-requested/empty/degraded/actor failure/proposal rejected/no-op/
  cancelled 仍生成 Recall Decision Outcome；actor timeout/crash/unparseable/schema-malformed
  output 确定映射为 `actor_failed + ACTOR_INVOCATION_FAILED|ACTOR_OUTPUT_MALFORMED`，通过
  policy/contract parse 但被 policy/preflight 拒绝才映射 `rejected`；不存在开放的
  `invalid` decision status；
- claimed adoption fidelity 和 execution fidelity 的验收分开统计。

## 6. Persisted models

### 6.1 新 model 命名

新 model 放在 `memory_models.py`：

```text
MemoryPayloadV1
TaskScopeIdentity
MemoryScope
DecisionTarget
DecisionContractView
DecisionContractViewRef
MemoryGovernanceBinding
DecisionIntentAdmissionProof
DecisionIntentClosureProof
DecisionRecallCommitAuthorizationProof
TerminalBarrierFreezeProof
DecisionIntentBarrierReadProof
DecisionIntentCoverageProof
DecisionRecallAppendReceipt
DecisionRecallNoCommitReceipt
DecisionIntentProposal
DecisionIntent
EffectEstimate
VerifiedEvidenceBundle
EvidenceLink
PolicyIdentity
MemoryRelation
FreezeEvidenceRequest
EvidenceSnapshotCaptureOperation
FreezeKnowledgeRequest
ComposeRecallInputRequest
DistillationRequest
DistillationProposal
DistillationCommitAttemptIdentity
DistillationCommitPlan
DistillationBatch
DistillationReport
DistillationCommitReceipt
DistillationNoCommitReceipt
DistillationCommitConflict
DistillationWorkDisposition
DistillationCommitAuthorizationProof
DistillationClosureAuthorizationProof
DistillationTerminalReceiptRef
ImmutableMemoryState
EvidenceSnapshotCommitReceipt
SnapshotCommitReceipt
LedgerAppendReceipt
DistillationEnqueueReceipt
DistillationEnqueueTransaction
DistillationCampaignAdmissionProfileRef
WorkItemProfileArtifactProof
DistillationEnqueueRecoveryRequest
DistillationEnqueueRecoveryProof
DistillationEnqueueObligationAbandonedProof
PositionedDistillationPage
KnowledgeCandidate
SemanticKnowledgeRecord
ProcedureRecord
ExperienceDistillationReceipt
DistillationWorkItem
DistillationAssignmentProof
DistillationWorkAssignment
DistillationWorkCompletion
DistillationCampaignRuntimeProof
WorkItemProfileArtifactProof
DistillationEnqueueRecoveryProof
CampaignBarrierReadProof
DistillationCampaignCoverageProof
DistillationDecision
KnowledgeLifecycleEvent
MemoryRetentionTombstone
RetentionErasureIntent
RetentionIntentCommitReceipt
RetentionCheck
RetentionReconciliationProof
ArtifactErasureReceiptProof
IndexInvalidationReceiptProof
PositionedRetentionPage
EvidenceSnapshot
EvidenceSnapshotMember
KnowledgeSnapshot
KnowledgeSnapshotMember
DerivedIndexBuildReceipt
DerivedIndexBuildFailure
RecallInputSnapshot
DecisionRecallRequest
EvidenceCard
DecisionRecallBlockedEvidence
DecisionRecallBlockedProposal
DecisionRecallBlockedProof
DecisionRecallPreparationResult
DecisionRecallContextProposal
DecisionRecallContext
DecisionPlannerMemoryInputArtifact
RecallDecisionOutcomeProposal
RecallDecisionOutcome
RecallOutcomeAttemptLink
```

`RequiredDecisionMemoryBinding`、`NoDecisionMemoryBinding`、
`RecallDispositionDraft` 和 `RecalledInterventionDecision` 是 Phase A Intervention
sidecar，唯一 owner 是 `research_agent/inno/experience/intervention.py`；
`memory_models.py` 不重复定义或 re-export 它们。

`ScientificClaimPlan`、`MemorySharedIdentityManifest`、`MemoryStageManifest`、
`MemoryAcceptanceManifest`、`RegistryTrustAnchor`、`RegistryAuthorityCheckpoint`、
`RetrievalAdapterSelectionReceipt`、`SharedManifestReceiptProof`、
`StageManifestReceiptProof`、`AcceptanceRootReceiptProof`、
`AcceptanceReleaseArtifactSetProof`、`AcceptanceValidationReceiptProof`、
`StageCampaignAdmissionReceipt`、`HiddenPoolExposureReceipt`、
`VisibilityNotIssuedReceipt`、`StageCampaignClosureReceipt`、typed lineage/global
`StageCampaignRegistryFrontier`、`SealedPartitionManifest`、
`PartitionNonOverlapReceipt`、`ConfirmatorySelectionReceipt`、`PilotGateReceipt`、
`PilotPrerequisiteAssessment`、`StageArtifactSet`、`StatusProvenance`、`RequirementCheck`、
`PreValidationArtifactSet`、
`StageTerminalOverrideCheck`、`CostPerValidImprovementScalar`、`TypedReportEnvelope`、`MemoryAcceptanceReport` 和
`AcceptanceValidationReceipt` 属于
validation domain，只定义在 `benchmark/memory/schemas.py`，不得成为 production
memory payload。

`DecisionIntentAdmissionProof`、`DecisionRecallCommitAuthorizationProof`、
`DecisionRecallBlockedProof`、`TerminalBarrierFreezeProof`、
`DistillationCampaignRuntimeProof`、`DistillationCommitAuthorizationProof`、
`DistillationClosureAuthorizationProof`、`DistillationTerminalReceiptRef`、
`DistillationTerminalReceiptProof`、
`DistillationEnqueueRecoveryRequest`、
`DistillationEnqueueObligationAbandonedProof`、
`ArtifactErasureReceiptProof` 和 `IndexInvalidationReceiptProof` 是
Runtime-owned canonical records 的 strict read models；Experiment Ledger 只在
Context/Outcome 或 Batch/Report/Completion 中保存其 exact ID/ref/digest/generation/
fence projection，不创建第二份授权真相。
`DecisionRecallBlockedProof` 是 Runtime Artifact Store 对
`DecisionRecallBlockedProposal` 的 strict read model：包含 artifact ref/digest、proposal
ID/digest、producer/object identity，以及 proposal 的 Intent、nullable Recall Input、reason
和 evidence 全字段；它不是 caller 可自行构造的授权声明。
`ArtifactErasureReceiptProof` 绑定 receipt ref/digest、namespace、target artifact/object
generation、incident/operation ID、terminal erasure state 和 Runtime event seq；
`IndexInvalidationReceiptProof` 另绑定 index build/artifact ref+generation、cache unload/
invalidation state与同一 incident。两者由 `RetentionRuntimeRead` getter 从 Runtime
canonical record read-back，versioned proof schema/domain 有 golden vectors；裸 digest、
foreign generation 或自报 bool 无效。
`DistillationCampaignAdmissionProfileRef` 指向 enqueue 前已发布的 content-addressed
configuration artifact；Work Item 固定其 ref/digest，projector 不得读取进程默认值覆盖。

不要重用旧 `KnowledgeRecord` 类名。旧类在迁移期 alias 为
`LegacyKnowledgeRecordV1`，原 import 保持兼容一个版本并发出 deprecation
warning；旧 JSON 仍由原类解析。

`MemoryPayloadV1` 使用 `extra="forbid"`、`frozen=True` 和
`schema_version: Literal["1"]="1"`。它不修改或继承旧 payload 的 hash projection；
每个新 payload 都有独立的 versioned domain。

`DecisionIntentProposal`、`DecisionRecallContextProposal`、
`DecisionRecallBlockedProposal` 与 `RecallDecisionOutcomeProposal` 是 scoped Runtime
artifact payloads。Intent/Context/Outcome proposal 各自包含最终 canonical record 的 exact
bytes、record ID、payload digest、producer identity 和 source receipts；Blocked proposal
包含自身 content ID/digest、authoritative Intent binding、nullable exact Recall Input binding、
closed reason 与 reason-specific typed evidence。它们本身都不是 Experiment Ledger canonical
record。Runtime 只能在 artifact read-back 后为 exact target 发 commit authorization；Store
append 后 proposal 不替代 canonical getter/read-back，Blocked artifact 也必须在 blocked
Outcome 的审计保留期内可由 strict getter 重读。

Intent/Context/Outcome 的 digest order 严格无环：先计算不含 authorization linkage 的 canonical
record ID/payload digest，随后发布 proposal；Runtime 再创建绑定 proposal/expected record
的 authorization；最后 Store 在同一 transaction 写 canonical record 与 immutable
authorization ID/digest append metadata。authorization linkage 不得回写 canonical JSON
或 record ID。三种 record 的 golden vectors 必须证明改变 authorization 只改变 append
metadata，而改变任一 semantic field 会改变 expected record/proposal/authorization digest。

`DecisionPlannerMemoryInputArtifact` 包含 Intent ID、actor slot、closed
`RequiredDecisionMemoryBinding | NoDecisionMemoryBinding` union、canonical rendered bytes/
digest 和 producer identity。Runtime 在 model Effect preparation 前发布/read-back 它；
model Effect request、Outcome proposal/authorization 和 final Outcome 全部绑定同一 artifact
ref/digest。Artifact Store 保留期至少覆盖 Run audit/Outcome retention，getter 必须可重算
payload digest；单独一个 caller-supplied binding digest 不构成 lineage proof。

### 6.2 ID 规则

所有新逻辑 ID 都复用现有 `semantic_digest(domain, value)` 的严格 JSON、有限数值、
domain separation 和 raw lowercase 64-hex 约定。新增 `memory_semantic_digest()` 只做
semantic projection 规范化后调用该 helper，不改变 Phase A helper 或任何旧 ID。

规范化规则：所有 identity string 必须先 NFC；dict key 排序；bool 不可冒充 int；
float 必须有限，作为 identity 的 decimal metric 使用规范 decimal string；真正具有
语义的 datetime 统一为 UTC RFC3339 microseconds，审计 `created_at` 不进入 ID；
ledger cutoff 使用整数 position 或 explicit members，不使用 wall clock。

虽然 `created_at` 不进入 logical ID，它仍参与 immutable payload equality，必须来自
首次已持久化的 Runtime Activity/Decision Intent/commit-attempt timestamp。尤其
Distillation Commit Plan 在 grant 前就把该 commit-attempt timestamp 写入全部拟提交
Batch/Report/output payload；Store 只复用，不能在 Ledger transaction 内调用 `now()`。
retry 复用该值，禁止在重放时生成不同 payload。

| ID | Versioned hash domain | semantic projection MUST include | MUST exclude |
| --- | --- | --- | --- |
| `candidate_id` | `ai-researcher/knowledge-candidate/v1` | Evidence Snapshot, source IDs, normalized proposal, drafting/policy identity | created_at, cost |
| `task_scope_id` | `ai-researcher/task-scope/v1` | taxonomy registry ID/version, public task family/problem-type attributes | evaluation-task instance ID, seed, private/evaluator labels |
| `contract_view_id` | `ai-researcher/decision-contract-view/v1` | source contract digest, allowlisted actor-visible projection | private/evaluator fields, created_at |
| `experience_distillation_receipt_id` | `ai-researcher/experience-distillation-receipt/v1` | Experience ID, disposition, Distillation Policy ID/digest, nullable committed Work Item ID, nullable abandoned Work Item ID + frozen payload digest + abandonment-proof ref/digest | created_at, retry count, lifecycle/retrieval policies |
| `distillation_work_item_id` | `ai-researcher/distillation-work-item/v1` | Experience ID, namespace/scope, Distillation + Lifecycle policy IDs/digests, Campaign Admission Profile ref/digest | deterministic `campaign_profile_artifact_ref_id` append metadata（由此 ID/profile digest 派生以避免 hash cycle）, claim/lease, created_at, any separate idempotency key |
| `distillation_enqueue_transaction_id` | `ai-researcher/distillation-enqueue-transaction/v1` | Experience/Work Item IDs, handoff/artifact-ref IDs, enqueue attempt ID/generation/fence, original profile-proof digest, ingestion-receipt ID/digest, Work Item payload digest | current handoff state, later attempts, journal positions, created_at |
| `distillation_work_assignment_id` | `ai-researcher/distillation-work-assignment/v1` | Work Item ID, campaign manifest ref/digest, `MEMORY_DISTILLATION` Run ID, stable Activity ID | lease/claim, Run terminal state after assignment, created_at |
| `distillation_activity_id` | `ai-researcher/distillation-activity/v2` | campaign Run ID, Work Item ID (which already binds both policies) | free policy parameter, source Run ID, lease/claim/retry |
| `distillation_proposal_id` | `ai-researcher/distillation-proposal/v1` | request/Evidence Snapshot, scope, sorted Work Item/Experience/candidate/output projections, both policy identities, drafting Adapter identity | Runtime lease/fence, created_at, invocation cost/logs |
| `distillation_commit_plan_id` | `ai-researcher/distillation-commit-plan/v1` | proposal ref/digest, output-independent authorization ID, exact sorted canonical output bytes/IDs/digests, expected heads and affected-view projection | authorization payload digest, Runtime lease expiry, created_at, invocation telemetry |
| `distillation_commit_authorization_id` | `ai-researcher/distillation-commit-authorization/v1` | Assignment, campaign Run/Activity, Activity generation/fence, commit-attempt ordinal, logical Effect ID | proposal/output/plan payload, wall clock, lease expiry; Runtime exact-payload equality separately pins proposal + commit-plan artifacts and final Batch/Report IDs/digests |
| `distillation_closure_authorization_id` | `ai-researcher/distillation-closure-authorization/v1` | Assignment, campaign Run/Activity, Activity generation/control event sequence, terminal status, terminal receipt ref/digest | worker claim, wall clock, display reason |
| `distillation_work_completion_id` | `ai-researcher/distillation-work-completion/v1` | Work Item + Assignment IDs, campaign Run/Activity generation/fence, terminal authorization ID/digest, terminal status, nullable Batch ID + Report ID/payload digest or terminal receipt ref/digest | retry events, created_at |
| `distillation_batch_id` | `ai-researcher/distillation-batch/v1` | commit authorization ID/effect, request/Evidence Snapshot, scope, sorted Work Item/Experience/candidate IDs, Distillation + Lifecycle policy identities | Snapshot Selection/Retrieval identities, transaction position, created_at, invocation cost/logs |
| `distillation_report_id` | `ai-researcher/distillation-report/v1` | commit authorization ID/effect, Batch ID, exact Work Item/Experience coverage, sorted Work Disposition IDs (whose IDs bind typed status/evidence/reasons), sorted candidate/decision/memory/event/relation IDs and affected-active-view digest over sorted affected `(scope_variant_id,final_memory_id,final_event_id,disposition)` | namespace-global/unaffected heads, journal positions, created_at, invocation cost/logs/display errors |
| `distillation_commit_conflict_id` | `ai-researcher/distillation-commit-conflict/v1` | commit authorization ID/digest, proposal/proposed-Batch IDs, conflict kind + closed discriminated body: `LIFECYCLE_HEAD_STALE` binds sorted expected/observed scope heads and retention fields canonical null；`RETENTION_REVOKED` binds current retention frontier/set + sorted reachable blocked targets and head-delta fields canonical null；both predicates true deterministically selects `RETENTION_REVOKED` | retry timing, created_at, display error |
| `distillation_work_disposition_id` | `ai-researcher/distillation-work-disposition/v1` | Batch + Work Item/Experience IDs, disposition, nullable covering Decision ID, typed evidence/reason codes, both policy identities | report ordinal, created_at, display prose |
| `distillation_decision_id` | `ai-researcher/distillation-decision/v1` | Candidate ID, disposition, nullable memory ID, Distillation/Lifecycle policy identities | created_at, display reason prose |
| `family_id` | `ai-researcher/knowledge-family/v1` | record kind, Decision Point, normalized target, metric, mechanism class | scope, prose, evidence count |
| `scope_variant_id` | `ai-researcher/knowledge-scope-variant/v1` | family ID, normalized exact MemoryScope | evidence, disposition |
| `memory_id` | `ai-researcher/memory-record/v1` | semantic record projection, family/scope IDs, sorted canonical evidence-link **bodies excluding parent `memory_id` and `evidence_link_id`**, policy, prior memory ID | created_at, lifecycle disposition, display ordinal, child link IDs |
| `support_unit_id` | `ai-researcher/support-unit/v1` | comparison, run/seed, observation, Intervention/source/dataset/contract digests | import time, retry copies |
| `lifecycle_event_id` | `ai-researcher/knowledge-lifecycle-event/v1` | target, expected prior head/event, transition, reasons/evidence, policy | DB row order, created_at |
| `evidence_link_id` | `ai-researcher/memory-evidence-link/v1` | memory, canonical evidence IDs, relation, support-unit ID | DB row order, created_at |
| `memory_relation_id` | `ai-researcher/memory-relation/v1` | canonicalized source/target IDs, relation, causing lifecycle event, policy | DB row order, created_at |
| `evidence_capture_operation_id` | `ai-researcher/evidence-capture-operation/v1` | owner Run/Activity/generation, logical capture Effect, namespace/visibility purpose and stable decision slot | selected members/frontier, retry time, created_at |
| `evidence_snapshot_id` | `ai-researcher/evidence-snapshot/v1` | sorted member bundle IDs/digests, ledger position, namespace/arm/pair, eligibility policy | wall clock, later appends |
| `knowledge_snapshot_id` | `ai-researcher/knowledge-snapshot/v1` | sorted record/event heads, lifecycle position, selection policy, namespace | Retrieval/index policy, raw unrelated Experience, wall clock |
| `index_build_id` | `ai-researcher/memory-index-build/v1` | source snapshot IDs, Adapter/model/tokenizer/build identities, sorted vector/member digests | build time/path |
| `index_failure_id` | `ai-researcher/memory-index-failure/v1` | source snapshots, Adapter/policy identity, attempt key, retry ordinal, error code and failure-receipt digest | created_at, stack trace/path |
| `recall_input_snapshot_id` | `ai-researcher/recall-input-snapshot/v1` | Knowledge/Evidence snapshots, Retrieval/renderer/tokenizer policy, index build IDs | alias, wall clock |
| `decision_intent_id` | `ai-researcher/decision-intent/v1` | run/activity/iteration/generation/arm/pair, evaluation-task ID, public task-scope ID, point, Research Context ref, sanitized contract view, logical decision slot/artifact kind, allowed-action digest, memory-profile/assignment-manifest refs/digests and recall requirement | actor output, private labels/answers |
| `decision_recall_no_commit_id` | `ai-researcher/decision-recall-no-commit/v1` | authorization kind + ID/digest, Intent ID, transition kind, expected record ID/payload digest, closed reason, observed phase digest | created_at, transport error text, display diagnostics |
| `decision_recall_blocked_proposal_id` | `ai-researcher/decision-recall-blocked-proposal/v1` | authoritative Intent ID/digest, nullable exact Recall Input ID/digest, request/retrieval-policy digests, closed blocked reason, canonical reason-specific evidence（retention branch 含 exact check Recall Input ID/digest、frontier、tombstone-set digest、sorted blocked targets）和 producer/object identity | Runtime artifact ref, Outcome/authorization append metadata, created_at, free-form diagnostics/private bytes |
| `card_id` | `ai-researcher/evidence-card/v1` | common source kind/record ID+digest and typed applicability/action/effect/evidence/citations/renderer; for semantic/procedure: memory ID + family/scope/current lifecycle head; for episodic: Evidence Snapshot/member bundle/Verification identities + evidence frontier | Decision Intent, rank/ordinal, score, created_at; episodic excludes memory/lifecycle fields and memory cards exclude episodic fields |
| `citation_id` | `ai-researcher/recall-citation/v1` | Decision Intent ID, Recall Input Snapshot ID, card ID, final ordinal | Recall Context ID (avoids cycle), created_at |
| `decision_recall_id` | `ai-researcher/decision-recall-context/v1` | intent/request, Recall Input Snapshot, Retention Check digest/frontier/tombstone-set digest, status, canonical typed degradation reason/fallback identity, selected cards/rank evidence, rendered-context digest/tokenizer/count | diagnostic candidate counts/log ordering, created_at |
| `recall_outcome_id` | `ai-researcher/recall-decision-outcome/v1` | intent, optional context, semantic commit authority, source/decision/artifact status, source outcome reason + decision terminal reason, required blocked-proof ref/digest iff source blocked, planner-input binding ref/digest when invoked, required retention/failure/cancel receipt identities, planned actor identities plus canonical nullable executed actor/response/prompt identities, per-card dispositions, artifact/action/config mapping | commit authorization ID/digest append metadata, downstream verified outcome, display diagnostics, created_at |
| `outcome_attempt_link_id` | `ai-researcher/recall-outcome-attempt-link/v1` | Recall Outcome ID, Experiment Attempt ID | append position, created_at, later Attempt results |
| `retention_erasure_intent_id` | `ai-researcher/retention-erasure-intent/v1` | incident, namespace, target kind/ID/last digest, reason, required retraction event or typed N/A, external target/object generation, sorted affected index build/artifact identities, retention policy | external receipts, completion state, created_at |
| `retention_tombstone_id` | `ai-researcher/memory-retention-tombstone/v1` | target kind/ID/last digest, incident/reason, required retraction event or typed N/A, external erasure receipt ref/digest, sorted index-invalidation receipt refs/digests | created_at, operator display name |

Memory record version order 由 `prior_memory_id` 链和 lifecycle events 派生，不保存
依赖并发插入顺序的自增 `record_version`。所有 helper 都有 golden-vector tests。
其中 distillation conflict golden vectors 必须分别覆盖两个 discriminant，并证明另一
分支字段 canonical null、blocked-target order 不敏感且 kind 改变必换 ID。
Memory/link identity 使用固定两阶段算法：先规范化并排序 evidence-link bodies（只含
canonical evidence refs、relation、support-unit ID）计算 `memory_id`；再以
`memory_id + link_body` 分别计算 `evidence_link_id`。禁止 memory projection 包含 child
link ID，否则形成 hash cycle；golden vectors 必须显式验证顺序不敏感和无环。
没有独立 `record_id` 列的 child rows（例如 evidence link/relation）使用上表的
content-derived logical ID 作为 `ledger_commits_v1.record_id`；其 composite PK 仍是
SQL lookup key。任何新增 persisted logical record 在合并 schema PR 前必须先在此表
登记 domain/projection/exclusion 和 golden vector，不能借用另一类型的 hash domain。

### 6.3 Evidence strength

首版不用无校准的单一 `confidence: float`。使用：

```python
class EvidenceStrength(ImmutableModel):
    grade: Literal["single", "replicated", "strong", "contested"]
    independent_support_count: int
    independent_counter_count: int
    paired_comparison_count: int
    effect_consistency: float
    uncertainty_method: str
    reasons: list[str]
```

`effect_consistency` 是验证结果的确定性统计，不是模型主观概率。Promotion Policy
决定哪些 grade 可以进入 development/confirmatory snapshot。

### 6.4 Policy schemas

Phase 0 冻结四个 `extra="forbid"`、内容寻址的 policy payload；未知字段或版本
fail closed：

| Policy | v1 required fields |
| --- | --- |
| `DistillationPolicyV1` | eligible outcomes；canonical bundle requirements；comparison-stratum field list；support-unit projection；minimum independent/paired support；effect/guardrail method；candidate rejection reasons；drafting Adapter identity |
| `LifecyclePolicyV1` | legal transitions；contest/supersede/retract reason enums；evidence-strength thresholds；expected-head CAS；relation/cycle rules |
| `SnapshotSelectionPolicyV1` | namespace；allowed record kinds/dispositions/strength grades；scope-variant head rule；trusted lifecycle position；provisional/contested inclusion |
| `RetrievalPolicyV1` | Decision Point profile；exact-scope field list；allowed source kinds/actions；candidate limits；lexical/embedding/direct Adapter IDs；feature/weight/threshold spec；family diversity；fallback rules；renderer/tokenizer；item/token budget |

四个 payload 一一对应四个文件和 digest，禁止把前三种隐式塞进一个未经定义的
`writer` 配置：

| Fixture / CLI | 持久化位置 |
| --- | --- |
| `distillation-v1.yaml` / `--distillation-policy` | Experience receipt/Work Item、Candidate、Distillation Decision、memory record |
| `lifecycle-v1.yaml` / `--lifecycle-policy` | Knowledge Lifecycle Event、Memory Relation |
| `snapshot-selection-v1.yaml` / `--snapshot-selection-policy` | Knowledge Snapshot |
| `retrieval-v1.yaml` / `--retrieval-policy` | derived index request、Recall Input Snapshot、Recall Context |

每个文件经 canonical JSON projection 得到独立 content ID 和 raw digest；四个 ID/
digest 都进入 `MemoryAcceptanceManifest.policy_identities`。需要整体引用时，另计算
只含这四个有序 content ID 的 `policy_set_digest`，不得以一个 digest 代替各自身份。

首版 `MemoryScope` 的 namespace、`task_scope_id`、domain、dataset、tested-source、
model、environment、Evaluation Contract 和 budget-class digests 全部 exact
equality；不支持
implicit wildcard、range 或层级继承。跨任务泛化必须通过显式、版本化的 v2 scope
algebra 和独立 acceptance corpus，不能在 ranker 中临时放宽。

这里的“跨任务”指跨 `task_scope_id`；同一 scope 内未见的
`evaluation_task_id` 是 v1 明确支持的 held-out instance transfer。source evidence
保留 evaluation-task IDs 用于 contamination；transferable record 的 scope 不含这些
instance IDs。若 policy 明确生成 instance-specific record，则把
`evaluation_task_id` 放入 MemoryScope，该 record 只能支持 same-task/new-seed claim。
taxonomy registry、public projection 和每个 evaluation task 的映射都必须在 corpus/
Run manifest 中预注册并内容寻址，不能从 private evaluator 字段推断。

`latest-development` 只允许作为 CLI 解析 convenience：在 Research Run acceptance
前解析为 exact Knowledge/Recall Input Snapshot ID，把 exact ID 写入 Run spec；任何
Runtime Activity 和 acceptance manifest 中不得持久化 `latest` alias。

## 7. SQLite schema revision 3

### 7.1 Additive tables

schema revision 3 保留所有 v2 表和 payload，新增：

表名尾缀表示该 logical payload family 的版本，不等同于 SQLite `user_version`；
`*_v2` memory/recall tables 与 `*_v1` 新 sidecars 都在 schema revision 3 一次创建。

| 表 | 关键列/约束 |
| --- | --- |
| `ledger_commits_v1` | `position INTEGER PRIMARY KEY AUTOINCREMENT`, `namespace/record_kind/record_id/payload_digest TEXT NOT NULL`, `payload_digest CHECK(lowercase 64-hex)`, `UNIQUE(record_kind,record_id)`；snapshots record the relevant namespace frontier |
| `experience_distillation_receipts_v1` | `record_id TEXT PK`, `experience_id TEXT UNIQUE NOT NULL FK`, nullable `work_item_id TEXT FK -> distillation_work_items_v1(record_id)`, nullable non-FK `abandoned_work_item_id/abandoned_work_item_payload_digest/abandonment_proof_ref/abandonment_proof_digest TEXT`, `disposition TEXT CHECK(queued_for_comparison/deferred_ineligible/not_required/abandoned_before_enqueue)`, `distillation_policy_id/distillation_policy_digest TEXT NOT NULL`, `created_at TEXT NOT NULL`, `payload_json TEXT NOT NULL`; queued iff committed Work Item is non-null and abandonment fields null；abandoned iff Work Item null and all abandonment fields non-null；deferred/not-required forbid both groups；abandoned validator recomputes the frozen non-inserted Work Item ID/digest and exact Experience/policy/profile lineage；source receipt never claims a later Activity |
| `distillation_work_items_v1` | `record_id TEXT PK`, `experience_id TEXT UNIQUE NOT NULL FK`, `namespace/distillation_policy_id/distillation_policy_digest/lifecycle_policy_id/lifecycle_policy_digest/campaign_admission_profile_ref/campaign_admission_profile_digest/created_at/payload_json TEXT NOT NULL`, immutable append metadata `campaign_profile_artifact_ref_id TEXT UNIQUE NOT NULL`；profile 覆盖 workflow/continuation/model/tool/Adapter/Budget/retention/cardinality；artifact ref ID 从 Work Item ID/profile digest 确定性派生并排除在 `record_id` canonical projection 外；`record_id` 本身是唯一 campaign-admission/idempotency key；enqueue transaction 验证 Runtime proof 后先写此 row，再写引用它的 queued receipt，最后写 enqueue sidecar |
| `distillation_enqueue_transactions_v1` | `record_id TEXT PK`, `experience_id/work_item_id/handoff_id/artifact_ref_id/enqueue_attempt_id TEXT UNIQUE NOT NULL`, `attempt_generation/attempt_fence INTEGER NOT NULL CHECK(>=0)`, `profile_proof_digest/work_item_payload_digest/ingestion_receipt_id/ingestion_receipt_digest/transaction_digest/created_at/payload_json TEXT NOT NULL`; `work_item_id FK`, `ingestion_receipt_id FK`；row 与 Work Item、queued ingestion receipt、三者 journal rows 原子提交；payload/transaction digest 绑定原 proof 与 ordered receipts，exact retry/read-back 不依赖 current Runtime handoff state |
| `distillation_work_assignments_v1` | `record_id TEXT PK`, `work_item_id TEXT UNIQUE NOT NULL FK`, `campaign_manifest_ref/campaign_manifest_digest/campaign_run_id/activity_id/created_at/payload_json TEXT NOT NULL`, `UNIQUE(campaign_run_id,activity_id)`；`record_id=distillation_work_assignment_id`；Runtime proof must show `run_kind=MEMORY_DISTILLATION`, non-terminal Run and owned Activity |
| `distillation_batches_v1` | `record_id TEXT PK`, `evidence_snapshot_id TEXT NOT NULL FK`, `commit_authorization_id/commit_effect_id/campaign_run_id/activity_id TEXT NOT NULL`, `activity_generation/fence INTEGER NOT NULL CHECK(>=0)`, `namespace/distillation_policy_id/distillation_policy_digest/lifecycle_policy_id/lifecycle_policy_digest/created_at/payload_json TEXT NOT NULL`; payload pins exact v1 singleton campaign Work Item plus Evidence Snapshot/Experience/candidate coverage and canonical request |
| `distillation_reports_v1` | `record_id TEXT PK`, `batch_id TEXT UNIQUE NOT NULL FK`, `commit_authorization_id/commit_effect_id/affected_active_view_digest/created_at/payload_json TEXT NOT NULL`; payload pins exact Work Item/Experience/Disposition coverage and all committed candidate/decision/memory/event/relation IDs; the digest covers only sorted affected scope final heads/dispositions, all protected by expected-head CAS; canonical payload excludes invocation telemetry, and its journal payload digest is the report digest used by Completion |
| `distillation_commit_conflicts_v1` | `record_id TEXT PK`, `commit_authorization_id/commit_authorization_digest/proposal_id/proposed_batch_id/conflict_kind/created_at/payload_json TEXT NOT NULL`, `commit_authorization_id UNIQUE`; `conflict_kind CHECK(LIFECYCLE_HEAD_STALE/RETENTION_REVOKED)`；payload 按 kind 保存 sorted expected/observed scope heads，或 current retention frontier/set + reachable blocked targets；`proposed_batch_id` is an expected identity, not an FK because no Batch exists on this branch; this no-commit receipt is mutually exclusive with any Batch using that authorization |
| `distillation_work_dispositions_v1` | `record_id TEXT PK`, `batch_id TEXT NOT NULL FK`, `work_item_id TEXT UNIQUE NOT NULL FK`, `experience_id TEXT NOT NULL FK`, `disposition TEXT CHECK(covered_by_decision/deferred_no_comparator/rejected_not_comparable/rejected_no_candidate)`, nullable `decision_id TEXT FK`, `created_at/payload_json TEXT NOT NULL`, `UNIQUE(batch_id,work_item_id)`; `covered_by_decision` iff decision non-null, all non-candidate dispositions forbid it |
| `distillation_work_completions_v1` | `record_id TEXT PK`, `work_item_id TEXT UNIQUE NOT NULL FK`, `assignment_id TEXT UNIQUE NOT NULL FK`, `campaign_run_id/activity_id/terminal_authorization_id/terminal_authorization_digest TEXT NOT NULL`, `activity_generation/fence INTEGER NOT NULL CHECK(>=0)`, nullable `commit_effect_id TEXT`, nullable `batch_id TEXT FK`, nullable `report_id TEXT FK`, nullable `report_digest/terminal_receipt_ref/terminal_receipt_digest TEXT`, `terminal_status TEXT CHECK(completed/dead_letter/cancelled)`, `created_at/payload_json TEXT NOT NULL`; assignment/Run/Activity/generation/fence must match exactly; completed requires commit authorization/effect and all three Batch/Report fields, forbids terminal receipt；dead-letter/cancelled require closure authorization plus a Runtime-resolvable typed terminal receipt ref/digest and forbid commit/Batch/Report fields |
| `evidence_snapshots_v1` | `record_id TEXT PK`, `ledger_position INTEGER NOT NULL`, `namespace TEXT NOT NULL`, nullable `run_id/arm_id/pair_id TEXT`, `eligibility_policy_digest TEXT NOT NULL`, `created_at TEXT NOT NULL`, `payload_json TEXT NOT NULL`；null Run/arm/pair 表示 namespace-wide base snapshot |
| `evidence_snapshot_members_v1` | `snapshot_id TEXT FK`, `ordinal INTEGER CHECK(ordinal>=0)`, `experience_id/observation_id/verification_id/intervention_id/provenance_id TEXT NOT NULL FK`, `bundle_digest TEXT NOT NULL`, `PRIMARY KEY(snapshot_id,experience_id)`, `UNIQUE(snapshot_id,ordinal)` |
| `evidence_snapshot_capture_operations_v1` | `record_id TEXT PK`, `request_digest/snapshot_id/snapshot_payload_digest TEXT NOT NULL`, `snapshot_id FK`, `snapshot_journal_position INTEGER NOT NULL`, `created_at/payload_json TEXT NOT NULL`; its own journal position is resolved by `(record_kind,record_id)`, not embedded in the payload; same operation ID/same request returns this original mapping before reading current Evidence frontier, while different request conflicts; operation ID is excluded from Snapshot ID |
| `knowledge_candidates_v2` | `record_id TEXT PK`, `source_snapshot_id TEXT NOT NULL FK`, `proposed_family_key TEXT NOT NULL`, `record_kind TEXT CHECK(semantic/procedure)`, `decision_point TEXT CHECK(ideation/experiment_design/intervention/diagnosis/writing)`, `created_at TEXT NOT NULL`, `payload_json TEXT NOT NULL` |
| `memory_records_v2` | `record_id TEXT PK`, `family_id/scope_variant_id TEXT NOT NULL`, nullable `prior_memory_id TEXT FK`, `record_kind TEXT CHECK(semantic/procedure)`, `decision_point TEXT CHECK(ideation/experiment_design/intervention/diagnosis/writing)`, `domain TEXT NOT NULL`, `created_at TEXT NOT NULL`, `payload_json TEXT NOT NULL` |
| `memory_evidence_links_v2` | `memory_id/experience_id/observation_id/verification_id/intervention_id/provenance_id TEXT NOT NULL FK`, `relation TEXT CHECK(supports/contradicts)`, `support_unit_id TEXT NOT NULL`, `PRIMARY KEY(memory_id,experience_id,support_unit_id,relation)` |
| `knowledge_lifecycle_events_v2` | `record_id TEXT PK`, `memory_id TEXT NOT NULL FK`, `family_id/scope_variant_id TEXT NOT NULL`, nullable `prior_event_id TEXT FK`, `expected_head_key TEXT NOT NULL`, `resulting_disposition TEXT CHECK(provisional/active/contested/superseded/retracted)`, `created_at/payload_json TEXT NOT NULL`, `CHECK(expected_head_key=coalesce(prior_event_id,'GENESIS'))`, `UNIQUE(scope_variant_id,expected_head_key)` |
| `memory_scope_variant_heads_v1` | `scope_variant_id TEXT PK`, `family_id/memory_id/lifecycle_event_id TEXT NOT NULL` with memory/event FKs, `cas_version INTEGER NOT NULL CHECK(cas_version>=1)`；derived projection updated only by expected-head CAS |
| `memory_relations_v2` | `source_memory_id/target_memory_id TEXT NOT NULL FK`, `relation TEXT CHECK(supersedes/scope_refines/procedure_implements/contests)`, `caused_by_event_id TEXT NOT NULL FK`, `PRIMARY KEY(source_memory_id,target_memory_id,relation)`, `CHECK(source_memory_id<>target_memory_id)` |
| `distillation_decisions_v2` | `record_id TEXT PK`, `candidate_id TEXT UNIQUE NOT NULL FK`, `disposition TEXT CHECK(rejected/deferred/promoted_provisional/promoted_active/promoted_contested)`, nullable `memory_id TEXT FK`, `distillation_policy_id/distillation_policy_digest/lifecycle_policy_id/lifecycle_policy_digest/created_at/payload_json TEXT NOT NULL`; promoted iff memory non-null |
| `retention_erasure_intents_v1` | `record_id TEXT PK`, `incident_id TEXT UNIQUE NOT NULL`, `namespace/target_kind/target_id/target_digest/reason_code/retraction_requirement/external_target_ref/external_target_digest/retention_policy_digest/created_at/payload_json TEXT NOT NULL`, nullable `external_object_generation/retraction_event_id/retraction_event_digest`, `UNIQUE(target_kind,target_id)`；payload 含 sorted expected affected index build/artifact IDs；append before any external erasure and immediately enters deny set |
| `memory_retention_tombstones_v1` | `record_id TEXT PK`, `intent_id TEXT UNIQUE NOT NULL FK`, `target_kind/target_id/target_digest/incident_id/reason_code/retraction_requirement/external_erasure_receipt_ref/external_erasure_receipt_digest/created_at/payload_json TEXT NOT NULL`, nullable `retraction_event_id/retraction_event_digest TEXT`, `UNIQUE(target_kind,target_id)`；payload 含 sorted index-invalidation receipt refs/digests并须与 Intent expected set exact equality；polymorphic target 由 transaction validator 验证仍有 canonical audit envelope/journal，schema v3 不删除该 row |
| `knowledge_snapshots_v1` | `record_id TEXT PK`, `lifecycle_position INTEGER NOT NULL`, `selection_policy_digest/namespace/created_at/payload_json TEXT NOT NULL`; no retrieval/index columns |
| `knowledge_snapshot_members_v1` | `snapshot_id/memory_id/lifecycle_event_id/family_id/scope_variant_id TEXT NOT NULL`, FKs to snapshot/memory/event, `ordinal INTEGER NOT NULL`, `PRIMARY KEY(snapshot_id,scope_variant_id)`, `UNIQUE(snapshot_id,ordinal)` |
| `derived_memory_indexes_v1` | ready receipt only：`record_id TEXT PK`, `knowledge_snapshot_id TEXT NOT NULL FK`, nullable `evidence_snapshot_id TEXT FK`, `adapter_kind/adapter_digest/vector_digest/artifact_digest/created_at/payload_json TEXT NOT NULL`；可进入 Recall Input 的行必有完整 artifact/vector digest |
| `derived_memory_index_failures_v1` | `record_id TEXT PK`, `knowledge_snapshot_id TEXT NOT NULL FK`, nullable `evidence_snapshot_id TEXT FK`, `adapter_kind/adapter_digest/attempt_key/error_code/failure_receipt_digest/created_at/payload_json TEXT NOT NULL`, `retry_ordinal INTEGER NOT NULL CHECK(retry_ordinal>=0)`, `UNIQUE(attempt_key,retry_ordinal)`；attempt key 是包含 source/Adapter/policy identity 的全局 content ID，failure 不能被 Recall Input 引用 |
| `recall_input_snapshots_v1` | `record_id TEXT PK`, `knowledge_snapshot_id TEXT NOT NULL FK`, nullable `evidence_snapshot_id TEXT FK`, `retrieval_policy_digest/renderer_digest/tokenizer_digest/created_at/payload_json TEXT NOT NULL` |
| `recall_input_index_builds_v1` | `recall_input_id/index_build_id TEXT NOT NULL FK`, `ordinal INTEGER NOT NULL`, `PRIMARY KEY(recall_input_id,index_build_id)`, `UNIQUE(recall_input_id,ordinal)` |
| `decision_contract_views_v1` | `record_id TEXT PK`, `source_contract_digest/actor_view_digest/created_at/payload_json TEXT NOT NULL`; payload validator forbids private/evaluator fields |
| `decision_intents_v1` | `record_id TEXT PK`, `run_id/activity_id/iteration_id/evaluation_task_id/task_scope_id/research_context_snapshot_id/decision_point/contract_view_id/decision_slot_id/artifact_kind/allowed_action_digest/planned_actor_model_ref/planned_actor_model_digest/planned_actor_config_digest/planned_prompt_template_ref/planned_prompt_template_digest/planned_actor_policy_digest/memory_profile_ref/memory_profile_digest/memory_assignment_manifest_ref/memory_assignment_manifest_digest/recall_requirement/created_at/payload_json TEXT NOT NULL`, immutable append-metadata `admission_authorization_id/admission_authorization_digest TEXT UNIQUE NOT NULL` excluded from canonical payload/record ID, `recall_requirement CHECK(REQUIRED/REGISTERED_NOT_REQUESTED)`, `decision_point CHECK(ideation/experiment_design/intervention/diagnosis/writing)`, `generation INTEGER NOT NULL CHECK(generation>=0)`, nullable `arm_id/pair_id TEXT`, `contract_view_id FK`, `task_scope_id` content-ID CHECK, `UNIQUE(run_id,activity_id,generation,decision_slot_id)`；append requires matching Runtime admission proof；planned actor fields name pinned plan/template identities rather than an executed prompt；`artifact_kind` 是 pinned workflow registry ID，不是开放 enum |
| `decision_recall_contexts_v2` | `record_id TEXT PK`, `intent_id TEXT UNIQUE NOT NULL FK`, `recall_input_id TEXT NOT NULL FK`, immutable append-metadata `commit_authorization_id/commit_authorization_digest TEXT UNIQUE NOT NULL` excluded from canonical payload/record ID, `status TEXT CHECK(ok/empty/degraded)`, nullable `degradation_reason/fallback_policy_digest TEXT`, `retention_check_digest/tombstone_set_digest/rendered_context_digest/tokenizer_digest TEXT NOT NULL`, `retention_frontier/rendered_token_count INTEGER NOT NULL CHECK(>=0)`, `created_at/payload_json TEXT NOT NULL`, `UNIQUE(record_id,intent_id)` for Outcome composite FK; degraded iff reason+fallback non-null, ok/empty require both null |
| `decision_recall_no_commit_receipts_v1` | `record_id TEXT PK`, generic `authorization_id/authorization_digest TEXT UNIQUE NOT NULL`, `authorization_kind TEXT CHECK(ADMISSION/COMMIT)`, `intent_id/transition_kind/expected_record_id/expected_payload_digest/reason_code/observed_phase_digest/created_at/payload_json TEXT NOT NULL`, `transition_kind CHECK(APPEND_INTENT/APPEND_CONTEXT/APPEND_OUTCOME)`, exact kind matrix `APPEND_INTENT->ADMISSION`, `APPEND_CONTEXT|APPEND_OUTCOME->COMMIT`, `reason_code CHECK(PRECONDITION_CONFLICT/CANONICAL_RECORD_CONFLICT/AUTHORIZED_PAYLOAD_REJECTED/RETENTION_FRONTIER_STALE)` with retention reason legal only for Context, mutually exclusive with any Intent/Context/Outcome using the same authorization；the transaction writes no Intent, Context, `decision_recall_items_v2`, Outcome, or disposition row and journals this receipt atomically |
| `decision_recall_items_v2` | `context_id TEXT FK`, `citation_id TEXT`, `ordinal INTEGER CHECK(ordinal>=0)`, `card_id/source_record_id/payload_json TEXT NOT NULL`, `source_kind TEXT CHECK(semantic/procedure/episodic)`, nullable `memory_id TEXT FK`, `PRIMARY KEY(context_id,citation_id)`, `UNIQUE(context_id,ordinal)` |
| `recall_decision_outcomes_v1` | `record_id TEXT PK`, `intent_id TEXT UNIQUE NOT NULL FK`, nullable `context_id TEXT UNIQUE`, composite `FK(context_id,intent_id) -> decision_recall_contexts_v2(record_id,intent_id)`, immutable append-metadata `commit_authorization_id/commit_authorization_digest TEXT UNIQUE NOT NULL` excluded from canonical payload/record ID, semantic `commit_authority TEXT CHECK(NORMAL/RUNTIME_CLOSURE)`, nullable `blocked_source_proof_ref/blocked_source_proof_digest/decision_memory_binding_ref/decision_memory_binding_digest TEXT`, `source_status TEXT CHECK(blocked/not_requested/cancelled_before_recall/failed_before_recall/empty/degraded/ok)`, `outcome_reason_code TEXT NOT NULL` validated by the closed source-status matrix, `decision_status TEXT CHECK(blocked/actor_failed/rejected/no_op/completed/cancelled)`, `artifact_status TEXT CHECK(committed/not_produced)`, planned actor identities read from Intent, nullable executed `actor_model_digest/actor_response_digest/rendered_prompt_digest TEXT`, nullable `terminal_reason_code TEXT CHECK(BLOCKED_RECALL_SOURCE/ACTOR_INVOCATION_FAILED/ACTOR_OUTPUT_MALFORMED/RUNTIME_FAILURE_CLOSURE/PROPOSAL_POLICY_REJECTED/PREFLIGHT_REJECTED/NO_APPLICABLE_ACTION/ALREADY_SATISFIED/CANCELLED_BY_COMMAND/CANCELLED_BY_INCIDENT)`, nullable `terminal_receipt_ref/terminal_receipt_digest/artifact_id/artifact_digest/intervention_id/pre_recall_closure_event_id/pre_recall_closure_event_digest TEXT`, `intervention_id FK -> intervention_records(record_id)`, `created_at/payload_json TEXT NOT NULL`; blocked-source-proof pair is non-null iff `source_status=blocked`, otherwise both fields are null |
| `recall_decision_dispositions_v1` | `outcome_id/context_id/citation_id TEXT NOT NULL`, `disposition TEXT CHECK(adopted/rejected/not_considered)`, nullable `mapped_target TEXT`, `reason_code TEXT CHECK(adopted_applicable/rejected_scope_mismatch/rejected_counterevidence/rejected_protected_action/rejected_stale_dependency/rejected_low_expected_utility/not_considered_budget/not_considered_cancelled/not_considered_actor_failed)`, `PRIMARY KEY(outcome_id,citation_id)`, composite FK `(context_id,citation_id)` to recall items；后两个 reason 仅允许 `RUNTIME_CLOSURE` |
| `recall_outcome_attempt_links_v1` | `record_id TEXT PK`, `outcome_id TEXT UNIQUE NOT NULL FK`, `attempt_id TEXT NOT NULL FK`, `created_at/payload_json TEXT NOT NULL`; `record_id=outcome_attempt_link_id`，append-only optional lineage when an Attempt is opened after the Outcome |

`memory_records_v2` 只统一存储物理表；`record_kind` 必须选择对应 Pydantic
model 验证。Domain Interface 仍区分 SemanticKnowledgeRecord 和 ProcedureRecord。

只有本设计新增的 content-derived logical-ID 列和 raw digest 列加 lowercase 64-hex
CHECK。既有/外部 operational identifiers（包括 `run_id`、`activity_id`、
`iteration_id`、`arm_id`、`pair_id`、legacy Experience/Intervention IDs）保持其原
schema contract，不得套用 64-hex 约束。所有 closed enum 采用明确 CHECK；
`artifact_kind`、retention `target_kind/reason_code`、index `adapter_kind/error_code`
是由 payload 中 pinned content-addressed workflow/policy/registry 校验的 versioned
code，不是开放 SQL enum，transaction validator 必须证明 code 在所引用 registry 中；所有
`payload_json` read-back 后必须 Pydantic parse 且 indexed columns 与 payload 一致。
唯一例外是上述 immutable `admission_authorization_id/digest`、
`commit_authorization_id/digest`、`campaign_profile_artifact_ref_id` 与 enqueue sidecar
handoff/attempt/proof append metadata：
它们由 Store transaction 从 proof 写入并与 Runtime record equality-validated，但明确
不进入对应 canonical payload/record ID；任何其他 indexed-column exception 禁止。
表中用 `/` 连写的列名表示每个名称都是独立列，所标类型与 NULL 约束分别适用于
每列，DDL 中不得创建带 `/` 的真实列。除显式写 `nullable` 外均为 `NOT NULL`。
DDL 还必须包含以下不可省略的 CHECK/UNIQUE：

- `distillation_decisions_v2` 仅 `promoted_*` 可且必须有 `memory_id`；
- queued Experience Distillation Receipt 以 immediate FK 引用唯一 Work Item，先写
  Work Item、后写 queued ingestion receipt、最后写以该 receipt 为 immediate FK 的
  `DistillationEnqueueTransaction` sidecar，并按相同顺序追加三条 journal rows 后在同一
  transaction commit；非 queued receipt 的
  `work_item_id IS NULL`；queued transaction 必须验证 strict
  `WorkItemProfileArtifactProof` 的 Work Item/owner/profile/object generation、
  deterministic handoff/ref IDs、attempt ID/generation/fence、`ACTIVE` ref 和
  `PENDING|BOUND` state，并把 exact ref ID 写入 Work Item append metadata，把原 proof/
  attempt/transaction digest 写入 frozen `DistillationEnqueueTransaction` payload/enqueue
  receipt；deferred/not-required 禁止 proof/
  ref。same Work Item/ref exact retry 返回原 transaction，foreign/inactive/released/
  mismatched proof 零 Ledger write；Work Completion 的
  terminal payload 条件由 CHECK 加 read-back validator 同时强制；
- `abandoned_before_enqueue` append 必须先通过 Runtime public getter read-back exact
  `DistillationEnqueueObligationAbandonedProof`，并在同一 Ledger transaction 证明 Work
  Item/enqueue sidecar 不存在；调用必须携带 frozen `abandoned_work_item`，Store 重算其
  ID/payload digest 并逐字段匹配 receipt Experience、policy/profile lineage 与 proof。
  receipt 绑定 non-FK abandoned Work Item ID/payload digest/proof pair，但不插 Work Item。
  A-Experience proof/payload 与 B-Experience receipt 的交换必须零写入。
  Runtime 只有 read-back 该 receipt 后才可 release handoff/ref；queued/deferred/not-required
  与 abandoned field matrix 任一混用都 rollback；
- Assignment append 验证 exact campaign manifest membership/ordinal/digest 与
  `AWAITING_ASSIGNMENT` Runtime proof；Runtime 重新 read-back Assignment proof 后才可
  CAS 到 READY。`completed` 必须绑定 Runtime commit authorization ID/digest、logical
  Effect、generation/fence 并 forbids terminal receipt；`dead_letter/cancelled` 必须绑定
  mutually-exclusive closure authorization 和可由 Runtime public getter read-back 的
  typed terminal receipt ref/digest，并 forbid commit Effect/Batch/Report；
- `completed` Work Completion 的 `batch_id` 必须 FK 到 canonical Batch，`report_id`
  必须 FK 到该 Batch 唯一 canonical Report，`report_digest` 必须等于 Report journal
  payload digest；transaction validator 通过 `KnowledgeStore` getter read-back 二者，
  并验证其 exact Work Item/Experience ID、namespace/scope、Distillation + Lifecycle
  policy identities 与 Work Item 相同，且 Report 含该 Work Item 唯一 committed
  `DistillationWorkDisposition`：`covered_by_decision` 必须解析到 reject/defer/promote
  Decision，三个 no-candidate dispositions 必须无 Candidate/Decision；任意裸 digest、
  unrelated Batch/Report 或缺失 disposition 都不能关闭 item；
- successful Completion 只能在 `commit_distillation()` 内与 Batch、Report、Knowledge/
  lifecycle writes 原子提交；独立 closure helper 禁止 `completed`。Store 必须 read-back
  Runtime authorization，验证 exact Assignment/Run/Activity/generation/fence/Effect 与
  proposal/final IDs/digests；same authorization/different payload 或 stale/foreign proof
  fail closed；
- 每个 commit authorization attempt 至多对应一个 successful Batch 或一个
  `DistillationCommitConflict`，两者互斥；Conflict 的 expected/observed head projection
  或 retention frontier/blocked-target projection 必须从当前 transaction read-back，
  exact retry 返回原 position。Runtime 只有在
  conflict getter 与 digest 验证成功后才可 CAS authorization 为
  `RETIRED_NO_COMMIT`；retired authorization 禁止后来写 Batch；
- successful v1 Batch 对 singleton Work Item 恰有一个 Work Disposition；Report 和
  Completion read-back 必须指向同一 disposition。`covered_by_decision` iff nullable
  Decision FK 非空；no-candidate 状态不能伪造 Candidate/Decision；
- Recall append 不依赖 `UNIQUE(intent_id)` 猜竞态顺序。完整 `DecisionIntentProposal`
  先发布/read-back；Runtime 以 CAS 创建 `REGISTERING` 和 admission authorization，Ledger
  success 才推进 `OPEN`，typed no-commit 则 retire ghost registration。此后每个 Intent 的
  closed phase 是 `OPEN/CONTEXT_COMMITTING/CONTEXT_COMMITTED/OUTCOME_COMMITTING/
  OUTCOME_COMMITTED`，并由 Run-version/control-event/Activity-generation/fence CAS
  发唯一 single-use authorization。closed tagged union 为
  `DecisionRecallAppendAuthorization = DecisionIntentAdmissionAuthorization |
  DecisionRecallCommitAuthorization`：admission subtype 只给 Intent，commit subtype 只给
  Context/Outcome。union 绑定 transition kind `APPEND_INTENT|APPEND_CONTEXT|
  APPEND_OUTCOME`、authority `ADMISSION|NORMAL|RUNTIME_CLOSURE`、Intent/Run/
  Activity/generation/fence、expected record ID/payload digest 和 optional preceding Context；
- `DecisionRecallCommitAuthorizationProof` 另含 nullable
  `blocked_source_proof_ref/blocked_source_proof_digest`；两者必须同时非 null 当且仅当
  `APPEND_OUTCOME + NORMAL` 的 expected Outcome 为 `source_status=blocked`，其他 transition、
  authority 或 source status 必须同时为 null。Blocked Outcome proposal、authorization 与
  canonical Outcome 的这两个字段必须 byte-equal；
- legal cross-product 是 exact closed matrix：`APPEND_INTENT <-> ADMISSION`、
  `APPEND_CONTEXT <-> NORMAL`、`APPEND_OUTCOME <-> NORMAL|RUNTIME_CLOSURE`。Runtime
  issuer 与 Store transaction 都验证；Runtime admission getter 只返回 admission subtype，
  commit getter 只返回 commit subtype，另一 subtype 必须拒绝；closure Context、
  normal/admission Intent mix、
  admission Outcome 等非法 pair 必须在零 Ledger write 下拒绝；
- normal/closure builder 都必须先把 complete Context/Outcome proposal 发布为 scoped
  Runtime artifact；authorization 另绑定其 ref/digest。Runtime read-back proposal 后才可
  grant，Ledger canonical payload bytes 必须与 proposal 内 record byte-equivalent；Store
  仅在 transaction 内另加 excluded-from-ID 的 immutable authorization metadata。Blocked
  builder 还必须先从 Runtime Artifact Store read-back `DecisionRecallBlockedProposal`，并把
  getter 返回的 exact blocked-source proof pair 同时写入 Outcome proposal 与 authorization；
- `append_decision_recall()` 与 `append_recall_outcome()` 必须 read-back authorization
  canonical record/digest 和当前 unresolved attempt，再在一个 Ledger transaction 验证
  exact payload。Context 只可从 `OPEN` authorization 写且 Outcome 必须 absent；normal
  Outcome 只可从 `CONTEXT_COMMITTED` 写，或对 registered-not-requested/typed blocked 从
  `OPEN` 写。成功 receipt 由 Runtime read-back 后推进 committed phase；typed no-commit
  才能 retire authorization；reply loss 以 same ID/digest reconcile；
- blocked Outcome append 时，Store 必须通过注入的
  `DecisionRecallArtifactRead.get_decision_recall_blocked_proof()` 独立解析
  `blocked_source_proof_ref`，重算 artifact/proposal digest，并逐字段核对 producer/object、
  proposal ID/digest、Intent ID/digest、nullable Recall Input ID/digest、request/policy digest、
  blocked reason 和 reason-specific evidence；retention evidence 还须逐字段等于 exact
  `RetentionCheck` 的 Recall Input、frontier、tombstone set 与 sorted blocked targets。
  getter proof、Outcome、Outcome proposal 或 authorization 任一 foreign/swap/forged/mismatch
  均须在零 Ledger write 下拒绝；
- Context transaction 在写任何 Context/item 前按 namespace 重算 current
  `RETENTION_KINDS` frontier/open-intent+tombstone set，要求与 proposal/authorization 的
  `RetentionCheck` exact equality，并 anti-join every selected source/index。retention-first
  返回 `RETENTION_FRONTIER_STALE` no-commit 且零 Context/item；Context-first 是该一次 actor
  exposure 的 Ledger linearization point，后续 Intent/Tombstone 阻塞所有 future Context；
- success append/read-back 必须包含 exact authorization ID/digest metadata；same
  record/same authorization 才是 replay，same record/different authorization 或相反组合
  是 identity conflict，Runtime 不得据 canonical record 单独存在推进 phase；
- typed no-commit 不是异常或“查不到 row”：Store 在验证 authorization 后以同一
  transaction 证明零 Intent、Context、Context-item、Outcome、disposition write，并 append 唯一
  `DecisionRecallNoCommitReceipt`。authorization ID 下 success/no-commit 互斥；exact retry
  返回原 journal position，same authorization/different expected payload fail closed。
  Receipt 使用 generic `authorization_kind/id/digest`；`APPEND_INTENT` 必须是
  `ADMISSION` proof，`APPEND_CONTEXT|APPEND_OUTCOME` 必须是 `COMMIT` proof，Store getter
  以同一 generic authorization ID read-back，不能把 admission 塞进 commit-only 列；
  Runtime 必须从 Store getter read-back receipt ID/digest/reason/observed phase 后才可 retire；
- cancel/fail-first 的 Runtime CAS 禁止 normal authorization，并授予 mutually-exclusive
  `RUNTIME_CLOSURE` Outcome authorization。若 normal append authorization 已 unresolved，
  cancel/failure 只登记一个由同一 control-event CAS 仲裁的 pending closure kind，不早撤
  fence；Ledger success 后 Context attempt 转为 closure Outcome，Outcome attempt 则 immutable
  Outcome 胜出；no-commit 后 retire attempt 并在任何 normal retry 前应用 pending closure。
  cancel-first 只抑制 duplicate/cancellation-induced failure；failure-first 对随后 cancel
  为 closure-help/no-op。独立 integrity/contract/infrastructure failure 另存 secondary
  evidence，arbitration 后按 success/no-commit 重新判定 failure path。未解决 attempt 保持
  COMMITTING/必要时 WAITING_INPUT，不能并发发第二授权；
- Recall Context 的 `degraded` iff typed degradation reason 与 fallback policy digest
  都非空；`ok/empty` 必须两者皆空。Retention Check/frontier/tombstone-set 与完整
  rendered-context identity 必须参与 Context ID/read-back；golden vectors 必须区分
  healthy empty、degraded zero-card 与 retention-frontier change；
- `recall_decision_outcomes_v1` 加 `UNIQUE(record_id,context_id)`；`blocked`、
  `not_requested`、`cancelled_before_recall`、`failed_before_recall` 必须
  `context_id IS NULL`，其他 source status 必须有 context；Intent/Outcome requirement
  是双向封闭映射：read-back Intent 的
  `recall_requirement=REGISTERED_NOT_REQUESTED` iff Outcome
  `source_status=not_requested`、Context null、disposition 行数为 0；`REQUIRED` Intent
  使用 `not_requested` 或 registered Intent 使用 blocked/pre-recall/context status 都必须
  失败，caller 不能传 profile bool 覆盖；
- 两个 pre-recall closure status 只允许 `REQUIRED` Intent 且 Context 尚不存在；
  `cancelled_before_recall -> decision_status=cancelled`，
  `failed_before_recall -> actor_failed`，均 zero dispositions/not_produced，并必须传
  `RUNTIME_CLOSURE` authorization，其中包含 `DecisionIntentClosureProof`。Store 经
  Runtime getter read-back closure event，验证
  exact Run/Activity/Intent/generation、cause 和 Context-absent frontier。只有这两个
  source status 可令 `pre_recall_closure_event_id/digest` 非 null：cancelled 分支必须与
  authorization 的 `terminal_evidence_ref/digest` byte-equal 且 evidence kind 为
  `CANCEL_EVENT`；failed 分支同样 byte-equal 且 kind 为 `RUNTIME_FAILURE`。两分支的
  `terminal_receipt_ref/digest` 也必须引用同一 evidence。所有其他 source status 的
  `pre_recall_closure_event_id/digest` 必须同时为 null，即使提供的是另一条自身有效的
  closure event 也拒绝；
- outcome 的 `artifact_status=committed` iff `artifact_id` 和 `artifact_digest` 都非
  null；`not_produced` iff 两者都 null。`completed` 必须 committed，
  `blocked/actor_failed/no_op/cancelled` 必须 not_produced；`rejected` 仅当有持久化的
  typed rejection artifact 时可 committed。`artifact_kind=intervention` 且 committed
  时 `intervention_id` 必须非 null、FK 可解析并与 artifact ID/digest 一致；其他 kind
  禁止伪造 intervention lineage；
- Outcome 的 planned actor model/config/template/policy identities 必须从 Intent read-back；
  executed actor model/response/rendered-prompt identities 只有真实 actor invocation 才能
  非 null；blocked、两个 pre-recall closure 和任何 actor-before-invocation closure 必须
  全 null，禁止用 planned template digest 伪造 executed prompt；
- actor invocation 发生时 `decision_memory_binding_ref/digest` 必须同时非 null，等于
  actor Effect 前已发布/read-back 且由该 Effect request exact binding 的 planner-input
  memory-binding artifact ref/canonical digest，并按
  discriminant 与 Intent/Recall Input/Context/counts 或 Intent governance/no-memory zero
  fields 完全一致。成功的 `RecalledInterventionDecision.decision_memory` 还必须与该输入
  artifact byte-equivalent；actor timeout/crash/unparseable output 不要求伪造 response
  envelope。未调用 actor 的路径该字段必须 null。Outcome ID 包含此字段；foreign
  envelope、input/response binding/Effect swap 或 governance digest tamper 必须 rollback；
  terminal matrix 是 closed：`completed` 仅允许 `NORMAL`、null reason/receipt 且无
  closure event/Runtime-only disposition；`blocked` 只允许 `BLOCKED_RECALL_SOURCE`、
  `NORMAL`、null terminal receipt，并要求 Outcome/authorization 的
  `blocked_source_proof_ref/digest` 指向同一个 strict read-back
  `DecisionRecallBlockedProof`；retention block 的 proof evidence 必须包含 exact
  `RetentionCheck`，不得另附一个 caller-supplied check；
  `actor_failed` 一律由 Runtime closure builder 写：model invocation failure/malformed
  output 分别使用 `ACTOR_INVOCATION_FAILED|ACTOR_OUTPUT_MALFORMED`，绑定同 Intent/model
  Effect failure receipt；其他 Runtime failure 使用 `RUNTIME_FAILURE_CLOSURE` 和 closure
  event receipt。三者均要求 `RUNTIME_CLOSURE` authorization；非空 Context 的 card 由
  Runtime 写 `not_considered_actor_failed`；`rejected` 只允许
  `PROPOSAL_POLICY_REJECTED|PREFLIGHT_REJECTED`、`NORMAL` 和 exact policy/preflight
  rejection receipt；`no_op` 只允许 `NO_APPLICABLE_ACTION|ALREADY_SATISFIED`、`NORMAL`、
  null receipt；`cancelled` 只允许 `CANCELLED_BY_COMMAND|CANCELLED_BY_INCIDENT`、
  `RUNTIME_CLOSURE` 和 exact closure receipt。两个 pre-recall statuses 及 post-Context
  Runtime-only dispositions 必须走 closure branch；receipt ref/digest 必须同 null/非 null，
  Store read-back 后与 authorization 所绑 closure/model-Effect/rejection receipt exact
  equality。foreign/forged receipt、closure-auth completed 或 NORMAL actor-failure/
  cancellation rollback；
  authorization proof 的 nullable terminal-evidence triple 使用 closed kind
  `MODEL_EFFECT_FAILURE|POLICY_REJECTION|PREFLIGHT_REJECTION|CANCEL_EVENT|
  RUNTIME_FAILURE`；Runtime grant 前已从 authority record read-back，Store 要求 Outcome
  receipt 与 proof exact equality，不接受 caller 单独提交的 ref/digest；
  这些字段全进入 Outcome ID；golden vectors必须区分 block reasons、malformed actor
  output、policy/preflight rejection、no-op、actor failures 和 cancellation receipts；
- non-null Outcome context 必须通过 `(context_id,intent_id)` composite FK 指向同一
  Intent 的 Context；禁止分别合法但交叉拼接的 Intent A / Context B；
- allowed status matrix 由 transaction validator 封闭校验：`source_status=blocked`
  iff `decision_status=blocked`，且 artifact 必为 `not_produced`；
  `source_status=not_requested` 只允许 Intent 中已验证的 registered control/no-memory
  binding，decision 可为
  `actor_failed/rejected/no_op/completed/cancelled` 但不可 `blocked`；
  `cancelled_before_recall` 与 `failed_before_recall` 只允许上一条 exact mapping；
  `empty/degraded/ok` 同样只允许后五种 decision status。`empty` Context item 数必须
  为 0，`ok` 必须至少 1，`degraded` 按 pinned fallback policy 可为 0 或多项；
- `outcome_reason_code` 是 mandatory closed source-level reason：`blocked` 只允许
  `blocked_request_invalid/blocked_identity_mismatch/blocked_policy_mismatch/
  blocked_corrupt_input/blocked_contamination/blocked_private_exposure/
  blocked_retention_revoked`；`not_requested` 只允许 `registered_not_requested`；两个
  pre-recall status 各用同名 reason；`empty/degraded/ok` 各用
  `retrieval_empty/retrieval_degraded/retrieval_ok`。它不替代 decision terminal reason；
- Context 已提交后若 cancellation/actor failure 的 closure authorization 胜出，Outcome
  保留原 Context/source status；Runtime 从 exact Context membership 为每张 card 写且只写
  `not_considered_cancelled` 或 `not_considered_actor_failed`，empty Context 为零行。normal
  actor 禁止这两个 reason，closure 禁止接收/拼接 partial actor dispositions；
- `recall_decision_dispositions_v1` 以 `(outcome_id,context_id)` 外键指向上项，
  `(context_id,citation_id)` 外键指向 recall items，因此不能借用另一 context 的 card；
- Recall item polymorphic source matrix 由 Context append transaction read-back：
  `semantic/procedure` 必须 `memory_id=source_record_id`，解析到
  `memory_records_v2` 的匹配 `record_kind`，并是 Context 所绑 Recall Input 的 exact
  Knowledge Snapshot member/lifecycle head；其 family/scope/lifecycle event、
  disposition 和 as-of position 必填，且 episodic-only 字段必须 canonical null。
  `episodic` 必须 `memory_id IS NULL`，family/scope/lifecycle fields 也必须 canonical
  null；其 `source_record_id`/digest、Evidence Snapshot ID、bundle digest、Verification
  ID 与 evidence-ledger as-of position 必填并解析到该 Recall Input exact Evidence
  Snapshot member。
  Candidate、非 member、kind mismatch 或 forged digest 全部 rollback；
- outcome `source_status` 必须与 referenced context status 相同，由 transaction
  validator read-back 检查；
- Outcome owner 始终由 `intent_id -> activity_id` 决定，不要求 Attempt 存在；后开的
  Attempt 只可追加唯一 `recall_outcome_attempt_links_v1`，不得回写或 reparent Outcome；
- Knowledge Snapshot member 的 `family_id/scope_variant_id` 必须与 memory payload
  和 lifecycle event 一致；indexed columns 与 JSON 不一致一律 rollback。
- ready index receipt 与 failure receipt 分表；失败重试不改变 source/policy
  identity，成功后按完整 canonical outputs 得到唯一 ready build ID。Recall Input
  只能 FK 到 `derived_memory_indexes_v1`。
- Memory/Procedure target 先从 current lifecycle head 确定性构造 expected retraction
  event ID/digest；`begin_erasure()` 在**同一 Ledger transaction** append Intent、该
  retraction event、head CAS 和各自 journal rows，再 read-back
  `RetentionIntentCommitReceipt`。只有 registry 中非-lifecycle target kind 才传 null
  event，并在 Intent 写 typed `not_applicable_target_kind`。因此 Intent 是 deletion flow
  的首个 durable fact，不存在“先 retraction、crash、却无 open incident”的缝；
- `begin_erasure()` 必须先按 stable `incident_id/retention_erasure_intent_id` 查询既有
  transaction，再做 expected-head CAS。same incident + byte-identical Intent/retraction
  exact retry 验证 Intent/event/journal receipts，以及 current head 等于该 retraction 或为
  其合法 descendant 后返回原 `RetentionIntentCommitReceipt`；same incident/target 但
  payload 不同是 identity conflict。reply loss 后不得从新 current head 重派生第二 event；
- Intent 冻结 incident/target/object generation 与 exact affected index set；从其 journal
  position 起 open Intent 就进入 deny set。在执行任何 external erasure/invalidation
  **之前**必须已 read-back该 receipt；
- Adapter 再通过 `RetentionRuntimeRead` public getters read-back exact external artifact
  erasure proof 与每个 expected ready index artifact 的 invalidation proof，要求 incident/
  target/generation exact equality；最后 append 引用 Intent 的 Tombstone。裸 digest、漏
  index、extra index、foreign generation 或顺序颠倒均 fail closed；
- `_assert_publishable_retention_frontier(tx, ...)` 是 Store-internal、transaction-local
  implementation detail，**不属于任何 public Protocol**，也不返回可供调用方跨事务持有的
  capability/check receipt。它不是可在
  两次 public 调用间复用的 check。每个新 Knowledge/Evidence Snapshot、ready index、
  Recall Input 或 Recall Context append 必须在**自己的同一 Ledger transaction**自行派生
  current `RETENTION_KINDS` frontier/set、展开 canonical reachable-target closure、
  anti-join open Intent/Tombstone；有 caller expected check 时还须 exact equality。public
  `append_*` 不得先 check 后另开 transaction；caller 不能用 stale frontier 绕过删除；
- recovery 从 `list_open_erasure_intents()` 扫描并以同 incident/target IDs 补齐 external
  receipt、invalidation 和 Tombstone suffix。crash 在任一 seam 后 open Intent 已先
  durable，因此 publication/recall 始终 blocked；不得在 external erasure 后才首次留下
  canonical recovery fact；

`contests` 以排序后的两个 memory IDs canonicalize；`supersedes`、`scope_refines`、
`procedure_implements` 必须通过 recursive-CTE cycle check。FTS/vector 实体不建在
canonical ledger DB：它们位于内容寻址的独立 index artifact，ledger 只存 build
receipt，避免 virtual/shadow tables 被严格 schema validator 误判。

### 7.2 必需索引

至少建立：

```text
idx_memory_records_family(family_id, created_at)
idx_memory_records_scope(scope_variant_id, record_kind, decision_point, domain)
idx_memory_evidence_experience(experience_id, relation)
idx_lifecycle_memory(memory_id, scope_variant_id, created_at)
idx_distillation_work_pending(namespace, record_id)
idx_distillation_assignment_run(campaign_run_id, activity_id)
idx_distillation_completion_activity(activity_id, work_item_id)
idx_evidence_snapshot_member(experience_id, snapshot_id)
idx_snapshot_members_memory(memory_id, snapshot_id)
idx_retention_target(target_kind, target_id)
idx_retention_intent_namespace(namespace, record_id)
idx_decision_recall_input(recall_input_id, created_at)
idx_recall_outcome_intervention(intervention_id)
idx_index_build_sources(knowledge_snapshot_id, evidence_snapshot_id, adapter_kind)
```

SQLite schema validator 必须检查列顺序、类型、NOT NULL、PK、UNIQUE、FK 和命名
索引，延续 revision 2 的 fail-closed 行为。

### 7.3 Commit journal and typed snapshot frontiers

schema-v3 Store 的**每个 canonical logical-record** append helper，包括对 legacy
v1/v2 表的新增 append，都必须走同一底层 transaction helper：

1. `BEGIN IMMEDIATE`（InMemory Adapter 持同一 Store lock）；
2. validate canonical payload、indexed columns 和 namespace；
3. insert canonical row，或对 exact retry read-back 验证 payload bytes/digest；
4. 对首次 insert 在同一 transaction 插入唯一 `ledger_commits_v1` row；
5. read-back canonical row + journal row，验证 record kind/ID/payload digest；
6. commit，并返回原始/新 `position`。

exact retry 已存在时不得插入第二个 journal row或推进 position。canonical row 缺
journal、journal 缺 target、digest 不同或 duplicate logical ID/payload 不同都
fail closed；open-time integrity validator 对所有 schema-v3 时期 canonical
logical-record tables
做双向检查。migration bootstrap rows 只在迁移 transaction 中产生。

`ledger_record_registry.py`（由 `ledger_migrations.py` schema validator 导入）必须
显式登记 `record_kind -> canonical table -> ID extractor -> namespace extractor`。
`evidence_snapshot_members_v1`、`knowledge_snapshot_members_v1`、
`recall_input_index_builds_v1`、`decision_recall_items_v2` 和
`recall_decision_dispositions_v1` 是其父 payload 的 normalized indexed projection；
`memory_scope_variant_heads_v1` 是 lifecycle journal 的 derived mutable projection。
这些表不分配独立 journal position，必须和父 record 同 transaction 写入，并由
read-back validator 逐字段证明等于父 payload；orphan/extra/missing projection row
仍 fail closed。`memory_evidence_links_v2`、`memory_relations_v2`、
`recall_outcome_attempt_links_v1`、`distillation_work_assignments_v1`、
`distillation_batches_v1`、`distillation_reports_v1`、
`distillation_commit_conflicts_v1` 和 `distillation_work_dispositions_v1` 则是独立
logical records，使用第 6.2 节 ID 并各有一个 journal row。新增表必须在 schema
review 时明确归入两类之一。

Snapshot Builder 不读取 `MAX(position)` 全局值，而读取以下 typed namespace
frontier：

```text
EVIDENCE_KINDS = {
  hypothesis, attempt, observation, verification,
  intervention, trial_provenance, experience
}
LIFECYCLE_KINDS = {knowledge_lifecycle_event}
RETENTION_KINDS = {retention_erasure_intent, memory_retention_tombstone}
```

Evidence Snapshot 的 `ledger_position` 是其 namespace/visibility 下
`EVIDENCE_KINDS` 的最大可见 position；Knowledge Snapshot 的
`lifecycle_position` 是其 namespace 下 `LIFECYCLE_KINDS` 的最大可见 position。
Retention checks/publication barriers 使用 namespace 下 `RETENTION_KINDS` 的**当前**
最大 position 与 canonical open-intent+tombstone set digest；caller 的 expected
frontier/set 只做 CAS equality，不能选择较旧 as-of view。
snapshot、recall、outcome、index、outbox、acceptance 及 journal metadata 本身不
推进这两个 frontier。空集合使用规范 sentinel position `0`。这样先写 snapshot 再
重放同一 request 不会改变 ID。InMemory/SQLite 必须通过同一 append-journal/
frontier contract suite。

### 7.4 Atomic distillation transaction

`KnowledgeStore.commit_distillation(plan, completion, authorization)` 是 successful
path 的唯一 writer；它在一个 `BEGIN IMMEDIATE` transaction 中：

1. 在打开本地 write transaction 前通过 Runtime public getter read-back immutable
   commit authorization，验证其
   `GRANTED` transition 在 current Run version/Activity generation/fence 上先于任何
   cancel/fail control CAS，并逐字段匹配 Assignment、commit-attempt ordinal、logical
   Effect、proposal/Commit Plan artifacts 及预期 Batch/Report IDs/digests；随后在本地
   transaction 内重算 plan 的全部 canonical bytes/IDs/digests。若同一 authorization 已有
   successful Completion 或 Commit Conflict，exact retry 只 read-back 原结果；
2. 在任何 semantic write 前比较 proposal 的所有 expected scope heads，并在同一
   transaction 派生 current `RETENTION_KINDS` frontier/set，展开 plan 每个 source
   Experience bundle、proposed Memory/Evidence Links 与受影响 index 的 canonical
   reachable-target closure。head stale 使用 `LIFECYCLE_HEAD_STALE`；任一 open Intent/
   Tombstone 命中使用 `RETENTION_REVOKED`；若两者同时命中，必须由 Store 选择
   `RETENTION_REVOKED`，且 lifecycle head-delta arm canonical null，禁止实现自行择一。
   两种 closed-union 结果都不得写 Batch/Candidate/Knowledge/
   Report/Completion，只 append/read-back 唯一 `DistillationCommitConflict` + journal row
   并返回 `DistillationNoCommitReceipt`；只有 head 与 current retention checks 都通过才
   进入成功路径。proposal/plan/authorization 可绑定预检，但不能替代该线性化检查；
3. 验证 Evidence Snapshot membership，并通过 canonical Verified Evidence Bundle
   逐一交叉验证 source rows/digests；
4. 检查已存在 content-derived IDs 的 payload 完全一致；
5. append candidates 及各自 commit-journal row；
6. append canonical Distillation Batch 及 journal row，并 read-back exact Work Item/
   Experience/candidate coverage；
7. append promoted memory records 及 journal row（rejected/deferred candidate 无 record）；
8. append memory evidence links 及 journal row；
9. 按 scope-variant ID 和 dependency order 处理 lifecycle chain；对**每个** event
   验证当前 expected head，append event + journal row，随后立刻以
   `UPDATE ... WHERE lifecycle_event_id=:expected` 或 genesis insert CAS head 到该
   event，rowcount 必须为 1，再处理同 scope 的下一个 event；
10. append memory relations 及 journal row，此时其 memory/event FK 和最终 head 均已存在；
11. append Distillation Decisions 及 journal row，此时 nullable promoted memory FK 已存在；
12. 为 exact singleton Work Item append 一条 `DistillationWorkDisposition` + journal：
    有 Candidate 时绑定 covering Decision；无 comparator/不可比较/无合法 candidate 时
    使用 closed no-candidate disposition 且 Decision 必须 null；
13. 重新投影并校验 affected scope-variant final heads；
14. 以 exact committed IDs、Work Item/Experience/Disposition coverage 和 sorted affected-
    active-view digest 构造、
    append canonical Distillation Report 及 journal row，再通过 getter read-back；
15. append 与 authorization、Batch、Report/Disposition exact matching 的 `completed` Completion
    及 journal row；
16. 验证本 batch（含 Batch/Disposition/Report/Completion）每个 canonical logical append 都恰有
    一个 digest 匹配的 journal row，所有 normalized projections 与父 payload完全一致；
17. `foreign_key_check` / integrity check 后 commit，并返回含 Batch、Disposition、Report、
    Completion 和全部 append receipts 的 `DistillationCommitReceipt`。

SQLite FK 使用默认 immediate semantics；本顺序不得改回“decision/relations 先于其
target”，也不得把一条 scope chain 的多个 event 全插完后只做一次 final-head CAS。
true contradiction 必须按 old-active→old-superseded→new-contested 两次连续 CAS。
同 batch 的 dependency graph 若不能拓扑排序则在 transaction 前拒绝，不依赖
`PRAGMA defer_foreign_keys` 隐藏错误。

成功路径任一步失败必须 rollback。conflict 分支只允许 Conflict+journal 两行，二者
原子且不能与同 authorization 的 Batch 共存。fault-injection tests 在每个 numbered
point 抛错并证明没有 partial visibility，尤其不允许 Knowledge/Report 已可见但
Completion 缺失。两个 campaign 对同一 scope old head 并发时恰一项成功；另一项得到
NO_COMMIT_CONFLICT、Runtime retire authorization 后可从新 head 重提，不会永久
`COMMITTING`。
`RETENTION_REVOKED` 同样先由 getter/digest 证明零 semantic write并 retire authorization；
Runtime 只能从 current retention-clean inputs 重新 propose，或在 Work Item source 已不可
处理时按 pinned policy 走 typed failure closure，绝不能重用旧 plan/authorization。

### 7.5 Migration algorithm

支持路径：

```text
empty/0 -> create legacy v1 tables -> revision 2 sidecars -> revision 3 tables
revision 2 -> revision 3 tables
revision 3 -> validate and open
other/partial/unknown -> fail closed
```

迁移步骤：

1. `BEGIN IMMEDIATE`；
2. 保存所有 legacy table `record_id + hex(payload_json BLOB)` 摘要；
3. 验证 revision 2 schema、FK 和 integrity；
4. 创建全部 revision 3 表和索引；
5. 对既有 canonical rows 按 `(record_kind, record_id)` 排序写
   `ledger_commits_v1` bootstrap positions 和 payload digests；这是新增 metadata，
   不声称恢复历史 wall-clock append 顺序；namespace 只能来自可验证的既有
   task/project mapping，否则标成隔离的 `legacy_unscoped`，不得 active recall；
6. 不调用 LLM、不生成 Candidate/Knowledge，不信任 nested Experience 副本；
7. 将所有 legacy Knowledge 标记为 audit-only 的 migration metadata；不修改旧表；
8. 校验 legacy payload hex 完全相同；
9. 设置 `PRAGMA user_version=3` 并 commit；
10. reopen 后对 `sqlite_master` 的 table/index/column/FK/CHECK SQL 做 golden schema
    比较，再执行完整 `foreign_key_check`/integrity 验证。

禁止：

- 在 DB open 时自动重蒸馏；
- 给旧 Knowledge 猜测 Intervention、effect 或 provenance；
- 重写旧 Recall Context；
- 把旧 `lesson` 自动 active；
- 将旧 Chroma index 当作 revision 3 index。

显式 offline command 可以 `--dry-run` 评估 legacy source 是否具备 valid
Verification、changed Intervention 和 Trial Provenance；满足条件也只能生成
Knowledge Candidate，再走正常 policy。

### 7.6 Rollback

回滚代码可以关闭 v3 reader/writer 并继续以 revision 3 DB 的 legacy tables 提供
record/legacy recall；不得将 `user_version` 降回 2 或删除新表。旧代码不能打开
revision 3，因此发布必须提供兼容 reader 或在 rollout 前备份；rollback runbook
必须在 Phase 0 冻结。

## 8. Distillation Implementation

### 8.1 Eligibility

候选 source 必须同时满足：

- completed Experiment Attempt；
- exit code、Artifact refs 和 digests 有效；
- Verification valid 且 outcome 分类完整；
- Trial Provenance 存在且与 Attempt/Observation/Intervention 匹配；
- Evaluation Contract、dataset、source、config、environment identity 可解析；
- private evaluator payload 未进入 actor/drafting view；
- changed/no-effect/baseline manipulation 语义明确。

invalid、environment failure、execution failure 仍保留在 Experience Ledger，
但不是 semantic candidate。它们可以作为诊断 Procedure 的 failure evidence，需
独立 policy。

### 8.2 Comparison construction

首版支持：

- 同一 stratum 下 baseline vs changed Intervention；
- 同一 stratum/seed 的 paired comparison；
- 多 seed 对相同 normalized action family 的 replication；
- verified no-effect 作为反对 action utility 的证据；
- guardrail violation 作为 counterevidence。

禁止跨 Evaluation Contract、dataset digest、source digest 或不等预算直接聚合。

### 8.3 Candidate validation reasons

机器可统计 reason codes 至少包括：

```text
missing_verification
missing_trial_provenance
private_evaluator_dependency
non_comparable_evidence
duplicate_support_unit
missing_decision_point
missing_typed_action
generic_or_non_actionable
missing_effect_estimate
missing_guardrail_evidence
insufficient_independent_support
scope_split_required
true_contradiction
eligible_provisional
eligible_active
eligible_contested
```

### 8.4 Family and conflict

- family ID 不包含 prose；
- family ID 也不包含 scope；validated `scope_variant_id = digest(family_id,
  normalized MemoryScope)`；
- compatible scope 的反向 evidence 产生新的 contested record；
- 不同 scope 产生同 family 下的新 scope variant 和可选 `scope_refines`
  relation；
- 更新外部 current-value 的 versioned fact 可由 deterministic version policy
  supersede；
- scientific contradiction 不能用“最新记录”覆盖；
- supersession graph 必须无环；
- retraction 需要 provenance/validity incident evidence 和 policy identity。

true contradiction 的 transaction 顺序固定：

1. 用 current record 的全部 Evidence Links 加新支持/反对 links 构造 immutable
   replacement，`prior_memory_id=current_memory_id`，同 family/scope variant；
2. 对 current record append `superseded` lifecycle event，并以 current head 做 CAS；
3. 对 replacement append `contested` lifecycle event，其 `prior_event_id`/
   `expected_head_key` 是上一步 superseded event，并立即 CAS scope-variant head 到
   replacement contested event；
4. append canonical sorted-pair `contests` relation，由 contested event 导致；
5. read-back 并验证 scope-variant final head 正是 replacement contested event；
6. append `DistillationDecision(disposition="promoted_contested",
   memory_id=replacement)`。

以上六步和各自 journal row 在第 7.4 节同一 transaction。normal/confirmatory
Snapshot Selection Policy 排除 contested head，因此不会暴露旧 active 记录或新的
争议记录；只有明确允许 contested 的审计 profile 可显示双方。后续 adjudicating
evidence 必须再创建 replacement，先 supersede contested head，再让新 record 以
active/contested 开始；不得给旧 record 补 evidence 后原地 `Contested -> Active`。

### 8.5 Procedure compilation

首版只编译 typed Intervention/diagnosis trajectory：

- 不从 chat transcript、generic event log 或 MemoryStore episode 编译；
- steps 只能引用 allowlisted tool/Intervention action；
- 每一步声明预期 artifact/Effect receipt 类型，但 Procedure 本身不授权执行；
- trigger/precondition/success/failure/early-stop/rollback 完整；
- 至少达到 policy 的 independent support threshold；
- Skill Adapter 只能装配现有注册工具，不生成任意 Python。
- 每个实际 step 仍通过 Durable Runtime Effect、普通 authorization 和 receipt；
  inactive/tampered/version-mismatched Procedure 只可展示为审计证据，不能执行。

## 9. Retrieval Implementation

### 9.1 Request construction order

在 `ImprovementCycleRunner` 每次 Decision Point：

1. 读取本 arm 自己上一 Attempt 的 verified feedback，并从 pinned Intervention
   Catalog 读取 allowed knobs/protected-field digest；
2. Runtime 从 Evaluation Contract 构造、持久化并 read-back 无 private/evaluator
   字段的 `DecisionContractViewRef`；
3. 预分配完整 `DecisionIntentProposal`，绑定 run/activity/iteration/
   generation/arm/pair、`evaluation_task_id`、public `task_scope_id`、上一步
   contract-view ID、logical decision slot/artifact kind 和 exact allowed-action
   digest、planned actor model/config/template/policy refs/digests，以及从 admitted
   Run/arm manifest proof 验证的 Memory Governance Binding；proposal 发布/read-back 后，
   Runtime CAS 创建 `REGISTERING` 与 exact admission authorization，Store append/read-back
   Intent（或 journal typed no-commit），Runtime 再 reconcile 为 `OPEN`/retired；未解决的
   REGISTERING 禁止进入 retrieval/actor；
4. 先重验 current Runtime state。若 actor invocation 前 cancel/fail 已赢得 per-Intent
   closure arbitration：`REQUIRED` 且 Context absent 时提交唯一
   `cancelled_before_recall/cancelled` 或 `failed_before_recall/actor_failed` Outcome；
   `REGISTERED_NOT_REQUESTED` 则提交 `not_requested + cancelled|actor_failed` Outcome。
   两者都不创建 Recall Input/Context、不调用 retriever/planner，并绑定 exact closure
   authorization/receipt；closure 同样先发布 exact Outcome proposal，再由 Runtime
   read-back 后授权，不能由 barrier 直接拼 SQL row；
5. 若仍可运行且为 `REGISTERED_NOT_REQUESTED`，跳过 Evidence/Recall Input/retriever/
   Context，只构造 typed `NoDecisionMemoryBinding`（null IDs、zero cards/tokens），尚不调用
   planner；
   若 `REQUIRED`，才在 episodic lane 开启时捕获 exact arm-local Evidence Snapshot，组合
   Recall Input Snapshot，调用 `prepare_required_decision()` 得到 closed preparation result。
   若为 Context proposal，Runtime read-back exact proposal 后以其 Context ID/payload digest/
   artifact ref/digest CAS 获得 `APPEND_CONTEXT/NORMAL` authorization，再调用
   `commit_required_decision_context()` 由 Store append/read-back exact Context，最后由
   Runtime reconcile phase；若为 Blocked proposal，则 Runtime 先持久化/read-back artifact，
   再用 strict getter 取得 `DecisionRecallBlockedProof`，不申请 Context authorization、不写
   Context/card、也不进入 planner，并把该 proof 留给第 8 步的 blocked Outcome；
6. 从 exact Context 构造 `RequiredDecisionMemoryBinding`，或构造
   `NoDecisionMemoryBinding`；在任何 actor Effect preparation 前先把该 discriminated
   union 作为 scoped Runtime planner-input artifact 发布并 read-back，再把 exact bytes
   交给 planner。成功响应解析 outer sidecar envelope 与 unchanged v1 proposal，并要求
   echoed `decision_memory` 与输入 byte-equivalent；actor timeout/crash/unparseable response
   仍可从输入 artifact 取得 binding digest；
7. 合法 proposal 继续执行 Phase A preflight/runner；不合法或 actor failure 走 typed
   terminal path。Context 后 cancel/fail 若先赢得 arbitration，不使用 partial actor draft，
   而由 Runtime closure 为每张 card 生成 exact `not_considered_*` disposition；
8. terminal evidence 齐备后，normal builder 或 Runtime closure builder 先构造并发布
   immutable `RecallDecisionOutcomeProposal` artifact；Runtime read-back exact Outcome
   ID/payload digest/artifact ref/digest 后，经 per-Intent CAS 获得
   `APPEND_OUTCOME/NORMAL|RUNTIME_CLOSURE` authorization，再由 Store 一次性提交、
   read-back 并由 Runtime reconcile 唯一 immutable Recall Decision Outcome；
   blocked 分支只使用 `NORMAL` authority，并要求 Outcome proposal、authorization、最终
   Outcome 的 `blocked_source_proof_ref/digest` 三者 exact equality，Store 再独立 getter
   read-back 并逐字段验证 proof；
   blocked/not-requested/cancelled-before-recall/failed-before-recall/empty/degraded/actor
   failure/rejected/no-op/completed/cancelled 都有记录，合法执行的 outcome 绑定
   effective config/manifest receipt。

baseline/no-memory 也有 Decision Intent 和
`source_status=not_requested`、null-context、zero-card outcome，不能绕过 denominator，
也不能误记为 `blocked`；其 Intent 必须在 append 时已经以 admission proof 固定
`REGISTERED_NOT_REQUESTED`，不能等写 Outcome 时临时声明。

`prepare_required_decision()` 虽为迁移期兼容接受 `contract_view`、Catalog/allowed-action ref，
但必须逐一验证其 IDs/digests 与已持久化 Intent bindings 完全相同；不相同为 typed
blocked identity error，禁止“以参数为准”覆盖 Intent。

Control 和 Treatment 共享相同的初始 baseline Observation。分叉之后，每个 arm
只接收自己的上一 Observation；不得把 Treatment feedback 喂给 Control。

### 9.2 Hard filters

按固定顺序执行：

```text
namespace/visibility
-> evaluator-private exclusion
-> Knowledge/Evidence Snapshot membership
-> current open-retention-intent + tombstone check before index artifact/member content load
-> active/provisional/contested profile eligibility
-> public task_scope/domain (+ exact evaluation_task only for instance-specific records)
-> dataset/source/model/environment/version scope
-> Evaluation Contract/metric/budget compatibility
-> Decision Point
-> allowed action/knob applicability
-> temporal validity and drift policy
```

任何 forbidden item return 都是 hard failure，不能由高语义相似度抵消。
`reachable_retention_targets(recall_input)` 是唯一 canonical transitive expansion：从
Recall Input 展开 Knowledge/Evidence Snapshot members；semantic/procedure member 再展开
current lifecycle event、全部 Memory Evidence Links、每个 Experience 的 canonical
Hypothesis/Attempt/Observation/Verification/Intervention/Trial-Provenance bundle 和 artifact
refs；episodic member 直接展开同一 bundle；每个 ready index 展开 build receipt、member
source mapping、content-addressed artifact ref/object generation。按 `(target_kind,target_id,
object_generation?)` 去重排序，任一 open Intent/Tombstone 命中闭包就 block。只检查
memory_id 或 snapshot direct member 不合法；closure 算法/version/digest 写入
`RetentionCheck` 并有 golden vectors。
`RetentionStore.check_recall_input()` 在一个 read transaction 固定 current
`RETENTION_KINDS` frontier/open-intent+tombstone set digest 并检查 Snapshot members +
上述完整 reachable closure。命中任何 target 时
返回 typed `blocked_retention_revoked`，并将该 exact `RetentionCheck`（同一 non-null
Recall Input ID/digest、frontier、tombstone-set digest、canonical sorted blocked targets）
封入 `DecisionRecallBlockedProposal`；proposal 必须持久化/read-back，随后其 proof ref/digest
绑定 blocked Outcome/authorization。不得读取旧 index artifact、不得降级为空或 lexical
fallback；只有新建 tombstone-clean Snapshot/index/Recall Input 才能继续。passed
`RetentionCheck` 的 frontier/digest 进入 Context；blocked check 只通过 blocked proof 进入
Outcome，禁止运行时另造第二份 check。

### 9.3 Candidate Adapters

- lexical Adapter 使用 SQLite FTS5/BM25；若目标 Python/SQLite 构建没有 FTS5，
  显式使用 deterministic token BM25 fallback 并记录 Adapter identity；FTS/shadow
  tables 位于 derived index artifact，不进入 canonical ledger DB；
- semantic Adapter 使用 policy 指定的真实 embedding model，必须 pin immutable
  revision、dimension、normalization 和 digest；
- tests 使用可注入 deterministic fake encoder，不访问网络；
- production embedding 不可用时，按 pinned policy lexical fallback 或
  `degraded`；不得 hash fallback 后标成 semantic；
- direct structured Adapter 负责 exact failure signature、provenance 和 recent
  verified Experience。

confirmatory semantic Adapter 使用 pinned local model 预计算的 float32 matrix、exact
cosine search、预注册 score quantization 和 stable-ID tie-break。ANN 只允许
development profile，不能支持 replay/confirmatory requirement。

index build 输出先提交为 Runtime-owned content-addressed artifact；Experiment
Ledger 只追加含 ArtifactRef/digests 的 `DerivedIndexBuildReceipt`。本地 materialized
index 可删除，不能成为 canonical truth。

### 9.4 Final ranker

final ranker 是 deterministic Implementation。Feature 分为：

1. hard-pass applicability；
2. lexical/semantic relevance；
3. expected decision utility；
4. evidence strength、effect size/uncertainty；
5. counterevidence/contested penalty；
6. dependency/environment drift；
7. novelty 和 family diversity；
8. stable ID tie-break。

不要把 wall-clock timestamp 除以常数当 recency。Freshness 只由有语义的
dependency/version/time predicate 计算。

### 9.5 Renderer

Renderer 只使用 typed Evidence Card 字段，不重新让 LLM 总结。卡片必须显示：

```text
why retrieved
applicability
recommended/avoided action
observed effect and uncertainty
guardrails
support and counterevidence citations
disposition/version/as-of
```

默认 3 cards / 1,200 tokens；token 数由 pinned tokenizer 对完整 rendered memory
section（header、separator、citation 全部包含）计算，不用逐卡 estimate。
confirmatory policy 固定后不能由 CLI 临时覆盖。

## 10. Evidence、Knowledge 和 Recall Input Snapshots

Evidence Snapshot build：

1. `BEGIN IMMEDIATE` / InMemory lock；
2. 固定第 7.3 节 namespace/visibility-scoped Evidence frontier，并派生 current Retention
   frontier/open-intent+tombstone set，不读 caller cutoff/global max；
3. 按 exact namespace/run/arm/pair 与 eligibility policy 选 Experience，展开每个 candidate
   的完整 canonical bundle/artifact reachable-target closure，并在读取任何 separately
   stored content 前 anti-join 所有 open Intent/Tombstone target；
4. cross-validate 每个 canonical Verified Evidence Bundle；
5. 排序 exact members，计算 ID，append snapshot + member projections + snapshot 的
   一个 journal row，read-back 后 commit；members 不独立 journal，snapshot 自身不
   推进 Evidence frontier。

Knowledge Snapshot build：

1. 固定第 7.3 节 namespace-scoped lifecycle frontier 与 current Retention frontier/set，
   不读 caller cutoff/global max；
2. Builder deterministic fold events；
3. 对每个 candidate head 展开 memory/lifecycle/Evidence Links/Experience bundle/artifact
   reachable-target closure，先排除任何命中 open Intent/Tombstone 的 candidate，再按
   Snapshot Selection Policy 选择每 scope variant 一个 eligible head；
4. 验证所有 Evidence Links 与 closure digest；
5. 排序 members；
6. 只绑定 selection policy/namespace，计算 ID；
7. Store append snapshot + member projections + snapshot 的一个 journal row，
   read-back 并复算 ID；members 不独立 journal，snapshot 自身不推进 lifecycle
   frontier。

Derived indexes 以 exact Knowledge/Evidence Snapshot 为输入构建并产生 ready
receipt；ready receipt、Recall Input 和 Context 的 append transaction 都在自身 Store
transaction 展开包括 index artifact/object generation 的完整 reachable closure，重验
current Retention frontier/set equality 和 anti-join；失败只写 failure receipt，不能被
Recall Input 引用。随后
Recall Input Snapshot 绑定 source snapshots、Retrieval Policy、renderer/tokenizer 和
ready build receipt IDs。Retrieval/index policy 不进入 Knowledge Snapshot ID，因而
不存在 `snapshot -> index -> snapshot` hash cycle。

必须证明：

- 追加无关 raw Experience 不改变既有 snapshot；
- active/lifecycle/policy membership 改变产生新 snapshot；
- 重放同 request 得到相同 snapshot；
- Evidence Snapshot 的 exact members 不受捕获后的 append 影响；
- 同 source/policy 的 index rebuild 产生相同 member/vector/build digest 与 final cards；
- held-out transfer 的 evaluation-task IDs 与 snapshot source-task/lineage 交集为 0；
  same-task/new-seed 只允许 task ID 相同，seed/Run/Attempt/artifact/answer/gold/
  evaluator-private lineage 仍必须零交集；
- confirmatory Run 没有写入 active development memory 的权限。

## 11. Runtime integration

### 11.1 第一条 tracer bullet

仅修改 `intervention_plan`：

```text
frozen Research Context Snapshot
  -> baseline execution or previous verified feedback
  -> sanitized Decision Contract View + preallocated Decision Intent
  -> exact Knowledge/Evidence/index receipts -> Recall Input Snapshot
  -> DecisionRecallRequest
  -> max 3 Evidence Cards
  -> RecalledInterventionDecision sidecar + unchanged InterventionProposal v1
  -> system-resolved config
  -> Phase A execute/verify/provenance
  -> RecallDecisionOutcome (all terminal statuses)
  -> Experience append
  -> ExperienceDistillationReceipt
  -> async/deferred distillation
```

prepare/survey/plan/implement 不再复用这份 Recall Context。它们在后续 PR 中拥有
各自 Decision Point 和 profile。

### 11.2 Shared mutable state removal

删除运行时：

```python
self.loop.knowledge_gate = KnowledgeGate(...)
```

domain/model/policy/snapshot 都来自 immutable request。Factory 在 application
Adapter 启动时装配 Retriever、Distiller 和 Store；一个 Research Run 不改变另一
Run 的 policy。

### 11.3 Completion and defer

Research Run completion 需要每个 Run-owned Decision Intent 的唯一
`RecallDecisionOutcome`，以及每个 completion-required durable Experience 对应的一个
`ExperienceDistillationReceipt`。receipt 可以是：

- `queued_for_comparison`；
- `deferred_ineligible`；
- `not_required`；
- `abandoned_before_enqueue`（只用于 exact Runtime abandonment proof 关闭 pre-enqueue
  orphan，不是 eligibility 判断）。

该 receipt 是 ingestion/enqueue 事实，不是 Candidate 的 Distillation Decision。
Completion barrier 按 Intent/Experience ID 校验基数、唯一性和 read-back digest，不能
用“至少一条 outcome/receipt”替代。Completion 不要求每个 Experience 立即生成
Candidate/Knowledge。异步
consolidation Runtime Activity 稍后聚合多 Run evidence，并单独提交
`rejected/deferred/promoted_*` Distillation Decisions。

`queued_for_comparison` 不是内存队列状态。online Activity 必须调用
`enqueue_distillation(receipt, work_item, abandoned_work_item=None,
profile_artifact_proof=profile_artifact_proof, abandonment_proof=None)`。调用前先发布 profile
bytes，并由 Runtime 为 deterministic Work Item ID 原子创建
Work-Item-owned `ACTIVE` ref + `PENDING` handoff；Ledger transaction 验证 proof 后让
receipt、Work Item、enqueue sidecar/artifact-ref append metadata 和三条 commit journal rows
同时成功。调用方必须独立 read-back Work Item/enqueue receipt 与
`get_distillation_enqueue_transaction()` sidecar，并核对 attempt ID/generation/fence、
original proof/transaction digests 后，Runtime 才可把 handoff CAS 为 `BOUND`；
只有 `BOUND + ACTIVE` 可越过 source Run completion barrier。source
`SCIENTIFIC` Run 到此只拥有 ingestion 事实；即使它随后 terminal，
也不得再为该 Work Item 创建或 dispatch Activity。stable Activity key 为：

```text
semantic_digest(
  "ai-researcher/distillation-activity/v2",
  {"campaign_run_id": campaign_run_id, "work_item_id": work_item_id}
)
```

Admission key、Run、initial command、Activity、Assignment 与 manifest temporary/run-owned
ref IDs 必须全部调用 Durable Runtime implementation plan 的 canonical ID table 对应的同一
pure module/golden-vector artifact；本 projector 禁止复制域名常量或自行重算近似 identity。

Work Item ID 已包含 Distillation + Lifecycle policy identities；Activity ID 不再接受
额外 policy 参数。Assignment 先固定 campaign Run，再计算该 Activity ID 并通过
Runtime proof 验证 owner。

admission projector 每轮只取最老一个 unassigned item，按 commit position/Work Item ID
稳定选择，read-back Work Item 所绑 Campaign Admission Profile，并只按该 profile 冻结
cardinality=1 的 Work Item ID/digest、namespace、Distillation/Lifecycle policy、workflow/
continuation、model/tool/Adapter configuration、Budget Envelope 与 retention 到
`DistillationCampaignManifest`；进程/部署默认值不得覆盖。manifest 先写入 Runtime
Artifact Store，再用 shared canonical helper 从 **Work Item ID**（不是 manifest digest）
派生 `DriveRun` admission key、Run ID 和 initial command ID，drive/read-back 一个
独立、non-terminal、`run_kind=MEMORY_DISTILLATION` 的 Run。Runtime 为每项创建上述
stable Activity，初始状态只能是 non-claimable/non-dispatchable
`AWAITING_ASSIGNMENT`。projector 凭 Runtime proof append/read-back 唯一 Assignment；
Ledger 同时验证 Work Item 是 exact manifest member、ordinal/digest 匹配、Run kind/
non-terminal 状态及 Activity ownership。随后 Runtime Stage Adapter 通过
`get_distillation_assignment_proof()` 自己 read-back proof，以 current Run version +
Activity generation CAS 绑定 assignment ID/digest，并且只有该 CAS 可令 Activity
`AWAITING_ASSIGNMENT -> READY`。旧 proof、cancel/terminal 竞态或 foreign manifest
只能 no-op/fail closed；已存在相同 Assignment 走 reconcile，不同 campaign/Activity
是 identity conflict。campaign worker/poller 只从该 Run 的 READY/assigned-incomplete
item 开始执行，绝不回写 source Run。

V1 禁止多 Work Item manifest。两个 projector 并发看到同一 item 时必须从 pinned
profile 派生相同 manifest digest、Runtime idempotency key、Run/Activity/Assignment
ID；same key/same spec 返回同 Run，same key/different manifest/config 返回 spec identity
conflict并强制 read-back/reconcile winner，绝不创建第二 Run。它不能形成 `[A,B]` 与
`[B]` 的重叠 campaign。未来若要
multi-item scheduling batch，必须先增加由 Experiment Ledger 原子提交的 membership
reservation/claim，再创建 Runtime Run，并升级 schema；不能仅靠 manifest hash。

claim、lease、fencing、retry/backoff 复用 Durable Runtime；memory Store 不保存可变
claim 状态。executor/LLM worker 只把 `DistillationProposal` 写成 Runtime
content-addressed artifact，不能调用任何 Ledger write。独立 Coordinator 先纯函数
prepare/publish immutable `DistillationCommitPlan`（exact canonical Knowledge/lifecycle/
Batch/Disposition/Report bytes/IDs/digests）；Runtime control read-back proposal+plan 后，
在同一个 control-store transaction 以 current Run version + Activity
generation/fence CAS `RUNNING -> COMMITTING`，并写唯一
`DistillationCommitAuthorization`：它绑定 Assignment、logical Effect、proposal ref/
digest、commit plan ref/digest 和预期 Batch/Report IDs/digests。grant 后 Coordinator 从
authorization digest 构造 exact Completion。只有赢得该 CAS 的 control owner 可调用
`commit_distillation(plan, completed_completion, authorization)`；该单一 Ledger
transaction 原子写 Knowledge/lifecycle/Batch/Disposition/Report 和 successful Completion。返回后 control
read-back `DistillationCommitReceipt`，再提交 Runtime Effect/Activity result。

commit authorization 是一个 fenced、必须先解决的 attempt，而不是对 lifecycle CAS
成功的预言。authorization-first 时并发 CancelRun 返回
`PENDING_AFTER_ARBITRATION`，持久化 pending cancel 但不进入 `CANCELLING`、不 revoke
attempt fence；并发 fatal failure 同理登记 pending failure。两个 pending control kind
由同一个 Run-version/control-event CAS 互斥选择 primary kind：cancel-first 只抑制
duplicate/cancellation-induced failure；failure-first 优先，随后 Cancel 只是
closure-help/no-op。独立 integrity/contract/infrastructure failure 另存 secondary evidence，
不能被 cancel 丢弃。Runtime 必须先把 attempt 解析成
atomic success 或 typed `NO_COMMIT_CONFLICT`。success 才是不可撤销 logical commit point：
pending cancel 解析为 `TOO_LATE_COMMITTED` 并完成；pending failure 保留已完成 Work Item，
随后进入 `FAILING/RUNTIME_FAILURE_AFTER_WORK`（若 failure 仍有效）。conflict getter/digest
通过后，Runtime CAS authorization 为 `RETIRED_NO_COMMIT`；pending cancel 在任何 retry 前
进入 cancellation closure，pending failure 在 retry 前进入 `FAILING`/dead-letter；无
pending control 才递增 generation/fence、基于新 head 回 `WAITING_RETRY`。cancel/fail-first
时 control CAS 先撤销 fence，Runtime 不得产生 commit authorization，旧 worker/proof
不能写任何 Batch/Knowledge/Completion。crash-after-authorization 或
crash-after-Ledger-commit 由相同 proposal/authorization/content IDs 恢复；未解析
authorization 保持 `COMMITTING`（完整性不可证明则 `WAITING_INPUT`），不得把同一 slot
关闭成 cancelled/dead-letter。
crash-before-campaign-start、start-after-reply-loss、Run/awaiting-Activity 后 assignment
前、assignment 后 activation/dispatch 前、Activity 后 completion 前、重复
projector/worker，都由
manifest/run/assignment/activity/completion stable IDs 与两类 scan 收敛；任何 crash
prefix 都不能在 terminal source Run 下创建 Activity。
重试耗尽由 Runtime control 先以 control-event CAS 写 mutually-exclusive closure
authorization，再调用 `append_distillation_closure()` 写 `dead_letter` 和可 read-back
Runtime failure receipt ref/digest；该 item 不再 pending，但 release report 必须显式
计数，不能当作 distilled。
transient failure 不写 Completion，item 保持 pending；deterministic non-retryable
failure 直接按 policy 写 `dead_letter`，retryable failure 仅在 Runtime 重试耗尽后写
`dead_letter`。pagination cursor 不是 durable ack，因此 crash-before-assignment/
Activity 不会跳过 item；进程启动/恢复和每轮 sweep 都从最老未完成类别重新开始，
只有可 read-back Assignment/Completion 才改变逻辑集合。
`completed` 写入前还必须通过 Store read-back 证明 canonical Batch/Report FK、Report
ID/payload digest 覆盖该 Work Item 的 exact Experience、namespace/scope、policy
identities 和 committed Work Disposition（可绑定 covering Decision 或 typed
no-candidate reason）；该验证与 Completion/journal append 同 transaction，
不能只检查 ref 或任意 digest 存在。campaign terminal validator 必须枚举 manifest 的
exact ordered set：每项恰有一个匹配 Assignment/Activity 和 terminal Completion，且无
foreign item；只枚举“已经 assigned 的项”不合法。terminal predicate 按顺序互斥：
任一 `dead_letter` 映射 `FAILED/DEAD_LETTER_PRESENT`；否则全部 `completed` 映射
`COMPLETED/ALL_COMPLETED`，但 terminal CAS 前独立 failure 赢时为
`FAILED/RUNTIME_FAILURE_AFTER_WORK`；否则至少一个 `cancelled` 映射
`CANCELLED/CANCELLED`，但该 failure 先赢时为
`FAILED/RUNTIME_FAILURE_AFTER_CLOSURE`。
若所有 Work Completion 已是 `completed` 后才出现不可恢复的 non-work Runtime/
contract/integrity failure，保留这些 immutable Completion，以 typed Run failure receipt
映射 `FAILED/RUNTIME_FAILURE_AFTER_WORK`；不得改写成 dead-letter。
若 exact manifest 零 dead-letter 且至少一个 cancelled status settled，则同类 failure 绑定覆盖每个
slot/status/Completion digest 的 receipt，映射
`FAILED/RUNTIME_FAILURE_AFTER_CLOSURE`；同样不得改写 Completion。

`CancelRun` 与 failure arbitration 使用同一 Run-version/control-event CAS：failure
authorization 先赢就 latch `FAILING`，后到 Cancel 只能帮助闭合或 terminal-noop；
Cancel 先赢就 latch `CANCELLING`，只抑制 duplicate/cancellation-induced closure
failure；独立认证的 integrity/contract/infrastructure failure 在 terminal CAS 前仍可
升级 Run，但不能改写任何 settled Completion。CancelRun 为
每个 manifest slot reconcile/create awaiting Assignment，并为所有没有 completed/
dead-letter/commit authorization 的 slot生成 closure authorization，再 append typed
`cancelled` Completion；`FAILING` 同样以 typed terminal failure receipt ref/digest 将
剩余未授权 slot闭合为 `dead_letter`。这些 closure Activity 不进入 READY/Adapter。exact manifest
coverage、公共 record-closure 与 operational-settlement barriers 全过后才可
`CANCELLED`/`FAILED`；assignment 不删除/重排/requeue，因此不会留下 terminal Run 下
永远 assigned-incomplete 的 item。campaign 不伪造 Hypothesis、Attempt、Decision
Intent、Verification 或 Experience。

Work-Item-owned Campaign Admission Profile ref 的生命周期独立于上述 source/campaign
Run terminal CAS。Runtime 只在 source barrier acknowledgement 与 terminal Work
Completion 均已 read-back，且 campaign
replay/audit retention 已建立独立 root 或确认过期后，提交 handoff
`BOUND -> RELEASED` 和对应 `ArtifactReferenceReleased`；随后普通 Artifact GC 才能按
全局 ACTIVE-ref 计数处理 bytes。Assignment、source Run terminal、campaign terminal
本身都不是 release authority。

## 12. CLI and policy files

新增内容寻址引用：

```text
--memory-mode <off|record_only|legacy_recall|memory_shadow|decision_memory|frozen_memory>
--distillation-policy <path-or-content-id>
--lifecycle-policy <path-or-content-id>
--snapshot-selection-policy <path-or-content-id>
--retrieval-policy <path-or-content-id>
--knowledge-snapshot <content-id|latest-development>
--recall-input-snapshot <content-id>
```

现有 `--experience-mode` 是一个 release 周期的兼容 alias，不能和
`--memory-mode` 同时出现。兼容映射：

| Legacy value | Target mode |
| --- | --- |
| `off` | `off` |
| `record` / equivalent | `record_only` |
| `recall` / `closed-loop` | `legacy_recall`，并发出 deprecation warning |

具体 embedding model、candidate limits、weights、thresholds、profiles 和 fallback
都在 retrieval policy 内。CLI 不新增一组无法完整寻址的散落参数。

Policy load 时分别计算四个 canonical content ID/digest 和一个有序
`policy_set_digest`；Run acceptance 把 alias 解析为 exact source / Recall Input
Snapshot ID。Distillation Policy 写入 receipt/Candidate/record；Distillation +
Lifecycle Policies 同时写入 Work Item/Batch/Decision；Lifecycle Policy 另写入
events/relations；Snapshot Selection Policy 写入 Knowledge
Snapshot，Retrieval/index/renderer/tokenizer identity 写入 Recall Input Snapshot、
Recall Context 和 acceptance manifest。

## 13. Legacy memory 分级处理

### 13.1 立即退出 trusted path

- `memory/store.py` process-local episodes；
- `memory/consolidation.py` summary-to-fact；
- `memory/meta_chain_wrapper.py` generic completion summaries；
- `memory/event_log.py` in-memory event backend；
- agent-callable `skills/memory_tools.store_memory`。

这些路径 MAY 在 compatibility mode 存在，但它们的输出不能进入
KnowledgeDistiller、Knowledge Snapshot 或 Decision-Point Retrieval。

### 13.2 保留为 Working State Adapter

- `session_state.py`；
- `agent_namespace.py`。

文档和类型必须明确它们不是 verified Knowledge。

### 13.3 迁移为 Source/Reference Adapter

- `paper_memory.py`；
- `code_memory.py` / `codetree_memory.py`；
- `tool_memory.py`；
- `rag_memory.py` 的 source chunk/index 能力。

目标包是 `research_agent/inno/reference_index/`。迁移期原 import 发
deprecation warning。Reference Card 必须含 source/path/URI、content digest、
version/retrieved_at、chunk offsets 和 Adapter identity。

### 13.4 Agent tools

Agent 不获得“写 Knowledge”工具。允许：

- `inspect_verified_experience`；
- `recall_verified_knowledge`（受 Decision Point policy 限制）；
- working-state note 工具，名称不得包含 durable knowledge 含义。

兼容 alias 保留一个版本，调用时告警；active/confirmatory mode 禁用 alias。

这里的禁用针对 Treatment/production trusted path。验收 harness 另有 benchmark-only、
read-only `LegacyBaselineAdapter`，只能在 manifest 明列的隔离 C2 arm 读取冻结 legacy
records；它不能写回、不能被 Agent tool 调用、不能进入 T snapshot/index，也不能作为
production fallback。C2 adapter/algo/record-set/budget digests 和 namespace isolation
进入 Stage Manifest/pair report；任何跨 arm 暴露使 campaign invalid。

## 14. Requirements traceability

### 14.1 Governing design invariants

| Requirement | 主代码证据 | 主测试证据 |
| --- | --- | --- |
| VRM-W01, W03 | evidence store + distillation eligibility | `test_knowledge_distillation.py`, store contract |
| VRM-W02 | retrieval source-kind gate excludes `KnowledgeCandidate` rows | `test_decision_point_retrieval.py::test_candidate_records_never_enter_normal_or_confirmatory_context`; requirement check `candidate_record_returns=0` |
| VRM-W04–W06 | comparison/support-unit builder | comparison, duplicate/metamorphic cases |
| VRM-W07–W08 | lifecycle + deterministic gate | contradiction, private/LLM adversarial cases |
| VRM-W09 | transactional outbox + Runtime stable Activity reconciliation | receipt/work atomicity, restart scan, duplicate worker, authorization/no-commit recovery, lifecycle conflict retry, WorkDisposition coverage, terminal/dead-letter tests |
| VRM-L01–L03 | lifecycle reducer + relation validator | full transition matrix, scope split, cycle rejection |
| VRM-L04–L05 | Evidence/Knowledge/Recall Input Snapshot builders | contamination, exact membership, hash-cycle and unrelated-growth tests |
| VRM-R01–R05 | request schema, hard filter, ranker, budgets | retrieval mechanics + gold corpus |
| VRM-R06–R08 | citation resolver, Recall Decision Outcome, Phase A lineage | utilization auditor and runtime integration |
| VRM-R09–R11 | renderer/security/error policy | injection, blocked/empty/degraded and ITT cases |
| VRM-O01, O03 | index builder, namespace policy | rebuild/corruption/private leakage |
| VRM-O02 | Adapter registry rejects `hash`/`non_semantic_test_index` for evaluation or production semantic role | assembly/config tests; requirement check `hash_semantic_assemblies=0` |
| VRM-O04, O06 | trace/report/cost instrumentation | acceptance report schema and causal harness |
| VRM-O05 | explicit ideation fresh-start branch and diversity evaluator | `test_ideation_fresh_start.py`; `ideation_diversity_report.json`; quality noninferiority + preregistered diversity checks |

### 14.2 Memory acceptance requirements

| Requirement group | Implementation deliverable | Blocking artifact |
| --- | --- | --- |
| `MEM-TR-*` | Decision Intent-to-Verification lineage auditor | trace completeness report |
| `MEM-SN-*` | snapshot builder, members, policy identity | `snapshot_report.json` |
| `MEM-WR-*` | comparative distiller and lifecycle | writer acceptance report |
| `MEM-RT-*` | Decision-Point Retriever | retrieval acceptance report |
| `MEM-UT-*` | Recall Decision Outcome and citation-to-config auditor | utilization report |
| `MEM-RB-001..003` | offline corruption/noise/injection harness | robustness report |
| `MEM-RB-004` | preregistered N-vs-T paired outcome runner | confirmatory causal report |
| `MEM-EF-001..003` | scale fixture、完整资源边界和 stage-aware usage attribution | assembled `efficiency_report.json` |
| `MEM-EF-004` | L5 Runtime ref/identity compatibility assembly validator | `runtime_release_refs.json` + final validation receipt |
| `MEM-CA-001` | signed registry/two-frontier、atomic exposure、all-hidden partition authority、A/A + causal lineage auditor | partition/exposure receipts + `aa_report.json` + Pilot/confirmatory reports |
| `MEM-CA-002, MEM-CA-005` | fixed-sequence paired causal contrasts | `confirmatory_report.json` |
| `MEM-CA-003` | external sensitivity、joint assurance、independent Pilot Gate 和 deterministic reserve selection | sensitivity + power + `pilot_gate_receipt.json` + selection receipt |
| `MEM-CA-004` | claim-kind/baseline/family/transfer-scope assembly validator | `claim_report.json` + final validation receipt |

精确定义和阈值只在
[Memory effectiveness evaluation protocol](memory-effectiveness-evaluation.md)
维护；本计划不复制第二套数值。

`requirements_report.json` 必须恰好覆盖 governing design 中全部 `VRM-*` 和本协议
全部 `MEM-*`。`VRM-*` 的原子 checks 可引用同一份 stage report，但不能只靠测试名
或 prose 判定；`MEM-*` 的阈值/统计口径以验收协议为唯一来源。

### 14.3 Atomic requirement registry

以下是 `benchmark/memory/requirements-v1.yaml` 的规范内容；实现时逐行机械转写，
不得保留 range/wildcard。每项只有一个 owner、一个或多个明确 check key、至少一个
exact pytest node 和一个 blocking artifact。validator 同时对该 registry、governing
design 和 evaluation protocol 的 ID 集合做 exact-set equality。
每一 YAML entry 还必须逐项写
`minimum_claim_level`、`required_stages`、`applicability_rule_id`、
`provenance_kind: stage|release_assembly`、`non_waivable_when_applicable`，以及有条件
check 的 claim-level/profile predicate（尤其 `MEM-CA-003` 的 L2/L3+ 两套 checks、
`MEM-CA-004` 的 L3/L4 checks、`MEM-CA-005` 的 claim-kind 条件，以及
`MEM-TR-001`、`MEM-UT-001..004`、`MEM-EF-003` 随 ceiling 扩展的 causal-stage
checks）。这些字段由
验收协议 §2.1/§12 唯一定义；Markdown 表只展示 owner/test/artifact，不省略 YAML
中的适用性字段。任一 ID 缺字段、assembly requirement 伪装 stage provenance 或
required ID 输出 N/A，registry validator fail closed。
表中 pytest filename 的路径解析也是规范性的：`test_decision_recall_integration.py`
位于 `tests/test_runtime/`；`test_memory_acceptance_report.py`、
`test_memory_claim_gate.py`、`test_ideation_fresh_start.py` 位于
`tests/test_benchmark/`；其余均位于 `tests/test_experience/`。registry 写入展开后的
完整相对路径 + `::node`，不得只存 filename。

| ID | Owner / report check key(s) | Exact pytest node | Stage / blocking artifact |
| --- | --- | --- | --- |
| VRM-W01 | `KnowledgeDistiller` / `immutable_source_mutations` | `test_knowledge_distillation.py::test_distillation_never_mutates_evidence` | offline / `writer_report.json` |
| VRM-W02 | `DecisionPointRetriever` / `candidate_record_returns` | `test_decision_point_retrieval.py::test_candidate_records_never_enter_normal_or_confirmatory_context` | offline / `retrieval_report.json` |
| VRM-W03 | `VerifiedEvidenceStore` / `canonical_bundle_mismatches` | `test_knowledge_store_contract.py::test_verified_bundle_rejects_nested_canonical_mismatch` | offline / `writer_report.json` |
| VRM-W04 | `ComparisonBuilder` / `active_without_comparison` | `test_knowledge_distillation.py::test_active_requires_registered_comparison` | offline / `writer_report.json` |
| VRM-W05 | `CandidateValidator` / `active_without_typed_action` | `test_knowledge_distillation.py::test_active_requires_decision_point_and_action` | offline / `writer_report.json` |
| VRM-W06 | `SupportUnitBuilder` / `duplicate_support_inflation` | `test_knowledge_distillation.py::test_duplicate_retry_does_not_increase_support` | offline / `writer_report.json` |
| VRM-W07 | `LifecycleReducer` / `discarded_counterevidence` | `test_knowledge_lifecycle.py::test_counterevidence_is_retained_and_changes_disposition` | offline / `writer_report.json` |
| VRM-W08 | `PromotionPolicy` / `nondeterministic_promotions` | `test_knowledge_distillation.py::test_llm_draft_cannot_override_deterministic_gate` | offline / `writer_report.json` |
| VRM-W09 | `DistillationOutbox` / `lost_or_duplicate_work_items,authorization_without_commit,lifecycle_conflict_recovery,distillation_work_disposition_coverage` | `test_distillation_outbox.py::test_receipt_work_campaign_assignment_restart_and_completion_converge` | offline / `trace_report.json` |
| VRM-L01 | `LifecycleStore` / `in_place_lifecycle_mutations` | `test_knowledge_lifecycle.py::test_lifecycle_is_append_only` | offline / `snapshot_report.json` |
| VRM-L02 | `KnowledgeSnapshotBuilder` / `duplicate_scope_variant_heads` | `test_knowledge_snapshot.py::test_one_actionable_head_per_scope_variant` | offline / `snapshot_report.json` |
| VRM-L03 | `ConflictResolver` / `scope_conflict_accuracy` | `test_knowledge_lifecycle.py::test_scope_difference_splits_instead_of_contests` | offline / `writer_report.json` |
| VRM-L04 | `EvidenceSnapshotBuilder` / `evaluation_or_cross_arm_members` | `test_evidence_snapshot.py::test_confirmatory_snapshot_excludes_evaluation_and_cross_arm_evidence` | offline / `snapshot_report.json` |
| VRM-L05 | `KnowledgeSnapshotBuilder` / `semantic_snapshot_identity_violations` | `test_knowledge_snapshot.py::test_identity_excludes_index_and_unrelated_growth` | offline / `snapshot_report.json` |
| VRM-R01 | `DecisionIntentFactory` / `unbound_recall_requests` | `test_decision_intent.py::test_request_binds_exact_preallocated_intent` | offline / `trace_report.json` |
| VRM-R02 | `HardFilterPipeline` / `forbidden_pre_rank_returns` | `test_decision_point_retrieval.py::test_hard_filters_and_retention_run_before_content_and_rank` | offline / `retrieval_report.json` |
| VRM-R03 | `EvidenceCardRenderer` / `item_or_token_overflow` | `test_decision_point_retrieval.py::test_full_rendered_section_obeys_exact_budget` | offline / `retrieval_report.json` |
| VRM-R04 | `FinalRanker` / `duplicate_family_returns` | `test_decision_point_retrieval.py::test_one_card_per_family_with_counterevidence` | offline / `retrieval_report.json` |
| VRM-R05 | `FinalRanker` / `forced_fill_returns` | `test_decision_point_retrieval.py::test_no_eligible_evidence_abstains_without_fill` | offline / `retrieval_report.json` |
| VRM-R06 | `CitationResolver` / `unresolved_or_forged_citations` | `test_decision_point_retrieval.py::test_polymorphic_citations_resolve_to_bound_snapshot_members` | offline / `trace_report.json` |
| VRM-R07 | `RecallStore` / `intent_terminal_outcome_coverage` | `test_recall_utilization.py::test_every_intent_has_exactly_one_typed_terminal_outcome` | offline / `trace_report.json` |
| VRM-R08 | `UtilizationAuditor` / `citation_execution_mismatches` | `test_recall_utilization.py::test_adopted_citation_binds_exact_intervention_and_config` | offline / `utilization_report.json` |
| VRM-R09 | `MemoryRenderer` / `memory_instruction_executions` | `test_decision_point_retrieval.py::test_memory_text_cannot_override_authority` | offline / `robustness_report.json` |
| VRM-R10 | `RecallAvailabilityPolicy` / `availability_semantic_violations` | `test_decision_recall_integration.py::test_failure_is_degraded_or_blocked_and_itt_is_retained` | offline / `robustness_report.json` |
| VRM-R11 | `RecallErrorClassifier` / `error_classification_mismatches` | `test_decision_point_retrieval.py::test_empty_degraded_blocked_are_disjoint` | offline / `retrieval_report.json` |
| VRM-O01 | `IndexBuilder` / `index_rebuild_mismatches` | `test_recall_input_snapshot.py::test_ready_index_rebuild_is_exact_and_ann_is_nonconfirmatory` | offline / `robustness_report.json` |
| VRM-O02 | `SemanticAdapterRegistry` / `hash_semantic_assemblies` | `test_recall_input_snapshot.py::test_hash_encoder_cannot_assemble_evaluation_or_production_profile` | offline / `robustness_report.json` |
| VRM-O03 | `NamespacePolicy` / `cross_namespace_returns` | `test_decision_point_retrieval.py::test_namespace_arm_seed_and_private_isolation` | offline / `robustness_report.json` |
| VRM-O04 | `LineageAuditor` / `mediation_edge_completeness` | `test_recall_utilization.py::test_write_recall_adoption_execution_verification_chain` | offline / `trace_report.json` |
| VRM-O05 | `IdeationAcceptanceRunner` / `fresh_start_quality_and_diversity` | `test_ideation_fresh_start.py::test_fresh_start_budget_quality_and_diversity_contract` | ideation / `ideation_diversity_report.json` |
| VRM-O06 | `UsageAttributor` / `memory_cost_component_completeness` | `test_memory_acceptance_report.py::test_memory_costs_are_separately_attributed` | offline / `efficiency_report.json` |
| MEM-TR-001 | `LineageAuditor` / `trace_resolvable_rate,dangling_edges,cross_lineage_hidden_reuse,exposure_token_atomicity` | `test_memory_acceptance_report.py::test_mem_tr_001` | every executed hidden stage + signed global exposure frontier / assembled `trace_report.json` |
| MEM-SN-001 | `KnowledgeSnapshotBuilder` / `knowledge_snapshot_replay,hash_cycles` | `test_memory_acceptance_report.py::test_mem_sn_001` | offline / `snapshot_report.json` |
| MEM-SN-002 | `EvidenceSnapshotBuilder` / `evidence_membership_replay,contamination_returns` | `test_memory_acceptance_report.py::test_mem_sn_002` | offline / `snapshot_report.json` |
| MEM-SN-003 | `RecallInputSnapshotBuilder` / `recall_input_readback,frozen_input_writes,duplicate_family_cards` | `test_memory_acceptance_report.py::test_mem_sn_003` | offline / `snapshot_report.json` |
| MEM-WR-001 | `WriterAcceptanceRunner` / `critical_false_promotions` | `test_memory_acceptance_report.py::test_mem_wr_001` | offline / `writer_report.json` |
| MEM-WR-002 | `WriterAcceptanceRunner` / `support_count_metamorphic_changes` | `test_memory_acceptance_report.py::test_mem_wr_002` | offline / `writer_report.json` |
| MEM-WR-003 | `WriterAcceptanceRunner` / `writer_schema_source_fidelity` | `test_memory_acceptance_report.py::test_mem_wr_003` | offline / `writer_report.json` |
| MEM-WR-004 | `WriterAcceptanceRunner` / `lifecycle_transition_accuracy` | `test_memory_acceptance_report.py::test_mem_wr_004` | offline / `writer_report.json` |
| MEM-WR-005 | `WriterAcceptanceRunner` / `promotion_precision,promotion_recall,writer_stratum_gates` | `test_memory_acceptance_report.py::test_mem_wr_005` | offline / `writer_report.json` |
| MEM-RT-001 | `RetrievalAcceptanceRunner` / `request_completeness,typed_missing_blocks` | `test_memory_acceptance_report.py::test_mem_rt_001` | offline / `retrieval_report.json` |
| MEM-RT-002 | `RetrievalAcceptanceRunner` / `forbidden_return_rate,held_out_lineage_overlap` | `test_memory_acceptance_report.py::test_mem_rt_002` | offline / `retrieval_report.json` |
| MEM-RT-003 | `RetrievalAcceptanceRunner` / `candidate_generation_recall_at_20,applicable_family_recall_at_3,all_required_evidence_recall,precision_at_3,ndcg_at_3` | `test_memory_acceptance_report.py::test_mem_rt_003` | offline / `retrieval_report.json` |
| MEM-RT-004 | `RetrievalAcceptanceRunner` / `abstention_f1,duplicate_family_returns` | `test_memory_acceptance_report.py::test_mem_rt_004` | offline / `retrieval_report.json` |
| MEM-RT-005 | `RetrievalAcceptanceRunner` / `citation_resolution,budget_compliance,replay_identity,online_generation_calls` | `test_memory_acceptance_report.py::test_mem_rt_005` | offline / `retrieval_report.json` |
| MEM-UT-001 | `UtilizationAcceptanceRunner` / `disposition_coverage` | `test_memory_acceptance_report.py::test_mem_ut_001` | offline + every ceiling-required causal stage / assembled `utilization_report.json` |
| MEM-UT-002 | `UtilizationAcceptanceRunner` / `claimed_adoption_fidelity,execution_fidelity` | `test_memory_acceptance_report.py::test_mem_ut_002` | offline + every ceiling-required causal stage / assembled `utilization_report.json` |
| MEM-UT-003 | `UtilizationAcceptanceRunner` / `end_to_end_utilization,abstain_forbidden_actions` | `test_memory_acceptance_report.py::test_mem_ut_003` | offline + every ceiling-required causal stage / assembled `utilization_report.json` |
| MEM-UT-004 | `UtilizationAcceptanceRunner` / `offline_terminal_case_coverage,causal_dropped_pairs,typed_terminal_outcomes` | `test_memory_acceptance_report.py::test_mem_ut_004` | offline + every ceiling-required causal stage / assembled `utilization_report.json` |
| MEM-RB-001 | `RobustnessRunner` / `noise_precision_loss,noise_recall_loss,forbidden_returns` | `test_memory_acceptance_report.py::test_mem_rb_001` | offline / `robustness_report.json` |
| MEM-RB-002 | `RobustnessRunner` / `instruction_executions,private_or_cross_scope_leakage` | `test_memory_acceptance_report.py::test_mem_rb_002` | offline / `robustness_report.json` |
| MEM-RB-003 | `RobustnessRunner` / `offline_rebuild_identity,confirmatory_rebuild_identity,adapter_identity_masquerade` | `test_memory_acceptance_report.py::test_mem_rb_003` | offline at L1; add confirmatory at L3+ / assembled `robustness_report.json` |
| MEM-RB-004 | `CausalAcceptanceRunner` / `n_minus_t_lower_ci,invalid_intervention_rates` | `test_memory_acceptance_report.py::test_mem_rb_004` | confirmatory / `confirmatory_report.json` |
| MEM-EF-001 | `EfficiencyRunner` / `online_generation_calls,render_budget_overflow` | `test_memory_acceptance_report.py::test_mem_ef_001` | offline / `efficiency_report.json` |
| MEM-EF-002 | `EfficiencyRunner` / `retrieval_p95_ms,retrieval_p99_ms` | `test_memory_acceptance_report.py::test_mem_ef_002` | offline / `efficiency_report.json` |
| MEM-EF-003 | `UsageAttributor` / `offline_cost_component_completeness,itt_usage_cost_completeness,cost_per_valid_improvement,nonfinite_json_numbers` | `test_memory_acceptance_report.py::test_mem_ef_003` | offline at L1; add Pilot at L2 and confirmatory at L3+ / assembled `efficiency_report.json` |
| MEM-EF-004 | `ReleaseValidator` / `runtime_ref_resolution,runtime_requirement_pass,identity_compatibility` | `test_memory_claim_gate.py::test_mem_ef_004` | assembly / `runtime_release_refs.json` |
| MEM-CA-001 | `LineageAndCausalAuditor` / `admission_before_visibility,registry_authority_signature,lineage_prefix_replay,global_exposure_prefix_replay,exposure_token_atomicity,registry_sibling_omissions,sealed_reserve_non_overlap,deterministic_reserve_selection,cross_lineage_exposure_overlap,registered_pair_integrity,all_hidden_stage_overlap_matrix,contamination,aa_equivalence,unexpected_exposure_differences` | `test_memory_claim_gate.py::test_mem_ca_001` | offline + selected ideation + A/A + Pilot + sealed reserve at L2; add actual confirmatory at L3+ / partition/exposure/selection receipts + `aa_report.json` + causal report(s) |
| MEM-CA-002 | `CausalAcceptanceRunner` / `t_minus_c2_lower_ci,t_minus_c2_point,manipulation_gate` | `test_memory_claim_gate.py::test_mem_ca_002` | confirmatory / `confirmatory_report.json` |
| MEM-CA-003 | `PilotGateAndPowerAuditor` / `sensitivity_gate_pass,sensitivity_lineage_isolation,power_plan_valid,pilot_gate_signature_and_prerequisite_coverage,planned_n_or_stop_reached,confirmatory_reserve_prefix_selected` | `test_memory_claim_gate.py::test_mem_ca_003` | external sensitivity + offline/selected-ideation/A/A/Pilot prerequisite assessments for L2; root assembly creates the final row from those three pre-gate checks plus signed terminal Gate receipt（joint assurance is inside `power_plan_valid`）；add deterministic selection + confirmatory for L3+ / sensitivity + power + `pilot_gate_receipt.json` + selection receipt |
| MEM-CA-004 | `ClaimValidator` / `family_gate,weighted_overall_ci,family_harm,transfer_scope` | `test_memory_claim_gate.py::test_mem_ca_004` | assembly / `claim_report.json` |
| MEM-CA-005 | `CausalAcceptanceRunner` / `t_minus_c0_lower_ci,t_minus_c0_point` | `test_memory_claim_gate.py::test_mem_ca_005` | confirmatory / `confirmatory_report.json` |

## 15. Delivery phases and PR slices

每个 PR 必须有 Interface-level red→green tests，不能以“后续 PR 会补验证”为由
合并不可审计状态。

### Phase 0 — Freeze acceptance contract and baselines

**Deliverables**

- freeze corpus manifest/report schema and metric dictionary；
- 在任何 memory hidden-stage admission/visibility 前完成独立 VQ/task-sensitivity campaign，
  冻结其 manifest/report/terminal receipt，并让 shared identity 只绑定 exact ref/digest；
- 在任何 hidden visibility 前冻结 `ScientificClaimPlan`：canonical release lineage、claim
  ladder/baselines、profiles、normalized utility/endpoints、全部 margins/alpha/decision rules、
  requirement/claim-matrix digests、完整资源边界和 deterministic reserve-selection rule；
- freeze `MemorySharedIdentityManifest`/Stage/confirmatory **schemas and templates** plus
  orchestration tests；真实 release lineage 的 Claim Plan/shared/offline/ideation/A/A/Pilot
  receipts 只能在 Phase 4 visible-development Adapter selection receipt 就绪后、Phase 6
  任一 hidden admission 前生成；confirmatory exact N/task/seed 在 Pilot power artifact 后
  才冻结；
- create minimum gold/adversarial fixtures and red acceptance tests；
- create configured Registry/Validation Authority trust anchors、signed lineage/global
  frontiers、append-only registry schema、`ADMITTED -> EXPOSURE_COMMITTED|NO_VISIBILITY`
  atomic CAS、all-hidden-stage Partition Authority 和 closure/frontier fixtures；
- capture current writer/retriever/utilization baseline；
- freeze migration backup/rollback runbook；
- freeze initial policy schemas and content-ID algorithm。
- freeze explicit `AA0/AA1` common/null Adapter + expected-difference allowlist，以及
  pair-shared content-addressed external-source replay contract（不可 replay 时的 synchronized
  drift probe/margin 也须 pre-register）；

**Exit**

- 所有当前失败都有明确 requirement ID；
- report validator 拒绝缺 threshold、digest 或 raw evidence refs；
- assembly 接受相同 release-lineage/shared identity 的不同 stage campaign，拒绝同
  lineage/stage 第二 logical admission、遗漏 failed/invalid/aborted closure、offline/
  selected ideation/A/A/Pilot/confirmatory reserve/actual 任一适用维度 overlap、unsigned/
  rollback frontier、token/no-visibility 双赢和 campaign 冒用；
- final validator 用 pinned authority 对“排除 receipt 自身”的 artifact set 签名；valid
  fail/invalid receipt 不得授权 publication，pass receipt 才可匹配最高 claim；
- baseline 报告不把当前 system 标成 passed。

### Phase 1 — Schema revision 3 and store contracts

- **PR 1:** immutable models and ID fixtures。
- **PR 2:** schema 3 migration + validators。
- **PR 3:** canonical Verified Evidence Bundle、ledger commit positions、Evidence/
Knowledge/Recall narrow Store contracts、transactional distillation outbox、
retention tombstone 和 atomic batch commit。

**Exit**

- 0→2→3、2→3、3 reopen 全通过；
- old payload hex 全不变；
- partial/malformed schema fail closed；
- InMemory/SQLite 同一 contract；
- 每个 v3-open new/legacy append 与唯一 journal row 同事务；typed Evidence/
  Lifecycle frontier 不被 snapshot/recall/outbox append 或 exact retry 推进；
- queued receipt/work item 原子、restart scan 可达、duplicate worker 收敛、
  campaign Assignment/Runtime proof 可 read-back、source Run 不获新 Activity、
  dead-letter 可见；
- queued Work Item 的 profile bytes/ref/PENDING handoff 先于 Ledger enqueue；Runtime 同
  transaction CAS enqueue attempt 到 `IN_FLIGHT` 后 proof 才可离开，首次 Ledger insert
  只接受 current fence，receipt read-back 后 `LEDGER_PRESENT/BOUND`；source terminal +
  aggressive GC、stop+higher-fence+drain+later-frontier orphan absence proof、
  first not-found→retire→old transaction commits/drains→`QUEUED_PRESENT` 后
  `RETIRED -> LEDGER_PRESENT/BOUND`、commit-before-bind 和 post-Completion retention
  release crash matrix 全过；
- Work Item pins Campaign Admission Profile，`DriveRun` admission/run/initial-command
  identities 由 Work Item ID 唯一派生；不同部署 config 的并发 projector 不能产生第二 Run；
- executor 只能提交 proposal；Runtime commit/closure authorization、pending cancel/
  failure arbitration、atomic Knowledge+Batch+Disposition+Report+successful Completion、
  NO_COMMIT_CONFLICT retirement/reproposal 均通过 crash/race tests；
- nested Experience 与 canonical row mismatch 必须拒绝；
- evidence capture 在并发 append 下仍有 exact members/position；
- fault injection 无 partial distillation。

### Phase 2 — Deterministic comparative distillation

- **PR 4:** comparability/support-unit/effect models。
- **PR 5:** candidate validation and deterministic VQ distiller。
- **PR 6:** lifecycle CAS、family/scope variant、contradiction、Knowledge Snapshot。

初版不依赖 LLM。只有 deterministic VQ/synthetic response-surface tracer bullet
通过后才加 structured drafting Adapter。

**Exit**

- generic/no-action、missing sidecar、duplicate support 被拒绝；
- paired effect/guardrail 正确；
- compatible contradiction→contested，不同 scope→split；
- contested 路径严格产生 replacement + old superseded + new contested + relation +
  `promoted_contested` decision，normal snapshot 不暴露旧/new record；
- concurrent transition 只有一个 expected head commit；
- snapshot identity 与 raw unrelated growth 解耦；
- writer hard gates 通过。

### Phase 3 — Decision-point lexical retrieval and Recall Decision Outcome

- **PR 7:** sanitized contract view、Decision Intent、Recall Input Snapshot、
`DecisionRecallRequest/Context/EvidenceCard` + hard filters。
- **PR 8:** deterministic BM25/direct candidates + rank/diversity/abstain。
- **PR 9:** sidecar decision envelope + Recall Decision Outcome Store（不改 Phase A v1 payload）。
- **PR 10:** ImprovementCycle/Experience Adapter tracer-bullet wiring。

**Exit**

- exact intervention decision 收到自己的 Recall Context；
- blocked/not-requested/empty/degraded/actor-failed/cancelled intent 也有唯一 terminal
  outcome；
- previous verified feedback/catalog 进入 request；
- 同 context 不再注入其他 stages；
- per-card disposition 100%；
- adopted citation→proposal→effective config→manifest 100% 可解析；
- lexical offline gates 通过。

### Phase 4 — Shadow rollout and real semantic Adapter

- **PR 11:** shadow mode/telemetry/offline report。
- **PR 12:** real embedding Adapter + rebuild/index identity。
- **PR 13:** hybrid candidate union and frozen policy comparison。

**Exit**

- hash-as-semantic production path 为 0；
- hash/non-semantic-test Adapter 无法以 production/evaluation semantic role 完成
  registry assembly，`VRM-O02` requirement check 为 0 violations；
- semantic unavailable 有 typed fallback/degradation；
- 删除 index 可重建；
- hybrid/semantic/lexical 只能在 visible development gold 上按预注册 rule 选择；formal
  hidden Stage Manifest 冻结唯一 release Adapter 后只评该 Adapter，不能在 hidden set
  选 winner；
- development selector 写/read-back immutable `RetrievalAdapterSelectionReceipt`；真实
  release lineage 随后按 evaluation §13.0 冻结 Claim Plan/shared/stages，三者 exact-match
  同一 receipt，早于任何 hidden admission/visibility；
- selector exact retry 返回原 receipt，same identity/different bytes fail closed；instrumented
  tests 证明 hidden corpus/member/result read count=0，candidate catalog 外 Adapter=0；
- active rollout 前完成 shadow quality/latency review。

### Phase 5 — Procedure and Reference Memory

- **PR 14:** Procedure Record/compiler and lifecycle。
- **PR 15:** ProcedureCapabilityBinding + pinned-catalog reference validation；每步仍走
ToolInteraction hard filters 与 Runtime final authorization。
- **PR 16:** Reference Card/index Module and legacy source Adapter migration。
- **PR 17:** trusted-path legacy isolation and docs/CLI deprecation。

**Exit**

- 至少一个诊断或 experiment procedure 从独立 verified trajectory 编译；
- inactive/tampered/unknown-tool procedure 不执行；
- Procedure 不成为 Capability Catalog source，不扩大 allowlist/scope/approval；
- Reference Card 可回原文，不能伪装 internal experimental Knowledge；
- legacy episode/fact 永不出现在 active Decision Recall。

### Phase 6 — Offline acceptance and mechanism Pilot

- **PR 18:** 完整 v1 corpus、adjudication 和 report。
- **PR 19:** robustness/scale runner。
- **PR 20:** selected-profile-only ideation fresh-start runner + explicit AA0/AA1 null-harness
  equivalence report。
- **PR 21:** causal Stage Manifest/ITT auditor integration。

运行顺序：

1. writer；
2. retrieval；
3. utilization synthetic response surface；
4. adversarial/scale；
5. read-back Phase 0 已冻结的 external VQ/task-sensitivity receipt，并验证 lineage 隔离；
6. ideation fresh-start quality/diversity（仅 ideation profile）；
7. A/A equivalence + lineage/budget identity；
8. 6–8 fresh-pair manipulation Pilot；
9. clustered variance/ICC sensitivity + power analysis；
10. independent validator 从 signed frontier 枚举 offline、selected ideation、A/A、
    Pilot closures 和排除 final CA003/root provenance 的全部适用 L0–L2
    `PilotPrerequisiteAssessment`，对 pass/fail/invalid 都签发 terminal
    `PilotGateReceipt`；可据任何 terminal receipt 创建审计 L2 root，但只有 pass receipt
    可由 Pilot power artifact 按 frozen strata/order/seed commitment
    生成 deterministic selection receipt 和 confirmatory Stage Manifest，**此时
    不创建 L3/L4 root**。早期 shards 只绑定 shared identity/release lineage，不因后续
    root 生成而失效。

**Exit**

- 所有 offline hard gates；
- iff `ScientificClaimPlan.selected_profiles` 含 ideation，fresh-start 与 memory-shadow
  使用相同冻结输入/预算并生成 `ideation_diversity_report.json`，预注册 quality/
  diversity gates 通过；未选择时从未 admission并输出 typed N/A；
- `aa_report.json` 的 90% equivalence CI 完全位于预注册
  `[-delta_aa,+delta_aa]`，unexpected exposure difference=0；
- Pilot manipulation/utilization denominator 只含 gold eligible decisions；Pilot outcome、
  variance/ICC、power/ITT denominator 含全部 registered pairs；
- claimed-adoption/execution fidelity 100%；
- no-op/invalid/timeout 没有被删除；
- endpoint、`delta_min/delta_memory/delta_harm/delta_aa`、alpha 与 exact decision rules
  已在任何 hidden visibility 前冻结；Pilot 只能按 frozen joint-assurance rule 决定 N/
  stopping，任一 threshold 漂移必须 fresh lineage。

### Phase 7 — Confirmatory and rollout

- **PR 22:** frozen Knowledge/Evidence/Recall Input Snapshot preregistration。
- **PR 23:** confirmatory results and claim validator。
- **PR 24:** production rollout/rollback evidence and legacy trusted-path removal。

**Exit**

- held-out claim 的 evaluation-task/source-task lineage 零交集；same-task/new-seed
  claim 允许 task ID 相同但 seed/Run/Attempt/artifact/answer/gold/evaluator-private
  lineage 零交集；
- paired ITT outcome gate 和 noninferiority/robustness/efficiency gates 通过；
- confirmatory Closure Receipt 后才创建 L3/L4 assembly root；若申请 L5，等 Runtime
  release manifest/report 可读后创建新的 superseding immutable L5 root；
- protocol-scoped multi-family claim 需要至少三个预注册 families，禁止
  domain-general/universal wording；
- iff requested ceiling=`L5`，Durable Runtime 生产 gates 与 pass final validation receipt
  同时通过；L3/L4 scientific roots 不依赖 Runtime production refs；
- claim 文本与证据等级一致。

## 16. Test matrix

### Models and identity

- canonical JSON/order/timestamp exclusions；
- versioned domain/NFC/decimal/UTC golden vectors；
- every content-derived ID mutation sensitivity；
- unknown enum/extra field rejection；
- old model payload round-trip byte identity；
- Evidence Card/source citation resolution；
- content-ID CHECK 不误伤 legacy/run/activity/arm/pair operational IDs。

### Store journal, outbox, and retention

- 每个 new/legacy append 在 schema-v3 open 下恰有一个同事务 journal row；
- crash at canonical-row/journal boundary rolls back；exact retry 返回原 position；
- orphan/missing/mismatched journal 在 open-time fail closed；
- Evidence/Lifecycle typed frontier 不被 Snapshot、Recall、Outcome、outbox append 推进；
- queued receipt/work row 原子；unassigned→campaign Run/Activity Assignment→
  Completion 的 restart/duplicate scan 收敛，source Run 保持 terminal/无新 Activity；
- Campaign Admission Profile handoff 在 publish bytes、create `ACTIVE` Work-Item ref +
  `PENDING` handoff、Ledger enqueue commit、enqueue receipt + sidecar independent
  read-back、`BOUND` CAS 的每个
  seam 注入 crash；每个 prefix 恢复后恰一 ref/handoff/Work Item/receipt，零 dangling
  Ledger row、零丢失 bytes；
- source Run terminal 后、admission projector 读取 profile 前运行 aggressive GC：
  Work-Item-owned `BOUND + ACTIVE` ref 仍使 exact bytes 可读；缺失/未绑定 ref 阻止 source
  terminal barrier；
- pre-enqueue crash orphan 只有 fixed-frontier
  request-bound `DistillationEnqueueRecoveryProof=ABSENT`（echo exact Experience、Work Item
  payload digest、handoff + attempt ID/generation/fence）、旧 coordinator 已停止、higher-fence retire
  且旧 Ledger transaction 已 drain，随后在 later frontier 证明无 in-flight enqueue
  attempt 时才把旧 attempt 置为 `PROVED_ABSENT`；handoff/ref 必须仍为 `PENDING + ACTIVE`。
  随后以同 Work Item 重试会 append higher-generation/fence attempt 并可成功 `BOUND`；只有
  exact `DistillationEnqueueObligationAbandonedProof` 且 Store 已 append/read-back exact
  `abandoned_before_enqueue` receipt 才显式 `ORPHAN_ABSENT/RELEASED`；proof 有而 receipt
  缺失时 release=0/Run=`WAITING_INPUT`。
  receipt commit reply-loss 必须由 `ABANDONED_PRESENT` arm 收敛；A/B Experience、payload
  digest 或 policy/profile lineage swap 时 append/release 都为 0。
  timeout、stale frontier、old-attempt proof、open obligation 或 concurrent enqueue 下
  release=0；higher-generation retry 与旧 abandon proof 交换的 race 必须 release=0；Ledger
  commit-before-bind reply loss 由 Work Item/enqueue receipt/sidecar 独立 read-back 收敛到 `BOUND`；
- foreign owner、wrong Work Item/profile/object generation、inactive/`RELEASED` ref、
  tampered proof digest 的 queued enqueue 全部零 Ledger write；exact retry with `BOUND`
  返回原 transaction；
- enqueue reply-loss 后清空 Runtime caller cache，只从
  `distillation_enqueue_transactions_v1` read-back handoff/ref、attempt ID/generation/fence、
  original proof/transaction digests；Runtime `BOUND` CAS 必须逐字段相等。缺 sidecar、字段
  swap、later-attempt digest 或 Work Item/receipt journal gap 均不得 bind/terminal；
- source/campaign Run terminal 不释放 Work-Item root；terminal Work Completion 加
  campaign replay/audit 独立 root（或 retention expiry）后显式 release，replay-retained
  bytes 始终可读，最终零独立 root 时才可由 GC 删除；
- campaign Activity 从 `AWAITING_ASSIGNMENT` 开始且不可 claim/dispatch；assignment
  read-back + version/generation CAS 后才 READY。assignment/activation/cancel/terminal
  1,000-race 中 stale activation/foreign member dispatch=0；
- 100 concurrent admission projectors 对同一 oldest item 只能产生一个 cardinality=1
  manifest/Run/Activity/Assignment；projectors 使用不同 deployed config 时仍因 Work
  Item-pinned Admission Profile + canonical Work-Item `DriveRun` admission/run/command
  identities 收敛，same key/different spec
  只报 identity conflict；不存在 overlapping manifest 或永久 orphan Run；
- terminal validator 对 manifest exact set 证明每项一个 assignment/activity/completion、
  foreign=0、missing 不可 vacuous complete；all-completed/dead-letter/cancelled/
  runtime-failure-after-work/runtime-failure-after-closure 映射正确；
- cancellation/failure 为所有剩余 manifest slot 写 typed cancelled/dead-letter
  Completion，terminal campaign 下 assigned-incomplete=0；
- commit/cancel/fatal-failure 3-way 1,000-race：同一 control-event CAS 只选择一个
  pending closure kind；authorization-first + success 分别得到
  `TOO_LATE_COMMITTED/ALL_COMPLETED` 或保留 Completion 后
  `FAILED/RUNTIME_FAILURE_AFTER_WORK`；authorization-first + conflict 在 retry 前分别
  cancel 或 dead-letter；cancel/failure-first authorization=0，且 precedence/replay 稳定；
- grant→cancel primary pending→independent integrity failure 顺序不丢 failure：success
  保留 Completion 并 `RUNTIME_FAILURE_AFTER_WORK`，no-commit 在 retry 前 dead-letter；
- zero-dead-letter + cancelled Completion coverage settled 后、terminal CAS 前到达独立 failure，
  immutable coverage 保持不变并映射 `RUNTIME_FAILURE_AFTER_CLOSURE`；receipt missing/
  foreign/tampered、pause/quarantine/watchdog 越过 unresolved authorization、second writer
  全部拒绝；
- 两个 campaign 对同 scope expected head 的 1,000-race：恰一 atomic success，另一
  只有 journaled NO_COMMIT_CONFLICT/零 semantic write；retire auth 后 fresh-head
  reproposal 可前进，pending cancel 则先进入 CANCELLING；
- successful Batch 对 singleton Work Item 恰一 Work Disposition；no-comparator/
  not-comparable/no-candidate 不伪造 Candidate/Decision，仍与 Batch/Report/Completion
  原子完成；
- completion 唯一且 canonical Batch/Report/Disposition、authorization/Effect 可解析；
  dead-letter/cancelled terminal receipt ref/digest 可由 Runtime getter 回读并进入 release
  denominator；
- tombstoned target 永不进入 active view/index；外部 encrypted/raw payload 或
  artifact 删除/crypto-erasure 后 canonical audit envelope/journal/FKs 仍通过 integrity；
  尝试物理删除 canonical row 必须失败；canonical JSON 中发现 erasable private
  bytes 时 quarantine + release invalid，不能用 tombstone 假装已删除。
- retention crash matrix 覆盖 lifecycle retraction、external erasure receipt、每个
  affected index invalidation、Tombstone append 与 publication barrier；任一 prefix
  不得发布新 snapshot/index，恢复后 exact refs/digests 可回读且旧 Recall Input blocked；
- `begin_erasure` commit-after-reply-loss exact retry 返回原 Intent/retraction/journal/
  receipt，即使 lifecycle head 已有合法 descendant；same incident different bytes 拒绝；
- open Intent 与 Snapshot/index/RecallInput/Context/distillation commit 各做 1,000 次 race：
  retention-first 时 publication semantic write=0；Context-first 只允许那一次已线性化
  actor exposure，后续全 blocked；proof/frontier/tombstone set tamper 全拒绝；
- reachable closure golden vectors 覆盖 memory→Evidence Link→Experience→Observation/
  Artifact、episodic bundle、index receipt→artifact/object generation；只撤回间接 source
  也必须使旧 Snapshot/Recall Input blocked，direct-memory-only anti-join 测试必须失败；
- Distillation plan/grant 后、atomic commit 前 Retention Intent 赢得时，只允许
  `RETENTION_REVOKED` conflict+journal，Batch/Knowledge/Report/Completion=0；retire 后从
  clean inputs 重提，旧 plan 永久无权；
- 同一 transaction 同时观察到 lifecycle stale 与 reachable retention revoked 时，golden/
  race/reply-loss replay 必须始终得到同一个 `RETENTION_REVOKED` conflict ID/receipt；
  head-delta arm canonical null，exact retry 只能返回原 journal position；

### Distillation and lifecycle

- generic/no-action rejected；
- missing/tampered or nested-vs-canonical Hypothesis/Attempt/Observation/
  Verification/Intervention/Trial Provenance mismatch rejected；
- duplicate attempt/import/retry does not change support；
- paired/multi-seed effect and guardrails；
- true contradiction, scope split, temporal update；
- `promoted_contested` replacement 的 event/relation/head/decision 原子顺序；
- transition legality and supersession cycle rejection；
- family stable across scope variants；expected-head lifecycle CAS race；
- idempotence/concurrent writers/atomic failure points；
- private evaluator and self-evidence exclusion。

### Snapshot and index

- unrelated Experience does not change frozen snapshot；
- concurrent evidence append does not change captured exact membership；
- EvidenceSnapshotCommitReceipt + getter read-back 同 snapshot ID/payload digest/original
  journal position；exact capture retry 不推进 position；
- capture commit 后丢 reply、随后新增可见 Evidence，再以相同
  `capture_operation_id+request_digest` retry 仍返回原 members/frontier/position；different
  request conflict，不得把 later Evidence 吸入原 operation；
- eligible lifecycle change creates new snapshot；
- selected scope-variant head uniqueness；
- Knowledge Snapshot ID excludes Retrieval/index identity；Recall Input binds it；
- evaluation contamination check；
- lexical/semantic exact rebuild and confirmatory final-card identity；
- model/revision/dimension/policy change creates new index identity；
- failed index attempt 不可进入 Recall Input；成功 retry 得到唯一 ready identity；
- corrupted/stale index typed behavior；
- `KnowledgeCandidate` 在 normal/confirmatory Recall Context return count 永远为 0。
- tombstone 后旧 frozen Snapshot/index/Recall Input 必须 blocked，不能从 pre-erasure
  artifact 或 cache 复活；新建 clean inputs 后才恢复。

### Retrieval

- hard filter executes before rank；
- `DecisionPointRetriever.propose()` 只返回 closed
  `DecisionRecallContextProposal | DecisionRecallBlockedProposal`；每个 blocked reason 的
  typed evidence golden vector 可被 Runtime artifact getter 重算，free-form/私密/exception
  evidence 拒绝；
- retention blocked proposal 精确绑定同一 Recall Input ID/digest、frontier、tombstone-set
  digest、sorted blocked targets；替换任一 target、顺序未 canonicalize、foreign input/check
  或 forged proposal/artifact digest 都失败且不发布 Context/card；
- full Evaluation Contract/private paths never enter request/actor process；
- Decision Intent exact artifact/generation/arm binding，以及 Runtime-admission-proof
  验证的 memory profile/assignment manifest/recall requirement；proof swap/tamper fail；
- task/domain/dataset/model/source/contract/decision/knob/version；
- active/provisional/contested profile；
- one-family diversity；
- counterevidence and abstention；
- stable tie break；
- Evidence Card tagged-union vectors：semantic/procedure 必含 family/scope/lifecycle，
  episodic 必含 snapshot/member/bundle/verification 且 memory/lifecycle canonical null；
- Recall Context ID golden vectors 区分 healthy empty、degraded zero-card、fallback policy、
  retention frontier/tombstone set 与 rendered identity；
- pinned-tokenizer complete rendered-section budgets；
- no generation call online；
- gold Precision/Recall/nDCG/abstention。

### Utilization and runtime

- previous feedback enters next request；
- arm-specific feedback isolation；
- every card disposition exactly once；
- blocked/not-requested/cancelled-before-recall/failed-before-recall/empty/degraded/
  actor-failed/cancelled zero-card outcome exactly once；
- `REGISTERED_NOT_REQUESTED` Intent 才接受 not_requested/null-context/zero-card；
  `REQUIRED` Intent 伪造 not_requested 必须失败，Outcome caller 无 profile override；
- REQUIRED Intent 在 Context 前 cancel/fail 必须用 matching Runtime closure proof 和
  exact pre-recall source/decision mapping；无 Recall Input/Context/retriever/planner call；
- blocked Outcome 必须由持久化/read-back `DecisionRecallBlockedProof` 驱动；覆盖 foreign
  Intent/input proof、在两个各自有效 blocked proposals 间 swap ref/digest/evidence、forged
  artifact/proposal digest，以及 Outcome proposal/authorization/canonical Outcome proof pair
  不一致，均由 Store strict getter 逐字段拒绝且零 Ledger write；
- pre-recall closure alias matrix 覆盖：cancelled 仅接受 byte-equal `CANCEL_EVENT`，failed
  仅接受 byte-equal `RUNTIME_FAILURE`；foreign/forged event、ref/digest 拆对、两个各自有效
  closure events 互换，以及任何其他 source status 携带 pre-recall fields 均拒绝；
- `prepare_required_decision`/`commit_required_decision_context` 拒绝 registered-not-requested Intent；no-memory path 只向
  planner 传 typed `NoDecisionMemoryBinding`，不伪造 Context；Intervention/Attempt v1
  lineage 保持 canonical `"off"`；registered-not-requested 在 actor 前 cancel/fail 不调用
  planner，仍提交 source `not_requested` 的 exact closure Outcome；
- Context append vs pre-Context closure、normal Outcome vs cancel/failure 各 1,000-race，
  phase/authorization/receipt read-back 收敛且 late writes=0；
- transition/authority illegal cross-product（closure Context、admission Outcome、normal
  Intent 等）全部零 write/no phase advance；
- Intent proposal→REGISTERING→Ledger append/no-commit→OPEN/retired 的每个 crash seam 和
  cancel/failure race 收敛；terminal enumerator 不漏 Ledger-backed Intent，也不为 retired
  ghost registration 伪造 Outcome；
- `REGISTERING` 与 `CONTEXT_COMMITTING|OUTCOME_COMMITTING` 都必须由 exact
  authorization-bound reconciliation deadline 覆盖；reply loss/control crash/overdue fire
  后 success/no-commit reconcile 会取消 deadline，且不得留下永久 registration 或重复授权；
- APPEND_INTENT/CONTEXT/OUTCOME 的 journaled no-commit 均验证 generic authorization
  kind/ID/digest；每个分支都断言 Intent、Context、`decision_recall_items_v2`、Outcome、
  disposition child-row 新增数全为 0，尤其 APPEND_CONTEXT 不得遗留孤立 recall item；
- post-Context closure 对每张 card 恰有一个 Runtime-only
  `not_considered_cancelled|not_considered_actor_failed`，empty 为零；normal actor 使用它们
  或 closure 混用 partial actor dispositions 必须失败；
- `outcome_reason_code` 覆盖 closed source/reason matrix；blocked corruption/policy/private/
  identity/contamination/retention 不碰撞；未调用 actor 的 executed actor/prompt fields 全
  null，调用路径才允许 exact execution receipts；
- REQUIRED 与 registered-no-memory 各覆盖 actor timeout/crash/unparseable-before-envelope：
  pre-invocation planner-input binding digest 仍可验证，response envelope 不得伪造；成功
  response 的 echoed binding、governance digest、foreign Context/input swap/tamper 全拒绝；
- nonempty REQUIRED Context 下 model crash/malformed 只能由 `RUNTIME_CLOSURE` 写
  actor_failed + 每卡 `not_considered_actor_failed`；NORMAL actor_failed、closure-auth
  completed、foreign model/rejection/closure receipt 均拒绝；
- adopted target within card/catalog；
- citation→proposal→config→manifest→Verification；
- existing InterventionProposal/Record v1 payload and proposal digest unchanged；
- rejected/no-op 仍持久化；malformed/unparseable actor output 映射 actor_failed，
  policy/preflight denial 映射 rejected，不存在 standalone invalid status；
- retrieval failure visibly degraded；
- confirmatory pair never dropped；
- no shared mutable policy/gate state；
- ideation fresh-start path、budget parity、quality noninferiority 和 exploration
  diversity artifact。

### Procedure/reference/legacy

- only verified trajectory compiles；
- unknown/tampered tool/procedure rejected；
- procedure step still requires normal Runtime Effect authorization/receipt；
- success/early-stop/rollback semantics；
- reference reverse provenance；
- prompt-injection text has no authority；
- legacy episode/fact excluded；
- working state is not Knowledge。

## 17. Acceptance commands

以下本地测试入口是稳定 Interface：

```bash
python -m pytest \
  tests/test_experience/test_memory_models.py \
  tests/test_experience/test_knowledge_store_contract.py \
  tests/test_experience/test_distillation_outbox.py \
  tests/test_experience/test_knowledge_distillation.py \
  tests/test_experience/test_knowledge_lifecycle.py \
  tests/test_experience/test_memory_retention.py \
  tests/test_experience/test_evidence_snapshot.py \
  tests/test_experience/test_knowledge_snapshot.py \
  tests/test_experience/test_recall_input_snapshot.py \
  tests/test_experience/test_decision_intent.py \
  tests/test_experience/test_decision_point_retrieval.py \
  tests/test_experience/test_recall_utilization.py

python -m pytest \
  tests/test_runtime/test_decision_recall_integration.py \
  tests/test_runtime/test_adaptive_experiment.py \
  tests/test_runtime/test_improvement_cycle.py \
  tests/test_runtime/test_experience_adapter.py \
  tests/test_experience/test_legacy_memory_isolation.py
```

正式 hidden acceptance/release 的**唯一规范命令序列**是
[Memory Effectiveness Evaluation §13](memory-effectiveness-evaluation.md#13-commands)；
本计划不维护第二份容易漂移的 CLI。实现必须逐字落实其中的 pre-visibility
`ScientificClaimPlan`、canonical release-lineage ID、Hidden Partition Authority、
signed registry trust anchor/two frontiers、atomic exposure token、shared/stage manifests、
offline/selected-ideation/A/A/Pilot、independent `PilotGateReceipt`、deterministic
confirmatory selection、ceiling-specific immutable root、assembly，以及 signed
`acceptance_validation_receipt.json`。不得使用旧 `shared.json/stages/_stages` 路径、
self-signed pilot gate、未带 trust anchor 的任意 SQLite，或无条件运行 ideation。

runner/validator exit-code、失败后仍须 assembly、immutable lineage/release paths 和
final-validation receipt 规则同样以该节为唯一规范；科学负结果不得被 transport code
改标为 operational failure。

完整回归入口：

```bash
python -m pytest
```

所有测试命令必须非交互并支持 clean temporary root。
## 18. Rollout and rollback

### Rollout

1. revision 3 reader + writer disabled；
2. shadow distillation；
3. shadow lexical retrieval；
4. shadow hybrid retrieval；
5. active `intervention` Decision Point on development tasks；
6. frozen-memory Pilot；
7. confirmatory；
8. production profile；
9. other Decision Points；
10. legacy trusted-path removal。

每步记录 policy/snapshot/corpus digest，不能在同一个 experiment 内变更。

### Rollback triggers

- critical false promotion；
- forbidden/superseded/private memory return；
- citation/action/execution fidelity <100%；
- prompt injection execution 或 namespace leakage；
- index identity/replay failure；
- outcome negative-transfer 超过 margin；
- p95/p99 或 token/cost hard limit；
- migration integrity failure。

Rollback 关闭 active injection，保留 immutable v3 audit records，重建或隔离 derived
index，并回到 `record_only` 或 `legacy_recall`。不得删除失败证据。

## 19. Acceptance artifacts

每次 release 生成：

```text
benchmark/results/memory/
  _lineages/<lineage-id>/<stage>/<campaign-id>/stage_artifacts...
  releases/<release-id>/
    acceptance_manifest.json
    stage_index.json
    requirements_report.json
    trace_report.json
    snapshot_report.json
    writer_report.json
    retrieval_report.json
    utilization_report.json
    robustness_report.json
    efficiency_report.json
    task_sensitivity_report.json
    ideation_diversity_report.json
    aa_report.json
    pilot_gate_receipt.json
    runtime_release_refs.json
    pilot_report.json
    confirmatory_report.json
    power_analysis.json
    claim_report.json
    raw_refs.json
```

上述是 assembly 完成时的 pre-validation 文件面；canonical report/envelope 始终存在，
不适用时必须写
`{status:not_applicable, reason, status_provenance, data:null}` 的 content-addressed
typed envelope，不能缺文件或伪造零值。该 N/A 规则明确不含
`acceptance_validation_receipt.json`：它只能由独立 validator 在 exit `0|10|20` 时
exact-once 新增，形成 validated release surface；exit 70 时保持缺失/unvalidated，
assembler 禁止生成 placeholder。Pilot 与 confirmatory 各有独立 stage-tagged
aggregate；跨 stage requirement 引用两份 provenance，不覆盖成同名报告。

runner 只写 immutable lineage/stage/campaign shard，assembler 只写新的 release-ID
directory；existing different bytes fail closed，绝不能覆盖较低 ceiling/superseded root。
每个 shard 共享 release-lineage/shared-identity digest，但
不要求预知后来生成的 root digest，并必须匹配自己的 stage-manifest digest 和独立
campaign ID。每个 executed stage 必须先有 append-only Admission Receipt；支持非 invalid
claim 时还必须有 terminal Closure Receipt。若 signed frontier 含 open/unclosed admission，
freezer/assembler 必须把 exact open set/frontier/reason 写入 claim=none 的 audit-only
invalid root，不得省略或伪造 Closure。`assemble_acceptance` 从 root 指定的 signed
Registry Authority checkpoint、lineage/global two frontiers 枚举 exact set，验证目标 ceiling 所需 stage、
全部失败/invalid/aborted admissions，以及 offline/selected ideation/A/A/Pilot/
confirmatory reserve/actual 的完整适用维度 overlap matrix，再生成 release-root files。validator 只接受
release root；未运行的可选 stage 才可按 registry rule 在 `stage_index.json` typed N/A。

`requirements_report.json` 必须严格实现验收协议 §2.1/§12：62 IDs 恰一行，closed
`pass|fail|invalid|not_applicable`，per-ID minimum level/applicability，以及
`stage|release_assembly` provenance tagged union。query-macro check 使用 sample count +
per-query distribution refs，不伪造 pooled numerator/denominator；N/A 行 checks 为空并
带合法 reason/assembly provenance。缺/重复/未知 requirement、required N/A、refs 不可
解析、registry sibling 未枚举或 identity mismatch 都使总状态 `invalid`，不能重跑到
有利结果后只选择成功 shard。

required stage 的 `failed|aborted|invalid` 使用 evaluation §12
`StageTerminalOverrideCheck.terminal_closure`；audit-only open admission 使用
`unclosed_at_frontier`，其 Closure refs 必须 null并绑定 signed Admission、authority
checkpoint、两 frontier/prefix 与 enumerated-absence proof；`insufficient_power` 使用 typed
assurance check。不得挑 partial metric checks或伪造 Closure。独立 validator 对排除 receipt 自身的 artifact-set 重算后，
由 Claim Plan pin 的 Validation Authority 写 signed `acceptance_validation_receipt.json`。
只有 signature valid、`final_status=pass` 且 highest claim 与发布目标 exact-match 才算已
验收；valid-fail/invalid receipt 只证明审计完成，不授权发布/L5。

## 20. Definition of Done

本交付只有在以下事实全部由当前代码和 acceptance artifacts 证明时完成：

- governing design 的每条 `VRM-*` invariant 都有测试和 requirement report；
- schema revision 3 迁移、原子提交、rollback runbook 和旧 payload byte identity
  全部验证；
- versioned ID domains、canonical projection、golden vectors 和 monotonic ledger
  positions 全部验证；
- schema-v3 所有 new/legacy append 与唯一 commit-journal row 同事务，typed
  Evidence/Lifecycle frontier 在 exact replay 与 snapshot/Recall append 下稳定；
- queued receipt/Work Item 可由 restart scan 到达；campaign Activity 在 Assignment
  proof CAS 前保持 `AWAITING_ASSIGNMENT`/不可 dispatch；exact manifest membership、
  completion/dead-letter/cancelled 可审计，terminal campaign 下 assigned-incomplete=0，
  duplicate Runtime invocation 收敛；
- 每个 queued Work Item 在 source terminal 前有 exact `BOUND` handoff 与
  Work-Item-owned `ACTIVE` Campaign Admission Profile ref；Artifact Store 是唯一 byte-GC
  authority，orphan recovery 与 terminal Completion/replay-retention release 均有
  crash-safe read-back 证明；
- Distiller 只读取 Store-validated canonical Verified Evidence Bundles；nested
  Experience mismatch 必须拒绝；
- 当前单-analysis KnowledgeGate 不再供应 active path；
- duplicate support 不涨 evidence strength，family/scope variant、contradiction、
  `promoted_contested` replacement 和 lifecycle expected-head CAS 正确；
- Evidence/Knowledge/Recall Input Snapshot 身份分离、无 hash cycle 且 confirmatory
  可冻结；
- intervention Decision Intent 使用 sanitized contract view、预分配 decision slot、
  admission-proof-backed Memory Governance Binding、最大三张 cards 和 exact policy；
- production semantic candidate path 使用真实 pinned embedding；canonical ledger
  DB 不含 FTS/vector tables，confirmatory exact index 可重建；
- hash/non-semantic test Adapter 在 production/evaluation semantic assembly 为 0；
- 每个 Decision Intent 都有 terminal Recall Decision Outcome，per-card disposition
  和 citation-to-config lineage 100%；registered not-requested 绕过 retriever/context，
  REQUIRED pre-context cancel/fail 只用 verified closure status/proof；
- Phase A InterventionProposal/Record v1 payload bytes 和 digest domains 未改变；
- Procedure/Reference/Working/Episodic/Semantic planes 在类型、持久化和 prompt 中
  保持分离；
- legacy episode/consolidated fact 不能进入 trusted active/confirmatory recall；
- offline writer/retrieval/utilization/robustness/efficiency hard gates 全通过；
- active ideation profile 的 fresh-start quality/diversity guardrail 已通过；
- Pilot 通过 manipulation gate，并完成不截断的 clustered variance/ICC sensitivity
  与 joint-assurance power analysis；independent Pilot Gate 绑定 pre-root prerequisite
  assessments，final requirements assembly 再生成 CA003，二者无 hash/self-dependency；
- confirmatory paired ITT、noninferiority、negative-transfer、安全和成本 gate 全通过；
- ScientificClaimPlan/requirement registry/claim matrix、signed Registry/Validation trust
  anchors、atomic exposure/no-visibility、all-hidden-stage non-overlap 与 deterministic
  reserve selection 全部通过 crash/race/signature tests；
- final `acceptance_validation_receipt.json` 签名有效、绑定 pre-validation artifact set、
  `final_status=pass` 且 highest claim exact-match；
- production release 的 Runtime manifest/report refs 可 read-back、digest match，
  required Runtime requirement IDs 全通过且 identity compatible；
- root README、docs indexes、CLI help 和 release claim 与实际证据一致；
- 全量测试通过，worktree 内没有未解释的 generated acceptance output。
