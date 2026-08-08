# Context-Aware Tool Use 实施与验收计划

**Status:** Ready for implementation

**Audience:** 负责 Agent、MetaChain、skills、Runtime、评测和发布的维护者

**Scope:** 把现有“阶段级静态工具列表 + Agent 内直接执行”迁移为可回放的
Tool Interaction、按需工具暴露、Runtime-governed Effect、完整评测与逐阶段发布

**Owner:** AI-Researcher maintainers

**Last updated:** 2026-07-31

**Governing design:**
[Context-Aware Tool Use and Governed Tool Effects](../design/context-aware-tool-use.md)

**Related governing designs:**
[Durable Research Runtime and Stage Continuation](../design/durable-research-runtime.md),
[Experience-Driven Research Loop](../design/experience-driven-research-loop.md),
and [Verified Research Memory](../design/verified-research-memory.md)

## 1. 交付目标

本计划完成时，AI-Researcher 必须具备以下生产能力，而不是只有一个离线
tool-search demo：

1. 每个 model turn 都能显式产生 `DIRECT | CLARIFY | DISCOVER | EXECUTE`
   之一；`COMPLETE | HANDOFF` 是独立控制结果，不是外部工具。
2. 每次决策先做 stage/auth/config/environment/data-flow/risk/budget 硬过滤，
   再做相关性排序；retriever 永远不能授权执行。
3. 小工具集在 schema 预算内直接暴露；只有超过预算，或公开 SelectionPolicy 中
   冻结的 development/baseline narrowing override 命中时才 progressive discovery；
   evaluator-only gold labels 永远不进入 decision plane。
4. 工具集合随已提交 ToolFeedback、失败、证据缺口、subgoal 和 availability
   变化重新选择。
5. 所有 model/tool 调用最终都成为现有 Long-Task Runtime 所有的 Effect；每次
   dispatch 有独立 Physical Invocation、Budget Envelope reservation、receipt、
   reconciliation 和 Durable Transition。
6. 工具返回是 typed、bounded、artifact-backed `ToolFeedback`；不再依赖字符串
   `Result` 判断成功，也不与 Experiment Attempt 的 Observation 混名。
7. 每个决策、候选、暴露集合、model proposal、授权结果、工具尝试、失败和
   feedback 都可重放，并进入正确的 cache/provenance identity。
8. static、hard-filter、dense、hybrid、trajectory 五个 arm 能在同一个工具使用
   Evaluation Contract、模型和预算下比较。
9. 通过 shadow、只读 canary、危险工具 canary 和 durable rollout 后，删除生产
   直接 callable dispatch、control-as-tool、全局覆盖式注册、重复 cache/trace
   authority 与 MD5 检索 fallback。

文档、接口类或通过若干 loader unit tests 不等于交付。只有本计划的 Definition
of Done 全部有当前代码、测试、运行 artifact 和 acceptance manifest 证据时，
才能把 governing design 标记为 Accepted。

## 2. 基线、前置条件与并行关系

### 2.1 当前基线必须重新冻结

Phase 0 在任何行为修改前生成 content-addressed baseline manifest，至少记录：

- git revision、依赖 lock/fingerprint、Python、OS 和 tokenizer 版本；
- 两个 entry flow 的 Agent/role/stage 列表；
- 每个 Agent 的 callable 名称、顺序、完整 provider schema 和 token 数；
- `tool_choice`、SiliconFlow 等 provider-specific effective choice、parallel flag；
- 完整 model request、model response、tool proposal、call args、返回、异常、handoff、
  context patch 和 stage artifact digests；
- model/tool call 数、input/schema/output tokens、p50/p95 latency 和 cost；
- cache key、hit/miss 和 cached transcript digest；
- 至少一组 provided-idea 和一组 reference-ideation fixture；
- 当前 45 个 decorator tool、SKILL manifest tool 和 Agent-bound wrapper 的清单与
  重叠/缺失报告。

当前调研测得 Agent 每轮约 264--1,637 schema tokens，只作为计划依据。发布比较
必须使用 Phase 0 自动生成的 raw measurement，而不是复制文档数字。

### 2.2 与 Durable Runtime 的依赖关系

工具选择不等待整个 Durable Runtime 完成，但执行声明有严格前置：

| Tool-use phase | 可并行开始 | Durable Runtime 前置 | 允许的声明 |
| --- | --- | --- | --- |
| T0 trace baseline | 立即 | 无 | “现有调用可观测” |
| T1 canonical catalog | 立即 | 无 | “工具身份/schema 可校验” |
| T2 pure ToolInteraction | 立即 | 无 | “决策可确定性测试” |
| T3 shadow integration | 立即 | 无 | “反事实选择对 active path 无影响” |
| T4 read-only enforcement | T0--T3 后 | Runtime Phase 2 的 effect journal、reservation、fencing、receipt/reconcile | “按需暴露已启用；每次 read-only call 也是 governed Effect” |
| T5 hybrid/trajectory selection | T4 后 | 同 T4；committed ToolFeedback 必须来自真实 tool Effect 或 tool preparation rejection | “动态重选已启用” |
| T6 execution/output convergence | T5 后 | Runtime Phase 2 + execution Adapter contract suites | “全部工具输出 typed，legacy output bridge 归零” |
| T7 all-stage migration | Runtime Phase 5/6 配合 | native stage Adapters 与 entry migration | “两个 flow 共用目标路径” |
| T8 acceptance/deletion | Runtime release gates 配合 | authoritative journal、rollout/rollback | 完整生产声明 |

T3 以前的 `LegacyMetaChainToolAdapter` 只用于 legacy/shadow active lane，仍是带 typed
trace 的 direct-call migration bridge，任何发布说明都不得称其 durable。进入 T4 后，
active adaptive profile 禁止 direct callable：旧 binding 只能作为真实 Runtime Effect
后的 `LegacyToolExecutionAdapter`，由 Runtime 产生 Effect/Physical Invocation/fence/
receipt/settlement；Adapter 可暂时把输出标为 `LEGACY_UNTYPED`，但不拥有执行或重试
语义。不得合成伪 Effect ID。

### 2.3 不可绕过的先决修复

T3 之前必须完成：

- 所有内部工具尝试都进入 trace，包括 unknown tool、JSON parse、schema、异常、
  denied 和 unavailable；
- `ToolModule` 不再无条件记录 `success=True`；
- `AgentModule` cache identity 绑定真实 active tool configuration；
- trace 明确区分 control action、model Effect、tool Effect 和 flow-level helper；
- 日志/trace 写入失败不能静默伪造一次成功调用；
- provider request schema token 由实际序列化内容自动计算。

T4 之前必须完成：

- 每个 active Agent 静态列表都能编译为 canonical catalog + static policy；
- 同名不同 schema/binding 冲突全部显式解决；
- adaptive provider profile 通过 optional tool-use 和 canonical control tests；
- `DIRECT/CLARIFY` 有 stage completion/wait 语义，不能依赖“没有 tool call 就 break”。

T4 active enforcement 之前必须完成 Durable Runtime plan 的 effect journal、Physical Invocation、
reservation、fencing、retry ownership、artifact commit 与 Adapter contract。

### 2.4 与 Verified Research Memory 的并行关系

基础 ToolInteraction 不依赖 memory 上线：`decision_memory` 是 closed optional
input，无 recall 时写显式 no-recall identity。T0--T5 的 memory case 可用
deterministic fixture 完成，不得因此声称生产 Recall Decision Outcome 已交付。
普通 memory-off/non-memory stage 使用 no-decision-memory；registered control arm
仍传 preallocated Decision Intent + `source_status=NOT_REQUESTED`、null Recall
Input/Context、zero-card/zero-token binding，并写 terminal outcome，不能借 `None`
逃出 denominator，也不能误记为 blocked。

生产启用 memory-informed tool decision 之前，Verified Research Memory plan 至少要
完成对应实现阶段（当前计划 Phase 3）的 typed Decision Intent、Recall Input
Snapshot、Recall Context、per-card disposition 和 durable Recall Decision Outcome
Store contracts。集成还必须证明：

- Tool Decision Record 先不可变提交；模型 disposition 只是 untrusted draft；Runtime
  绑定实际 decision/authorization 后提交 Recall Decision Outcome，再由幂等
  `MemoryToolDecisionLinked` event 关联；
- memory-informed `EXECUTE` 的 guarded `DISPATCHED` 必须等待 outcome link；
  crash/replay 不产生孤儿、重复逻辑 outcome 或未记录的外部行动；
- empty/degraded recall 不扩大候选或触发 global fallback；
- Evidence Card 永远不能改变 hard eligibility、approval 或 Runtime authorization；
- outcome evaluator 使用 opaque trial identity，评分后由独立 manipulation audit
  连接 Tool Decision/Recall Decision Outcome，不把 actor memory 暴露给 evaluator。
- 每个 memory-governed model Effect 预分配新的 logical decision slot/Decision Intent；
  `DIRECT/CLARIFY/DISCOVER/EXECUTE/REJECTED` 各自关闭当前 Intent。discovery 后、
  clarification resume 后和 committed ToolFeedback 后的 model Effect 使用新的 child
  Intent，并可绑定 parent outcome digest；不能复用旧 Intent。
- 下一 model request 从 committed artifacts 重建，删除前一 turn rendered Recall
  Context bytes，只携带 bounded trajectory facts 和 parent outcome digest；新 turn
  重新 recall，或用注册的 `source_status=not_requested` zero-card/null-context control
  outcome。

若 memory Phase 3 未就绪，rollout 继续支持 no-recall ToolInteraction；不得保留一条
没有 terminal Recall Decision Outcome 的临时 production recall 通道。

## 3. Dependency rule 与目标文件

### 3.1 目标依赖方向

```text
Agent stage policy data
          ↓
inno.tool_use.ToolInteraction (pure)
          ↓ directives only
runtime.adapters.tool_interaction
          ↓ EffectSpec
LongTaskRuntime private control/executor protocol
          ↓ authorized Physical Invocation
runtime ToolExecutionAdapter
          ↓ raw evidence
LongTaskRuntime receipt selection/settlement
          ↓ committed ToolFeedback input
inno.tool_use.ToolInteraction
```

旁路但不混入 per-turn Interface：Run admission/Snapshot builder 调用独立
`CapabilityCatalogCompiler`，把 legacy/skill fragments 编译为 pinned catalog；Runtime
Adapter 验证 Selection Bundle artifacts 并构造 read-only ToolInteraction
Implementation。二者都在 `advance()` 前完成。

禁止依赖：

- `inno.tool_use` 不得 import `litellm`, Docker socket, Browser environment,
  mutable Registry, SQLite store 或 concrete tool Implementation；
- Agent factory 不得在目标状态 import concrete tools 来决定暴露集合；
- retriever/ranker 不得 import ToolExecutionAdapter；
- ToolExecutionAdapter 不得 import selection/ranking policy；
- CLI/Web 不得 import ToolInteraction、Runtime private authorization、worker、store
  或 execution Adapter；
- evaluator 不得通过 ToolInteraction/Agent 写 Verification Record；
- actor/decision package 不得 import evaluator-label schema 或 private corpus namespace；
- `flowcache.py` 不得成为 external Effect execution 或 retry authority。

新增 dependency test 应解析 import graph，并在 CI 中拒绝上述反向边。

### 3.2 新文件

```text
research_agent/inno/tool_use/
  __init__.py
  interaction.py
  canonical.py
  catalog.py
  policy.py
  data_flow.py
  bundle.py
  views.py
  selection.py
  feedback.py
  protocol.py
  tracing.py
  adapters/
    __init__.py
    catalog_legacy.py
    catalog_skill.py
    provider_native.py
    provider_prompt.py

research_agent/runtime/
  _tool_authorization.py
  adapters/
    tool_interaction.py
    tool_execution.py
    tool_shadow.py

research_agent/inno/evals/
  tool_use.py

benchmark/tool_use/
  __init__.py
  schemas.py
  contracts/tool-use-v1.yaml
  contracts/release-criteria-v1.yaml
  cases/actor/
  cases/evaluator_private/
  fixtures/
  run.py
  analyze.py
  validate_manifest.py

tests/test_tool_use/
  test_interaction_contract.py
  test_catalog_contract.py
  test_policy.py
  test_data_flow.py
  test_selection_bundle.py
  test_views.py
  test_selection.py
  test_feedback.py
  test_protocol_contract.py
  test_shadow_inertness.py
  test_meta_chain_integration.py
  test_cache_identity.py
  test_dependency_rules.py
  test_evaluator_label_isolation.py
  test_trace_causality.py
  test_acceptance_manifest.py
  test_rollout_rollback.py

tests/test_runtime/
  test_tool_authorization.py
  test_tool_effect_adapters.py
  test_tool_effect_faults.py
```

类型放在拥有该 Seam 的文件中，不新建 catch-all `models.py`、`interfaces.py` 或
`utils.py`。

### 3.3 现有文件修改图

| File/Module | 实施动作 |
| --- | --- |
| `research_agent/inno/core.py` | T0 完整 trace；T3 接 migration Adapter；T4 从 Prepared model Effect 构造 request；T6 删除 direct callable execution |
| `research_agent/inno/types.py` | 增加迁移期 policy/profile refs；最终收窄 `Agent.functions` 与 string `Result` 职责 |
| `research_agent/inno/registry.py` | T1 只作为 legacy binding source；禁止覆盖式 identity resolution；T8 删除 metadata authority |
| `research_agent/inno/tools/__init__.py` | T1 停止为 catalog 做 eager import；T8 删除 recursive production import |
| `research_agent/inno/skills/base.py` | manifest 指向 canonical descriptor/schema digest，不维持独立可漂移 schema |
| `research_agent/inno/skills/loader.py` | 保留 manifest-only scan，输出 catalog fragment，实际校验 required config metadata |
| `research_agent/inno/skills/registry.py` | 停止把 skill tool 注入全局 Registry；迁移为 catalog source，最终删除旧 search Interface |
| `research_agent/inno/skills/search.py` | 删除 MD5 fallback；可复用逻辑迁入 private selection Implementation；T8 删除浅 Interface |
| `research_agent/inno/workflow/flowcache.py` | trace/cache identity 完整化；停止独立工具执行和结果 cache authority |
| `research_agent/inno/workflow/cache_identity.py` | 增加 catalog/policy/protocol/toolset/trajectory/Adapter digests |
| `research_agent/inno/evals/trace.py` | closed typed tool-decision/execution projection；不再遗漏 internal call |
| `research_agent/inno/evals/metrics.py` | 加 tool-use diagnostic metrics；end-state Verification 仍是 primary |
| `research_agent/runtime/context.py` | Snapshot 绑定 catalog/policy/protocol/Adapter bundle digests；构造 actor-safe scope 与 Runtime-only authorization envelope，禁止 transitive private identity 泄漏 |
| `research_agent/run_infer_plan.py` | 两个 flow 逐阶段改用 policy ref 与共同 Adapter |
| `research_agent/run_infer_idea.py` | 同上 |
| `research_agent/inno/agents/inno_agent/*.py` | callable selection 迁移为 stage capability/completion policy；移除 control-as-tool |

### 3.4 Trace 与评测 ownership

| Component | 唯一责任 | 禁止 |
| --- | --- | --- |
| `tool_use/tracing.py` | canonical Tool Decision/event payload schemas 和 canonical digest | 写 journal、拼最终评测 report |
| Runtime journal/store | append-only mutation authority、顺序、linkage | 改写 Tool Decision Record、计算研究结论 |
| `inno/evals/trace.py` | journal -> `ResearchRunTrace` 只读 projection Adapter | 成为第二事实源 |
| `inno/evals/tool_use.py` / `metrics.py` | 从 frozen trace + label artifact 纯计算 metrics | 读取 actor mutable state、写 Verification |
| `benchmark/tool_use/run.py` | 装载 manifest、分配 Run、保存 raw artifacts | 内嵌另一套 metric 公式 |
| `benchmark/tool_use/analyze.py` | 调用 pinned metric Implementation、CI 和 gate evaluator | 接受临时阈值覆盖 frozen criteria |

## 4. Normative data contracts

所有持久化模型使用 Pydantic v2、`extra="forbid"`、`frozen=True`、显式
`schema_version`、closed enum 与 canonical JSON。时间用 UTC；digest 使用 SHA-256。
未知 enum/schema version 必须 fail closed。

`frozen=True` 不是深不可变。所有 JSON schema、canonical args、policy map 和 provider
projection 在进入 domain model 时必须转换为递归 immutable `CanonicalJsonValue`
（object key 排序、array 保序、拒绝 NaN/Infinity/duplicate key），digest 计算自同一组
canonical bytes。Provider Adapter 只能从该值生成一次性 wire dict，不能把可变 dict
保存回 record。

所有 content digest 使用同一个 `canonical.py` Implementation：覆盖 schema version
和全部语义字段，排除自身 `*_digest`、artifact 存储位置、签名包装与非语义写入时间；
ref/digest pair 必须在使用前验证。禁止每个 Module 自己拼 JSON 或把 digest 字段递归
包含进自身。

### 4.1 CapabilityDescriptor

`catalog.py` 至少定义：

```python
class CapabilityDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"]
    capability_id: str             # namespace/name@version
    source_kind: Literal["legacy_registry", "skill_manifest", "builtin"]
    source_ref: str
    source_digest: str

    provider_name_hint: str
    summary: str
    action: str
    object: str
    when_to_use: tuple[str, ...]
    when_not_to_use: tuple[str, ...]
    positive_examples: tuple[str, ...]
    negative_examples: tuple[str, ...]
    confused_with: tuple[str, ...]

    input_schema: CanonicalJsonObject
    output_schema: CanonicalJsonObject
    input_schema_digest: str
    output_schema_digest: str
    descriptor_digest: str

    stage_tags: tuple[str, ...]
    required_config: tuple[str, ...]
    required_auth_scopes: tuple[str, ...]
    execution_binding: ExecutionBinding
    effect_policy: CapabilityEffectPolicy
    data_policy: CapabilityDataPolicy
    output_policy: CapabilityOutputPolicy
    dependency_policy: CapabilityDependencyPolicy
    cost_hint: CapabilityCostHint | None
```

`descriptor_digest` 覆盖全部行为相关字段，但不包含 live availability、secret、
近期成功率等运行时观测。非权威历史统计可存于 derived ranking feature artifact，
必须有时间窗和来源，不得改变 hard authorization。

### 4.2 CapabilityEffectPolicy

至少表达：

```python
class CapabilityEffectPolicy(BaseModel):
    schema_version: Literal["1"]
    side_effect: Literal["none", "read", "write", "destructive", "external_publish"]
    execution_kind: Literal["in_process", "subprocess", "docker", "browser"]
    idempotency: Literal[
        "pure", "idempotent", "queryable", "reexecutable", "non_reconcilable"
    ]
    checkpoint_policy: Literal[
        "RESUMABLE", "RESTARTABLE", "RECONCILE_ONLY", "NON_RESUMABLE"
    ]
    cache_policy: Literal["never", "exact_receipt", "content_addressed_read"]
    parallel_safety: Literal["serial", "independent_read", "stateful"]
    timeout_seconds: int
    worst_case_reservation: WorstCaseUsage
    approval_class: str | None


class WorstCaseUsage(BaseModel):
    schema_version: Literal["1"]
    model_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    wall_time_ms: int
    cpu_time_ms: int
    gpu_time_ms: int
    network_bytes: int
    output_bytes: int
    cost_microunits: int


class ExecutionBinding(BaseModel):
    schema_version: Literal["1"]
    operation_id: str
    adapter_kind: Literal["in_process", "subprocess", "docker", "browser"]
    binding_ref: ArtifactRef
    binding_digest: str
    adapter_contract_version: str
    adapter_contract_digest: str


class CapabilityDataPolicy(BaseModel):
    schema_version: Literal["1"]
    accepted_input_classes: tuple[str, ...]
    output_class: str
    allowed_destination_classes: tuple[str, ...]
    network_access: Literal["none", "restricted", "open_world"]
    evaluator_private_allowed: Literal[False]
    policy_digest: str


class CapabilityOutputPolicy(BaseModel):
    schema_version: Literal["1"]
    allowed_content_types: tuple[str, ...]
    max_raw_bytes: int
    max_inline_bytes: int
    max_model_tokens: int
    artifact_required_above_bytes: int
    structural_redaction_policy_digest: str
    projection_renderer_digest: str
    policy_digest: str


class CapabilityDependencyPolicy(BaseModel):
    schema_version: Literal["1"]
    prerequisite_capability_ids: tuple[str, ...]
    successor_capability_ids: tuple[str, ...]
    incompatible_capability_ids: tuple[str, ...]
    required_evidence_kinds: tuple[str, ...]
    policy_digest: str


class CapabilityCostHint(BaseModel):
    schema_version: Literal["1"]
    measurement_window: str
    source_artifact_ref: ArtifactRef
    source_artifact_digest: str
    sample_count: int
    p50_wall_time_ms: int
    p95_wall_time_ms: int
    p50_cost_microunits: int


class CatalogSourceRef(BaseModel):
    schema_version: Literal["1"]
    source_kind: Literal["legacy_registry", "skill_manifest", "builtin"]
    source_ref: ArtifactRef
    source_digest: str
    adapter_contract_digest: str
```

Model Effect validator 要求 `(model_calls, tool_calls) == (1, 0)`；Tool Effect request
要求 `(0, 1)`；所有 usage 数值非负，currency 使用整数 microunits，不用 float。

Catalog compilation 验证 effect policy 与 execution Adapter contract 兼容。例如
`non_reconcilable` 外部写不能声明 `RESTARTABLE`，stateful Browser 不能声明
`independent_read`，超出 in-process bounded limit 的工具必须用 subprocess/container。

### 4.3 Capability Catalog artifact

```python
class CapabilityCatalog(BaseModel):
    schema_version: Literal["1"]
    catalog_id: str
    descriptors: tuple[CapabilityDescriptor, ...]  # sorted by capability_id
    source_fragments: tuple[CatalogSourceRef, ...]
    compiler_version: str
    compiler_digest: str
    catalog_digest: str
```

编译命令的目标 Interface：

```text
python -m research_agent.inno.tool_use.catalog check
python -m research_agent.inno.tool_use.catalog build --output ARTIFACT_DIR
python -m research_agent.inno.tool_use.catalog diff OLD NEW
```

`check` 必须在不调用任何 Tool Implementation 的情况下发现 identity/schema/policy
冲突。需要环境 wrapper 才能生成 executable schema 的 legacy tool，使用显式 fixture
binding；不能通过递归 import 全库并吞掉异常来“检查”。

### 4.4 SelectionPolicy and SelectionBundle artifacts

Policy 是 content-addressed data，由一个 pinned interpreter 解释，不是任意 Python
subclass plugin。建议 v1 schema：

```yaml
schema_version: "1"
policy_id: researcher/adaptive-v1
mode: adaptive                    # static | shadow | adaptive
selection_bundle_ref: artifact://tool-selection/bundle-v1.json
selection_bundle_digest: "..."
stage_allowlists:
  prepare: ["..."]
  coding_plan: ["..."]
frozen_protocol_denies:
  - side_effect: write
  - side_effect: destructive
schema_budget:
  absolute_tokens: 2048
  max_context_fraction: 0.02
small_set_bypass:
  enabled: true
narrowing_overrides:
  - override_id: coding/file-vs-web-v1
    capability_ids: ["builtin/file.read@1", "builtin/web.search@1"]
    approved_development_artifact_ref: artifact://tool-evals/dev-confusion-v1.json
    approved_development_artifact_digest: "..."
selection:
  strategy: hybrid_trajectory_v1
  dense_degradation: lexical_only # lexical_only | expand | clarify | wait | fail
  low_confidence: expand_then_clarify
  max_discovery_steps: 2
  max_model_corrections: 1
reretrieve_on:
  - tool_feedback
  - typed_failure
  - evidence_gap
  - subgoal_change
  - availability_change
fallback:
  scope: original_stage_allowlist # never global registry
  only_if_within_schema_budget: true
```

`2048` 和 `0.02` 是初始 compatibility profile 值，依据当前最大约 1,637 tokens
留出控制 schema 余量；不是跨模型结论。T0 必须测量各 provider tokenizer，并在
adaptive 结果揭晓前冻结正式 policy。任何调整产生新 policy digest 和新 Research
Run。

`SelectionBundle` 关闭所有“代码默认值没进 digest”的后门：

```python
class IndexedDescriptorBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"]
    capability_id: str
    descriptor_digest: str


class DenseRuntimeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"]
    inference_runtime_version: str
    inference_runtime_digest: str
    kernel_abi: str
    platform_abi: str
    cpu_feature_mask: str
    thread_count: Literal[1]
    device: Literal["cpu"]
    vector_dtype: Literal["float32"]
    score_encoding: Literal["signed_int64_fixed_point"]
    score_scale: int
    rounding_mode: Literal["half_even"]
    profile_digest: str


class SelectionBundle(BaseModel):
    schema_version: Literal["1"]
    bundle_id: str
    interpreter_version: str
    interpreter_digest: str
    tokenizer_ref: ArtifactRef
    tokenizer_digest: str
    schema_estimator_version: str
    schema_estimator_digest: str
    lexical_analyzer_config: CanonicalJsonObject
    lexical_analyzer_digest: str
    embedding_model_ref: ArtifactRef | None
    embedding_model_revision: str | None
    embedding_model_digest: str | None
    dense_index_ref: ArtifactRef | None
    dense_index_digest: str | None
    indexed_catalog_digest: str | None
    indexed_descriptors: tuple[IndexedDescriptorBinding, ...]
    indexed_corpus_digest: str | None
    feature_input_projection_digest: str | None
    dense_runtime_profile: DenseRuntimeProfile | None
    normalization_digest: str
    fusion_config: CanonicalJsonObject
    fusion_digest: str
    confidence_thresholds: CanonicalJsonObject
    renderer_version: str
    renderer_digest: str
    stable_tie_break: Literal["capability_id"]
    bundle_digest: str
```

static/lexical-only policy 对 optional dense refs/profile 使用显式 `None`，对
`indexed_descriptors` 使用显式空 tuple，不能运行时偷用本地模型。
`NarrowingOverride` 只能引用 adaptive 结果揭晓前冻结的 development/baseline
artifact，且 schema 禁止 case ID、expected/forbidden、milestone、minefield、answer、
treatment 字段。Run spec、ToolInteraction request、cache、Tool Decision Record 和
acceptance manifest 全部绑定 `bundle_digest`。

dense-enabled bundle 的 admission validator 必须证明：

- `indexed_catalog_digest == active catalog_digest`；
- `indexed_descriptors` 按 capability ID 排序，和 Catalog 的
  `(capability_id, descriptor_digest)` 集合完全相等；
- `indexed_corpus_digest` 覆盖该 ordered tuple、feature/input projection 和 embedding
  model identity；
- 当前 worker fingerprint 精确匹配 `DenseRuntimeProfile`；
- query/document score 在 threshold/fusion 前按 profile 转为 canonical signed-int64
  fixed point。

V1 不允许 partial dense index。陈旧、catalog-swap、descriptor 缺失或 runtime
fingerprint 不匹配均产生 typed bundle rejection，并按 pinned policy 显式
lexical-only/wait/fail；不能把未索引 capability 静默丢掉。clean-process、不同 worker
和允许的 CPU 主机上必须有 byte-golden tests；GPU、并行归约和未固定 kernel 禁止进入
active selection。

### 4.5 ExecutionPolicy artifact

至少包含：

- stage/role 到 capability class 的 allow/deny；
- principal/auth scope 与 required config 规则；
- source/destination data classification 和 egress matrix；
- destructive/external-publish approval requirement；
- per-capability argument constraints；
- allowed execution Adapter bundle；
- idempotency/reconcile/cache requirements；
- blocked-diagnostic identity/summary/reason/remediation visibility rules；
- ToolFeedback inline/artifact/token/redaction policy；
- maximum tool calls, tool result tokens, wall time and cost within the enclosing
  Budget Envelope；
- availability attestation TTL 与 stale behavior。

SelectionPolicy 可以缩小候选，ExecutionPolicy 才拥有 hard allow/deny 语义。两者
都被 Run pin，但 final authorization 必须重新解释 ExecutionPolicy 与 exact args。

```python
class ExecutionPolicy(BaseModel):
    schema_version: Literal["1"]
    policy_id: str
    stage_role_rules: tuple[StageRoleRule, ...]
    principal_scope_rules: tuple[PrincipalScopeRule, ...]
    required_config_rules: tuple[RequiredConfigRule, ...]
    data_flow_matrix: tuple[DataFlowRule, ...]
    approval_rules: tuple[ApprovalRule, ...]
    argument_constraints: tuple[ArgumentConstraint, ...]
    allowed_adapter_bundle_digest: str
    effect_contract_rules: tuple[EffectContractRule, ...]
    diagnostic_visibility_rules: tuple[DiagnosticVisibilityRule, ...]
    output_policy: RuntimeToolOutputPolicy
    max_tool_calls: int
    max_result_tokens: int
    max_wall_time_ms: int
    max_cost_microunits: int
    availability_ttl_seconds: int
    stale_behavior: Literal["refresh", "wait", "deny"]
    policy_digest: str


class StageRoleRule(BaseModel):
    schema_version: Literal["1"]
    rule_id: str
    stage_ids: tuple[str, ...]
    role_ids: tuple[str, ...]
    capability_ids: tuple[str, ...]
    side_effect_classes: tuple[str, ...]
    disposition: Literal["ALLOW", "DENY"]


class PrincipalScopeRule(BaseModel):
    schema_version: Literal["1"]
    rule_id: str
    principal_classes: tuple[str, ...]
    capability_ids: tuple[str, ...]
    required_scope_names: tuple[str, ...]


class RequiredConfigRule(BaseModel):
    schema_version: Literal["1"]
    rule_id: str
    capability_ids: tuple[str, ...]
    required_config_names: tuple[str, ...]


class DataFlowRule(BaseModel):
    schema_version: Literal["1"]
    rule_id: str
    source_classes: tuple[str, ...]
    destination_classes: tuple[str, ...]
    capability_ids: tuple[str, ...]
    disposition: Literal["ALLOW", "DENY"]


class ApprovalRule(BaseModel):
    schema_version: Literal["1"]
    approval_class: str
    capability_ids: tuple[str, ...]
    principal_classes: tuple[str, ...]
    ttl_seconds: int
    exact_argument_binding_required: Literal[True]


class ArgumentConstraint(BaseModel):
    schema_version: Literal["1"]
    constraint_id: str
    capability_id: str
    json_pointer: str
    operator: Literal["EQ", "IN", "NOT_IN", "PREFIX", "MAX", "MIN", "MATCH_ENUM"]
    operand: CanonicalJsonValue


class EffectContractRule(BaseModel):
    schema_version: Literal["1"]
    capability_ids: tuple[str, ...]
    allowed_idempotency: tuple[str, ...]
    allowed_checkpoint_policies: tuple[str, ...]
    allowed_cache_policies: tuple[str, ...]


BlockedDiagnosticReason = Literal[
    "AUTH_MISSING", "CONFIG_MISSING", "ENVIRONMENT_MISSING",
    "PROVIDER_DEGRADED", "APPROVAL_REQUIRED", "BUDGET_NOT_ADMITTED",
]

DiagnosticRemediationClass = Literal[
    "CLARIFY", "WAIT", "REQUEST_APPROVAL", "REQUEST_BUDGET",
    "RETRY_PROVIDER",
]


class DiagnosticRemediationRule(BaseModel):
    schema_version: Literal["1"]
    blocked_reason: BlockedDiagnosticReason
    remediation_class: DiagnosticRemediationClass
    public_text: str


class DiagnosticVisibilityRule(BaseModel):
    schema_version: Literal["1"]
    rule_id: str
    stage_ids: tuple[str, ...]
    role_ids: tuple[str, ...]
    principal_classes: tuple[str, ...]
    capability_ids: tuple[str, ...]
    blocked_reasons: tuple[BlockedDiagnosticReason, ...]
    render_profile: Literal["IDENTITY_SUMMARY_REASON_REMEDIATION"]
    remediation_rules: tuple[DiagnosticRemediationRule, ...]
    disposition: Literal["ALLOW", "DENY"]


class RuntimeToolOutputPolicy(BaseModel):
    schema_version: Literal["1"]
    max_inline_bytes: int
    max_model_tokens: int
    artifact_required_above_bytes: int
    structural_redaction_policy_digest: str
    semantic_summary: Literal["forbidden", "separate_effect"]
    renderer_digest: str
```

上述 nested types 都是 closed、frozen models，按 canonical ID 排序；不允许
`dict[str, Any]` policy escape hatch。validator 至少检查 deny-overrides-allow、egress
闭包、approval class 存在、argument constraint 可判定、Adapter/effect contract 一致。
`DiagnosticVisibilityRule` 也是 `policy_digest` 的 canonical 内容；无匹配规则、多个
冲突匹配或 `DENY` 一律归为 `HIDDEN_DENY`。只有唯一 `ALLOW` 才可投影规则钉死的
namespaced identity、bounded summary、closed reason、remediation class/public text 和
descriptor digest；auth/config/scope 值、provider alias、schema、binding 与参数永不进入
diagnostic bytes。remediation 文本不得由模型、descriptor 或异常字符串临时生成。

#### 4.5.1 Effective policy algebra

`policy.py` 只实现一个 pinned、纯 `normalize_effective_policy()`；selection eligibility
和 Runtime final authorization 都调用它。前者不给 exact arguments/可变 dispatch state，
只读取 argument-independent projection；后者以 exact canonical arguments、最新
Availability/Budget/Fence 再调用并独占授权提交权。两个调用共享 canonical rule matching、
reason precedence 和 normalized-policy digest，禁止各写一套 if/else。

Normative 合成规则：

| 输入约束 | Effective policy |
| --- | --- |
| 任一 matching `DENY`、descriptor incompatibility、frozen/workflow deny | deny 胜出 |
| descriptor stage、Selection stage allowlist、Execution stage/role/capability/data allow | 取交集；缺 applicable Execution `ALLOW` 默认 deny |
| required scopes/config/approval/evidence/preconditions | 取并集，policy 只能增加要求 |
| allowed destination/content type/Adapter/effect/idempotency/cache class | 取交集 |
| max bytes/tokens/calls/wall time/cost | 取所有 applicable ceiling 的最小值 |
| network/output exposure | 取最严格值 |
| SelectionPolicy narrowing | 只能从 effective eligible set 删除，不能添加或授权 |

`CapabilityDescriptor.stage_tags` 不得为空；显式 `"*"` 表示 stage-neutral。stage 必须
同时满足 descriptor、SelectionPolicy 和 matching ExecutionPolicy `ALLOW`。缺 rule、
空 intersection、无法判定或冲突都 fail closed。统一 reason precedence 为：

```text
integrity/schema
-> explicit deny
-> stage/role
-> data flow
-> Adapter/effect contract
-> scope/config
-> approval
-> availability
-> budget
-> dependency/trajectory
-> exact argument constraint
```

Run-admission `ToolConfigurationValidator` 还要拒绝 descriptor 要求无法被当前
ExecutionPolicy 表达、required approval class 无定义、以及
descriptor/Adapter/effect class intersection 为空的 bundle；Catalog compiler 本身仍
只验证 descriptor/source 内部一致性，不读取 Run policy。
validator 输出一个 canonical `normalized_tool_configuration_digest`，覆盖 catalog、
Selection/Execution policy、Selection Bundle、provider protocol、Adapter bundle、
normalized policy algebra 与兼容性矩阵。Run spec、Research Context binding、actor
request、outer Runtime Effect authorization 和 acceptance manifest 都绑定该 digest；
Catalog compiler 不能生成或冒充它。
contract tests 使用冲突矩阵证明 selection 与 final authorization 对共同输入得到相同
normalized policy/reason；final authorization 只能因 exact args 或更新后的 mutable state
增加更晚的 denial reason，不能重排或覆盖既有约束。

### 4.6 AvailabilitySnapshot

```python
class AvailabilitySnapshot(BaseModel):
    schema_version: Literal["1"]
    generation: int
    observed_at: datetime
    expires_at: datetime
    capability_status: tuple[CapabilityAvailability, ...]
    attestation_refs: tuple[ArtifactRef, ...]
    freshness: Literal["FRESH", "STALE"]
    validated_at_event_seq: int
    digest: str
```

```python
class CapabilityAvailability(BaseModel):
    schema_version: Literal["1"]
    capability_id: str
    status: Literal[
        "AVAILABLE", "AUTH_MISSING", "CONFIG_MISSING", "ENVIRONMENT_MISSING",
        "PROVIDER_DEGRADED", "DISABLED"
    ]
    reason_codes: tuple[str, ...]
    available_scope_names: tuple[str, ...]
    available_config_names: tuple[str, ...]
    provider_generation: str | None
    attestation_ref: ArtifactRef | None
    attestation_digest: str | None
```

状态是 `AVAILABLE | AUTH_MISSING | CONFIG_MISSING | ENVIRONMENT_MISSING |
PROVIDER_DEGRADED | DISABLED`。不存 secret 值。dispatch 时过期必须刷新或进入
typed wait，不能假定仍可用。Runtime 在调用 pure `advance()` 前计算并提交
`freshness`；ToolInteraction 不读取 live clock。final authorization 再检查当前状态。

#### 4.6.1 Progressive-disclosure wire views

`views.py` 实现 governing design 的 closed `CatalogEntryView`、`CatalogView` 和
`InspectView`。共同 validator 要求：

```python
EligibilityDisposition = Literal[
    "EXECUTABLE_ELIGIBLE", "BLOCKED_DIAGNOSTIC", "HIDDEN_DENY"
]


class BlockedCapabilityHintView(BaseModel):
    schema_version: Literal["1"]
    capability_id: str
    summary: str
    blocked_reason: Literal[
        "AUTH_MISSING", "CONFIG_MISSING", "ENVIRONMENT_MISSING",
        "PROVIDER_DEGRADED", "APPROVAL_REQUIRED", "BUDGET_NOT_ADMITTED"
    ]
    remediation_class: str
    descriptor_digest: str


class CatalogView(BaseModel):
    schema_version: Literal["1"]
    entries: tuple[CatalogEntryView, ...]
    blocked_hints: tuple[BlockedCapabilityHintView, ...]
    executable_token_count: int
    diagnostic_token_count: int
    catalog_digest: str
    selection_policy_digest: str
    renderer_digest: str
    view_digest: str
```

policy normalizer 必须先把每个 capability 分类为三种 disposition。permanent policy/
data/confidentiality/frozen-protocol deny 只能是 `HIDDEN_DENY`，在 actor view 中完全
消失。只有可补救的 auth/config/environment/provider/approval/budget 缺口可进入
`BLOCKED_DIAGNOSTIC`。executable 与 diagnostic 两个 lane 各自有独立 budget、stable
rank、trace 和 digest；execution ranker 只能排序 `EXECUTABLE_ELIGIBLE`，diagnostic
ranker 只能排序 approved hints。blocked hint 不含 schema、provider alias、binding、
arguments 或 auth scope，Inspect/Execute/fallback 都只接受 `entries` 成员。命中 hint
只能产生 clarify/wait/remediation，永远不能准备 Effect 或被提升为 executable。

- entry 按 capability ID stable sort；schema/examples/dependency 保持 declared order；
- 每个 view 绑定 catalog、SelectionPolicy、SelectionBundle renderer、descriptor/schema
  digests、exact tokenizer count 和自身 digest；
- Catalog 的 executable entries 只含 identity/summary/availability/risk/full-schema-token estimate；Inspect
  才含一个 capability 的 full schema/examples/preconditions/dependencies；
- `DISCOVER` 输入绑定旧 view/query digest，输出下一 model Effect 的新 view/toolset
  digest；不能在同一 prepared Effect 中热换 schema；
- Catalog/Inspect/Execute 只是 internal view phases，不注册为 model-callable tools。

#### 4.6.2 Actor identity、Runtime envelope 与两步续回合

`interaction.py` 的 actor request 与 `runtime/adapters/tool_interaction.py` 的运行时
authority 必须是两个不相互嵌套的 closed model：

```python
class ActorTurnScope(BaseModel):
    schema_version: Literal["1"]
    actor_request_scope_digest: str
    actor_workflow_view_digest: str
    actor_continuation_view_digest: str
    stage_name: str
    actor_stage_contract_view_digest: str
    actor_decision_contract_view_digest: str
    actor_interaction_key: str
    decision_epoch: int


class RuntimeAuthorizationEnvelope(BaseModel):
    schema_version: Literal["1"]
    run_id: str
    run_spec_digest: str
    full_evaluation_contract_digest: str
    activity_id: str
    activity_generation: int
    expected_event_seq: int
    fencing_epoch: int
    decision_intent_id: str | None
    decision_intent_digest: str | None
    actor_request_digest: str
    actor_decision_slot_digest: str | None
```

`ToolInteractionRequest` 只含 `ActorTurnScope`、actor-visible Research Context/
Decision Input/Decision Memory、pinned catalog/policies/bundle、availability、budget、
rollout 和 trigger。它禁止 Run/Activity/fence/full private Evaluation Contract、actual
Decision Intent ID、evaluator/treatment metadata。`DecisionMemoryBinding` 使用
`actor_decision_slot_digest` 与 optional parent outcome actor-projection digest；actual
Intent 只存在 envelope。Runtime journal 以 append-only link 把 actor request/directive
digest 与 envelope 绑定。actor transcript cache 只绑定 actor scope；Effect identity、
execution authorization/cache 绑定 actor digest + envelope，禁止跨 Run 复用 Effect。

closed continuation types 至少包括：

```python
ToolInteractionTrigger = (
    BeginInteraction | ModelEffectSettled |
    ModelPreparationRejected | ModelDispatchAuthorizationRejected |
    ToolEffectsSettled | ToolPreparationRejected |
    ToolDispatchAuthorizationRejected |
    InputResolutionCommitted | DecisionTurnInputsCommitted
)

ToolDirective = (
    PrepareEffect | CommitDecisionAndRequestNextTurnInputs |
    CommitStageProposal | WaitForInput | RejectActivity
)

class NextTurnInputSpec(BaseModel):
    schema_version: Literal["1"]
    actor_interaction_key: str
    next_decision_epoch: int
    cause_digest: str
    committed_trajectory_digest: str
    decision_input_projection_spec_digest: str
    catalog_or_toolset_view_digest: str
    decision_point: DecisionPoint | None
    memory_profile_digest: str | None
    parent_recall_outcome_required: bool
    spec_digest: str
```

`DISCOVER`、ToolFeedback、input resolution、model protocol correction、tool
preparation rejection 和 tool dispatch rejection 后，需要 model continuation 时的
第一次 `advance()` 只能返回
`CommitDecisionAndRequestNextTurnInputs`：关闭旧 Tool Decision/Recall Outcome 并描述
下一轮输入，不创建 Effect。Runtime 提交/link 旧 outcome，生成 bounded Decision
Input，预分配 child Intent/actor slot，重新 recall 或创建 NOT_REQUESTED binding，并
删除旧 rendered Recall bytes；然后以 `DecisionTurnInputsCommitted` 第二次调用
`advance()`。只有第二次调用可 `PrepareEffect(model)`。任一中间 crash 只补 missing
suffix，不能复用旧 Intent/Recall 或重复创建 model Effect。

`NextTurnInputSpec.cause` 与 trigger 有 closed applicability matrix；例如 discovery 只能
使用 `DISCOVERY`，tool rejection 只能使用对应 rejection cause。Model Effect rejection
不适用此立即续回合规则：它按下一段关闭当前 Intent 并 wait/reject，只有后来真正的新
committed state 才能从 InputResolution/availability resolution 进入两步协议。

Runtime 构造 `source_status=NOT_REQUESTED` actor binding 前，必须 read-back actual
Decision Intent 的 admission-proof-backed Memory Governance Binding 并确认
`recall_requirement=REGISTERED_NOT_REQUESTED`；`REQUIRED` Intent、model proposal 或
ToolInteraction 均无权把它降成 not requested。

model 与 tool rejection 是不同 closed branches。`ModelPreparationRejected` 表示
exact model request/provider/data-flow/budget 在 Effect 创建前被拒；
`ModelDispatchAuthorizationRejected` 保留已创建 model Effect/Invocation、
not-executed receipt/reason 与 settlement。二者都不构造 ToolFeedback，只能按 pinned
policy 关闭当前 Intent 后 WaitForInput/RejectActivity；若 operator/input/provider 的新
committed state 允许再试，必须走 next-turn two-call protocol 并使用新 Intent，不能作为
hidden Adapter retry。

#### 4.6.3 Data classification、provenance 与 egress

`data_flow.py` 定义 closed、canonical types：

```python
class DataClassification(BaseModel):
    schema_version: Literal["1"]
    confidentiality: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
    compartments: tuple[Literal["EVALUATOR_PRIVATE", "CREDENTIAL_SECRET"], ...]
    integrity: Literal["VALIDATED", "UNTRUSTED_EXTERNAL"]


DataDestinationClass = Literal[
    "LOCAL_PROCESS", "TRUSTED_MODEL_PROVIDER", "RESTRICTED_NETWORK", "OPEN_WORLD"
]


class DataProvenanceBinding(BaseModel):
    schema_version: Literal["1"]
    source_kind: Literal[
        "DECISION_INPUT", "RECALL_CARD", "TOOL_FEEDBACK", "ARTIFACT",
        "USER_INPUT", "TRUSTED_CONSTANT"
    ]
    source_ref: ArtifactRef | None
    source_digest: str
    classification: DataClassification
    declassification_receipt_digests: tuple[str, ...]


class ArgumentSourceClaim(BaseModel):
    schema_version: Literal["1"]
    json_pointer: str
    claimed_source_digests: tuple[str, ...]


class DeclassificationReceipt(BaseModel):
    schema_version: Literal["1"]
    source_digest: str
    output_digest: str
    source_classification: DataClassification
    output_classification: DataClassification
    removed_field_paths: tuple[str, ...]
    policy_digest: str
    trusted_transform_effect_id: str
    receipt_digest: str
```

join 算法固定为 confidentiality 取最大级别、compartments set-union + stable sort、
任一 untrusted 输入令 integrity 为 `UNTRUSTED_EXTERNAL`。model 的 per-pointer claim
只能增加来源，不能删来源或降级；所有自由生成参数默认继承当前 actor-visible
Decision Input、Recall、ToolFeedback 与 artifact 的并集。只有 trusted deterministic
transform Effect 的 verified derivation/declassification receipt 可收窄，且
`EVALUATOR_PRIVATE`/`CREDENTIAL_SECRET` 不得 declassify 到 actor/open-world。

`DecisionInputView`、`DecisionMemoryBinding`、`ToolCallProposal`、raw receipt、artifact、
`CommittedToolReceiptView` 和 `ToolFeedback` 都带 classification/provenance digest。
`ModelEffectSpec` 与 `ToolEffectRequest` 都必须绑定 destination class、effective input
classification、input/argument provenance digest、declassification receipt digests、
execution-policy digest 和由 Runtime 重算的 `data_flow_digest`。model provider、semantic
summarizer、renderer/truncator 与 tool-to-tool forwarding 都走相同 egress matrix；不能
把摘要/截断当成洗白边界。Runtime 在 Effect preparation 和原子 dispatch transaction
各重算一次，未通过前不得发送 provider/tool bytes；output classification 是 effective
input 与 descriptor output class 的 join。

### 4.7 Tool Decision Record

`tracing.py` 的记录必须覆盖：

- request/turn/trajectory/catalog/selection-policy/Selection-Bundle/
  availability/budget digests；
- actor decision-slot、Recall Input Snapshot content、optional Recall Context actor
  projection digests，或显式 no-recall；actual Decision Intent/Run/Activity/private
  contract identity 只由 Runtime envelope/link event 保存；
- active/shadow lane；
- candidate universe；
- 每个 capability 的 hard-filter disposition/reason；
- query artifact/digest；
- lexical/dense/fused ranks、score 与 ranker digest；
- exposed ordered capabilities、provider aliases、schema digests/tokens；
- model proposal interaction/control、arg digest；
- proposal validation disposition；
- correction/discovery counters；
- resulting interaction/control digest，`EXECUTE` 另含 exact capability 与
  canonical-argument digests；
- redaction policy digest。

每次 `advance()` 恰好生成一个 step-level Tool Decision Record。它不包含因果上稍后
才知道的 directive、authorization、Effect、Physical Invocation 或 memory outcome
ID。后续分别由 `ToolDirectiveEmitted`、`ToolAuthorizationRecorded`、
`ModelPreparationRejected`、`ModelDispatchAuthorizationRejected`、
`ToolPreparationRejected`、`ToolDispatchAuthorizationRejected`、`ToolEffectLinked`、
普通 invocation/receipt events 和
`MemoryToolDecisionLinked` append-only 关联；trace 只是 join projection，不能回写
原 record。所有集合 canonical sort；所有有语义的 wire order 单独保存，不依赖 map
insertion order。

### 4.8 ToolFeedback

`feedback.py` 按 governing design 的 closed status 生成 bounded view。full output
先完成 digest、artifact commit、malware/content policy 与 redaction，再构造模型
视图。摘要失败不能丢失 raw receipt；按 pinned policy使用结构化截断或 wait/fail。

Runtime Adapter 先构造 immutable `CommittedToolReceiptView`，再交给 pure
ToolInteraction。需要语义摘要时另建受预算 Model Effect；不得在 `feedback.py`
隐式调用模型或读取 artifact。closed status 是：

```text
OK | EMPTY | RETRY_EXHAUSTED | PERMANENT_FAILURE | CONFIRMED_NOT_EXECUTED
LEGACY_UNTYPED
DENIED | UNAVAILABLE | BUDGET_NOT_ADMITTED | APPROVAL_REQUIRED
```

前两行中的 Effect-backed status 必须有 Effect ID、Physical Invocation ID、selected
receipt、classification/provenance digest 和 settled usage；其中
`RETRY_EXHAUSTED` 只在 Runtime 已耗尽其唯一 retry policy 后生成，并绑定
`runtime_retry_disposition=EXHAUSTED`。Adapter 的中间 `retryable` 事实不直接进入
ToolFeedback。`CONFIRMED_NOT_EXECUTED` 还必须有 closed
`dispatch_rejection_id/reason`、Adapter 未进入证明及 reservation release/settlement；它
保留已有 Effect/Invocation lineage，并由 `ToolDispatchAuthorizationRejected` 触发。
最后一行必须有 `ToolPreparationRejected` ID，且 Effect ID、Physical
Invocation、artifact output、settled usage 均为空。closed validator 保证二者恰有其一，
并校验 `NOT_APPLICABLE | EXHAUSTED | NOT_RETRYABLE` retry disposition 与 status
组合。

`LEGACY_UNTYPED` 只允许迁移期，并在 T8 前归零。每个 legacy tool 必须有 fixture
将已知 success/error/empty shapes 映射为 typed evidence；未知 shape 不能默认为
成功。

## 5. Interface 与 MetaChain 迁移桥

### 5.1 目标 Interface

`interaction.py` 公开给 Runtime Activity Adapter 的唯一入口：

```python
class ToolInteraction(Protocol):
    def advance(self, request: ToolInteractionRequest) -> ToolDirective: ...
```

contract tests 通过同一个 Interface 测 static、shadow、hybrid 和 trajectory policy。
不公开 `search() / inspect() / authorize() / execute()` 给 Agent 或应用 caller。
`interaction.py` 必须逐字段实现 governing design 的 bounded `DecisionInputView`、
actor-safe `DecisionMemoryBinding`、`ActorTurnScope`、single `PrepareEffect`、
`CommitDecisionAndRequestNextTurnInputs`、`NextTurnInputSpec`、
`DecisionTurnInputsCommitted`、`ModelEffectSpec`、`ToolEffectRequest`、
`ModelPreparationRejected`、`ModelDispatchAuthorizationRejected`、
`ToolPreparationRejected`、`ToolDispatchAuthorizationRejected` 和 acyclic digest order；不得以
`dict[str, Any]` 或 pass-through kwargs 代替这些 contracts。

`RuntimeAuthorizationEnvelope` 只能定义/持久化在 Runtime side。dependency/serialization
tests 禁止它或其中任一 Run/Activity/fence/private-contract/actual-Intent 字段出现在
`ToolInteractionRequest`、provider bytes、actor turn contract、Tool Decision Record 或
actor cache key。

Runtime Activity Adapter 在进入循环前解析并验证 Selection Bundle，把 tokenizer/
ranker/index/renderer 作为 read-only constructed dependencies 注入 ToolInteraction
Implementation；`advance()` 期间不得 lazy-load、联网或读取 mutable process cache。

### 5.2 迁移期 caller-first Adapter

为了不一次重写 `MetaChain.run_async()`，T3 新增 private
`LegacyMetaChainToolAdapter`：

```python
class LegacyMetaChainToolAdapter:
    def open(self, request: LegacyInteractionOpen) -> LegacyInteractionSession: ...


class LegacyInteractionSession:
    @property
    def active_cache_identity(self) -> dict[str, Any]: ...

    def prepare_turn(
        self,
        active_agent: Agent,
        history: list[dict],
        turn_index: int,
    ) -> LegacyPreparedTurn: ...

    def resolve_turn(
        self,
        prepared: LegacyPreparedTurn,
        model_message: Message,
        context_variables: dict,
    ) -> LegacyResolvedTurn: ...
```

它是短生命周期 Adapter，不持久化 Python closure。durable record 只保存 canonical
ID、artifact ref、schema/policy/Adapter digest 和 closed data type。replay 时重新
构造 Adapter。

T3 `AgentModule` 的 caller 变化应限制为：创建 Adapter/session、把 active cache
identity 传给 `CacheIdentity`、把 session 交给 `MetaChain`。当前 Agent factory 和
`run_infer_*` 不需要在同一个 PR 改写。

### 5.3 Shadow parity contract

`legacy-v1` profile 必须复用当前 callable schema 生成、排序、provider-specific
tool choice、parallel flag、message conversion、return conversion、context patch 和
handoff。`shadow-v1` 不增加 mode-specific synchronous serialization 或 Run-journal
event。active model request artifact 提交后，独立 non-causal audit projector 从该
immutable artifact 派生 bounded shadow-outbox ref，写入不递增 Run event sequence 的
audit namespace。独立 worker 随后做 selection-only replay；active path 不等待
projector/worker，也不在 critical path 运行 ranker。
Projector 以 committed request artifact cursor 扫描并 read-back，shadow job ID 由
request digest + shadow policy digest 派生；crash 后补扫、重复通知和重复 claim 均只
产生一个 logical shadow record，cursor/outbox 永不写回 active journal。

Golden assertion：同一 fixture 在 `legacy-v1` 与 `shadow-v1` 下，除 shadow
audit projection/outbox/result 外，下列 active 内容逐字节一致，Run event sequence 与
active Budget Envelope 不变：

- system/user/history messages；
- provider-visible tool schema 和顺序；
- effective `tool_choice` 与 `parallel_tool_calls`；
- model request/response digest；
- actual tool/control calls、args、返回和顺序；
- context patch、handoff 和 stage result；
- active cache identity/hit；
- active Effect/Physical Invocation（durable path 上线后）；
- total provider calls。

Shadow failure 记录 `SHADOW_SKIPPED | SHADOW_FAILED`，不能让 active Activity 失败。
production selection-only shadow 禁止 remote ranker 和 counterfactual model call。
shadow 使用隔离 worker/resource quota；其可能的资源争用不宣称为零，而由正式结果前
冻结的 p50/p95 active-latency overhead SLO 约束。
需要完整 DIRECT/EXECUTE 反事实时启动独立 replay Research Run，使用独立 budget、
journal、cache/namespace 与 recorded-read/isolated deterministic tool fixtures；不
重复 live irreversible Effect，结果不回写 active Run。

### 5.4 Enforced profile progression

固定 profile：

```text
legacy-v1
  -> shadow-v1
  -> dynamic-required-v1   # 只缩 capability；保留 legacy control closure；tool 经 Runtime Effect
  -> dynamic-auto-v1       # typed interaction/control；允许 DIRECT/CLARIFY
  -> durable-v1            # typed output/Adapters 收敛，LEGACY_UNTYPED=0
```

这些名字是 immutable artifact 实例，不是 Python subclass：

```python
class ToolUseProfile(BaseModel):
    schema_version: Literal["1"]
    profile_id: str
    selection_mode: Literal["legacy", "static", "shadow", "adaptive"]
    selection_policy_ref: ArtifactRef
    selection_policy_digest: str
    selection_bundle_ref: ArtifactRef
    selection_bundle_digest: str
    provider_protocol_ref: ArtifactRef
    provider_protocol_digest: str
    control_mode: Literal["legacy_tools", "typed"]
    execution_mode: Literal["legacy_callable", "durable_effect"]
    shadow_mode: Literal["off", "selection_outbox"]
    fallback_scope: Literal["original_stage_allowlist", "none"]
    profile_digest: str
```

Profile validator 强制 `selection_mode=adaptive -> execution_mode=durable_effect`。
`legacy_callable` 只允许 `legacy-v1` 与 `shadow-v1` active lane；不能生成 canonical
ToolFeedback、authorization incident 或 `DISPATCHED` 证据。T4/T5 的 legacy output
binding 仍使用 `durable_effect`，只是 receipt projection 暂标 `LEGACY_UNTYPED`。

`dynamic-required-v1` 只用于短期兼容 canary：

- capability 候选可缩小；
- legacy `case_*`/`transfer_*` control closure 始终保留；
- 低置信度 fallback 只回到该 Agent 原始 allowlist，不扩大到全局 Registry；
- 不改变无 tool call 时的 legacy 行为。

`dynamic-auto-v1` 只有在该 stage 的 typed completion/wait/handoff contract 通过后
才启用，并在同一 stage 删除无限 “Please use the tools” correction。不得全局一次性
将 `required` 改为 `auto`。

## 6. 分阶段实施

每个 Phase 可拆多个小 PR，但不得跨越 exit gate。每个 PR 必须增加通过目标
Interface 的测试，且旧测试保持绿色。

### T0 — truthful trace 与 frozen baseline

**修改**

- 扩展 `evals/trace.py`，增加 `ToolAttemptTrace`, `LegacyToolDecisionProjection`,
  `ToolExposureTrace`, `ToolFeedbackTrace` closed types；
- `MetaChain.handle_tool_calls()` 在 name lookup、JSON parse、schema validate、call
  start、exception、return conversion 每个 seam 写完整 attempt；
- 同步与 async 路径使用同一个 tracing Implementation；
- `ToolModule` 从 typed outcome 计算 success，不再硬编码；
- `FlowModule.export_runtime_trace()` 包含 Agent 内 model/tool/control call；
- 给所有 trace 增加 run/stage/agent/turn/trace IDs 和 schema token count；
- 生成 baseline capture/analyze 命令和 manifest；
- 添加 provider request spy 与 deterministic fake model/tool fixtures。

Baseline “完整 request/args/return”不等于明文落盘：捕获前先做 data
classification；credential/secret 字段拒绝持久化，普通 trace 只留 typed redaction、
digest 与 policy ref；确需复现的敏感 payload 进入加密、访问控制、有限 retention 的
artifact namespace。任何 evaluator-private label/answer 都不得进入 actor trace。

T0 类型只是 legacy 事实投影，不是 canonical Tool Decision Record。T2 建立
`tool_use/tracing.py` 后，Runtime journal 才成为 mutation authority，T0 projection
迁为对 canonical events 的只读 Adapter。

**不得改变**

- schema、tool order、tool choice、prompt、turn termination、tool execution、cache
  或 Agent handoff 语义。

**Exit gate T0**

- fixture 中每个 provider tool proposal 恰好对应一条 attempt terminal disposition；
- unknown/parse/exception/error-string/empty cases 都不被记录为 success；
- 两个 entry flow 的 frozen fixture trace 可重放并自动重算工具数/tokens/latency；
- 26 个空 log 或缺失 `trace.json` 的旧现状不再出现在新 fixture；
- baseline manifest 在 adaptive 代码进入前归档并固定 digest。

### T1 — canonical Capability Catalog

**新增**

- `tool_use/catalog.py` 的独立 `CapabilityCatalogCompiler` Module/contracts；
- `LegacyRegistryCatalogAdapter` 与 `SkillManifestCatalogAdapter`；
- `catalog check/build/diff` 命令；
- inventory report：decorator、manifest、Agent wrapper、active stage references；
- schema/binding/identity conflict 和 required config validation；
- content-addressed catalog artifact。

Compiler 只由 Run admission/Snapshot build 调用；ToolInteraction 只能消费已验证
artifact，不能 import source Adapter、读 manifest 或访问 Registry。

**迁移规则**

- 先为所有 active Agent callable 生成 `legacy-incomplete` descriptor；
- 每个 descriptor 在 T4 前补齐 use/non-use、risk、effect、data、output、dependency
  policy；
- `legacy-incomplete` 只允许 static/shadow，不允许 adaptive enforcement；
- manifest 参数 schema 与 callable/typed request schema 比较，不再成为平行真相；
- `SkillRegistry.register_skill()` 不再允许同名后注册者静默覆盖生产 binding；
- 删除 search 初始化过程的 MD5 fallback；在 T5 前可以保留显式 lexical-only test
  degradation。

**Exit gate T1**

- 当前 active tool universe 100% 有 namespaced identity、schema 和 execution binding；
- catalog compile 无 silent import failure、name collision 或 schema mismatch；
- 每个 current Agent 的 ordered callable list 可从 static policy + catalog 精确重建；
- catalog 在随机 map insertion order 下 digest 稳定；
- manifest 与 legacy Adapter 运行同一 contract suite；
- `catalog diff` 能解释每个行为相关 digest 变化。

### T2 — pure ToolInteraction 与 tool-use Evaluation Contract

**新增**

- `interaction.py` 的唯一 `advance()` Interface 和 closed request/directive types；
- `views.py` bounded `DecisionInputView`、executable/blocked-diagnostic Catalog/Inspect
  与 committed receipt views；
- actor-safe `ActorTurnScope`/decision-slot bindings、Runtime-only
  `RuntimeAuthorizationEnvelope` 与 append-only journal linkage；
- 两步 `CommitDecisionAndRequestNextTurnInputs -> DecisionTurnInputsCommitted`
  continuation 和 crash-recovery contract；
- `data_flow.py` closed classification/provenance/declassification/join/egress contracts；
- `bundle.py` static Selection Bundle 与 verifier；
- `policy.py` static parity policy artifact 与 pinned interpreter；
- `selection.py` deterministic eligibility 和 small-set bypass；
- `protocol.py` canonical interaction/control proposal；
- `feedback.py` typed/bounded projection；
- `benchmark/tool_use` 分离的 actor/evaluator-private case schema、runner 和 analyzer；
- deterministic fake catalog/model/tool/evaluator。

**首批 case family**

- direct、clarify、single、跨 turn 顺序 multi-tool；
- local file vs web/GitHub/arXiv confusion；
- auth/config/environment missing；
- write/destructive/egress denial；
- empty/transient/permanent/ambiguous；
- long output、prompt injection；
- memory-informed tool choice、memory abstention、malicious Evidence Card、
  evaluation-plane memory isolation；
- dependent order、provider multi-call proposal 必须按 v1 single-call contract 拒绝；
- repeated failure 和 evidence satisfied。

**Exit gate T2**

- 相同 canonical request + Selection Bundle digest 产生 byte-identical directive/digest；
- dense-enabled bundle 精确绑定 catalog/descriptor corpus/numeric runtime；陈旧、
  partial、catalog-swap 或 worker mismatch 不得进入 active selection；
- 任一 model-visible schema/order/alias/policy/protocol/Adapter change 改变正确 digest；
- 无关 metadata 和 dict insertion order 不改变 digest；
- closed interaction/control combination 全覆盖；
- forbidden candidate 永不进入 ranker；
- schema budget/low-confidence/degradation 行为由 policy fixture 精确测试；
- ToolFeedback 超预算时生成 artifact ref + bounded view；
- tool final-authorization denial 经 `ToolPreparationRejected` 回流且 Effect/Invocation=0；
- blocked-diagnostic hint 只产生 clarify/wait/remediation；无 schema/alias/Effect，
  `HIDDEN_DENY` actor bytes 为 0；
- actor request/cache 对 Run/Activity/fence/actual Intent/private contract 变体逐字节不变，
  outer Runtime authorization/Effect identity 随 envelope 改变且不能跨 Run replay；
- DISCOVER/feedback/input/protocol/rejection continuation 必须先 commit old outcome/new
  input spec，第二个 `advance()` 才能 prepare model Effect；中间 crash 不重复 outcome/
  Intent/Effect；
- data classification join、model claim only-add、trusted transform declassification、
  model/tool egress fail-closed 与 output inheritance 均有 golden/property tests；
- evaluator label type/bytes 无法进入 ToolInteraction、actor prompt、turn/cache identity；
- 同 actor fixture/view 改变 private labels 或 full evaluator contract digest 时，actor
  request/turn/cache bytes 不变；
- benchmark raw trace 可独立重算全部 diagnostic metrics。

### T3 — all-stage shadow integration

**新增/修改**

- private `LegacyMetaChainToolAdapter`；
- `AgentModule` 把 session active identity 传给 cache；
- `MetaChain` 每轮调用 migration Adapter 的 prepare/resolve；
- 所有 Agent factory 绑定 `legacy-v1`/`shadow-v1` profile ref；
- non-causal audit projector、bounded shadow outbox、selection-only shadow record 和
  independent replay command；
- active/shadow lane isolation；
- shadow inertness golden test 覆盖 sync/async 与 provider profiles。

**选择 Implementation**

T3 projector 只从已提交 canonical actor request artifact 派生 outbox ref。独立 worker
运行 hard filter + static allowlist + small-set bypass，记录
candidate/exposure/need-gate prediction；它不
预测 counterfactual model response。dense/hybrid 或完整 DIRECT/EXECUTE 反事实只在
独立 replay Run 中执行，不能在 active critical path 隐式加载模型或 Chroma。

**Exit gate T3**

- 两个 entry flow、所有 active Agent 均产生 shadow record；
- legacy 与 shadow active lane byte-equivalent；
- shadow failure/timeout 不影响 active result；
- Run event sequence 与 active Budget Envelope 不含 shadow execution；
- active path 不等待 shadow，且 p50/p95 active-latency overhead 通过预注册 SLO；
- active cache hit 不受 shadow policy/digest 影响；
- selection replay 只使用捕获的 canonical input并得到同一 shadow digest；
- 候选 universe/filter/exposure/need-gate prediction 覆盖率可自动报告。

### T4 — typed control 与 read-only adaptive canary

**新增/修改**

- `NativeFunctionCallProtocolAdapter` canonical round-trip；
- provider capability matrix 与 prompt-emulation contract tests；
- stage completion/wait/handoff typed contract；
- control namespace 与 legacy control compatibility mapping；
- 首个 read-only stage 切 `dynamic-required-v1`，然后切 `dynamic-auto-v1`；
- 该 stage 的 Agent tool list 改为 catalog + policy 生成；
- 低置信度 static-stage fallback，不允许 global expansion；
- run spec/cache/trace 绑定 active policy/Selection-Bundle/toolset/control digests。
- read-only legacy binding 通过 Runtime Effect Adapter 执行并产出真实
  Effect/Invocation/receipt/settlement；禁止回退 direct callable。
- Runtime preparation 只创建 `DISPATCHABLE` Effect/Invocation/reservation；紧邻
  Adapter entry 的 dispatch transaction 重验 state/generation/event/fence/incident、
  exact bindings、live auth/config/availability/approval、data-flow、budget/reservation
  与 effect-kind memory lineage，成功后才提交 `DISPATCHED`：model Effect 校验当前
  Intent/actor slot/Recall Input/optional Context 且该 turn 尚无 terminal Outcome；只有
  settled `EXECUTE` proposal 的 tool Effect 才要求 terminal Recall Decision Outcome 与
  `MemoryToolDecisionLinked`。

**Canary 顺序**

1. 已使用 optional tool choice 的只读 survey/idea role；
2. coding-plan read/planning role；
3. 其他无 write/command/Browser capability 的 role。

**Exit gate T4**

- canary 正确产生 direct 和 clarify，不进入 required correction loop；
- control action 不出现在 capability catalog、Effect 或 tool-call metrics；
- model 不能调用未暴露 alias、stale toolset 或非法 interaction/control combination；
- forbidden exposure/call 和 sensitive egress 为 0；
- 每个 executed canary call 有真实 Effect/Invocation/selected receipt/settlement；
- prepare 后 mutable authorization 变化必须落 `CONFIRMED_NOT_EXECUTED`、settle
  reservation、零 Adapter entry，并经 `ToolDispatchAuthorizationRejected` 回流；
- 与 static baseline 比较的 end-state gate 非劣；
- fallback 次数、原因和 schema budget 全部可解释；
- scientific/performance rollback 仅改变新 Run admission，健康 in-flight Run 保持
  pinned profile；integrity/security trigger 必须按 §9.3 建立 incident、revoke fence，
  并使受影响 scope 的新 `DISPATCHED` 为 0。

### T5 — progressive hybrid 与 trajectory-aware selection

**新增**

- deterministic lexical ranker；
- pinned local dense ranker Implementation 与 immutable model/index assets；
- deterministic fusion、stable tie break、adaptive top-k；
- tool-level positive/negative/pseudo-use queries 与 confused-with metadata；
- closed Catalog/Inspect view models、deterministic renderer/token accounting；
- low-confidence expand/clarify/static fallback；
- executable 与 blocked-diagnostic 两 lane 的独立 rank/budget/digest；
- committed ToolFeedback/subgoal/availability/evidence-gap re-selection；
- dense-only/static/hybrid/trajectory ablation runner。

**约束**

- 不新增 remote router 作为 v1 前置；
- dense 初始化失败按 policy 显式 `lexical_only | expand | clarify | wait | fail`；
- 小集合 schema 在预算内时不调用 retriever Effect；
- 同一个失败 proposal 无新状态/参数变化不得无限重复；
- active toolset 只在新 committed trigger 后变化。
- every re-selection/model continuation 使用两步 next-turn input commit，不能在旧
  Decision Intent/Recall binding 上直接创建 child model Effect。

**Exit gate T5**

- over-budget case 的 exact exposed schema 不超过 pinned budget；
- small-set bypass case 不增加 remote/model selection call；
- hard-negative 与 multi-tool set Recall/precision 报告完整；
- empty/typed failure 后能选择替代/扩展/澄清，不重复相同失败循环；
- evidence satisfied 后可转 DIRECT，不做多余工具调用；
- adaptive arm 通过 preregistered end-state noninferiority gate 后才能发布效率改善。

### T6 — execution Adapter 与 typed-output convergence

**前置**

T4 的 read-only Runtime Effect vertical slice 已通过；Durable Runtime Phase 2 的
Effect journal、Physical Invocation、Budget Envelope、fencing、reconcile、artifact
与 one-retry-owner contracts 保持绿色。

**新增/修改**

- 把 T4 的 `runtime/_tool_authorization.py` sealed authorization 与
  `runtime/adapters/tool_interaction.py` vertical slice 扩到全部 stage；
- 补齐 in-process/subprocess/Docker/Browser/fault ToolExecutionAdapters；
- exact capability/schema/binding/args/toolset/policy/Selection-Bundle digest validation；
- dispatch transaction 内 availability/approval/data-flow/budget recheck；
- `DISPATCHABLE -> DISPATCHED` 是唯一 Adapter-entry gate；失败提交
  `CONFIRMED_NOT_EXECUTED`/settlement 与 `ToolDispatchAuthorizationRejected`；
- full output artifact commit 与 bounded typed ToolFeedback；
- `LEGACY_UNTYPED` legacy binding/string output 逐个迁到 typed execution binding 并归零；
- 禁止 tool/SDK hidden retries；
- flow-level `ToolModule` 和 Agent internal tools 汇合到同一 Effect path。
- v1 provider proposal 最多一个 external tool call；multi-tool task 在 committed
  ToolFeedback 后由下一 turn 继续；
- `ToolPreparationRejected` closed trigger 和无 Effect-ID ToolFeedback；
- model/tool Effect 共用 provenance/classification/egress authorization；
- memory-informed proposal 的 Recall Decision Outcome/link guard。

**Exit gate T6**

- 每个 external dispatch 有唯一 Effect 与 Physical Invocation/reservation；
- denial 路径 logical Effect 与 Physical Invocation 数均为 0；
- dispatch rejection 保留已有 Effect/Invocation、Adapter entry=0、reservation 已
  settle；不得误算为 preparation denial；
- denial/unavailable/budget/approval 能回流 reselect/wait/fail，不悬挂等待不存在的
  receipt；
- stale fence、stale toolset、schema swap、args tamper 均不能 `DISPATCHED`；
- crash matrix 在 prepare/dispatch/return/receipt/feedback/reselect seams 全过；
- known/not-executed/ambiguous/reconciled/unresolved semantics 与 durable design 一致；
- late receipt 只能进 evidence inbox；
- unknown outcome 永不成为 successful ToolFeedback；
- memory-informed tool invocation 在 Recall Decision Outcome link 前 `DISPATCHED`=0；
- in-process/subprocess/Docker/Browser Adapter contract tests 全过；
- `LEGACY_UNTYPED` 数量按 manifest 跟踪并持续下降。

### T7 — all-stage migration 与双 entry flow 收敛

**修改**

- 按 read-only -> planning -> external search -> write/command/Docker/Browser ->
  judge/control 顺序迁移；
- Agent factory 只引用 stage capability/completion policy，不决定 callable list；
- `case_*`/`transfer_*` 从 Tool Catalog 和 provider capability list 删除；
- `MetaChain.handle_tool_calls()` 生产执行职责删除，只保留 protocol Adapter 所需
  的 wire translation 或整体被替换；
- `FlowModule.ToolModule` 不再是生产 execution/cache/retry authority；
- 两个 entry flow 通过相同 native Stage/Tool Interaction Adapter；
- Tool Effect trace 从 Runtime journal 投影到 Evaluation Contract；
-所有 legacy string return/tool wrappers 迁为 typed evidence。

**Exit gate T7**

- 所有 active Agent stage 都有 dynamic-auto/durable profile 或经批准的 no-tool
  control-only profile；
- concrete tool import 不再决定 Agent 暴露集合；
- direct callable dispatch 的 production caller 为 0；
- `LEGACY_UNTYPED` 为 0；
-两个 entry flow 的 parity、cache isolation、restart、completion/handoff tests 全过；
- final Research Run completion 仍要求 Verification/Experience、required Recall
  Decision Outcome、Experience Distillation Receipt 与 operational settlement 完整链。

### T8 — acceptance、rollout 与 deletion

**执行**

- static/hard-filter/dense/hybrid/trajectory 正式 Evaluation Contract；
- hard-negative catalog scale sweep；
- provider profile matrix；
- fault injection 与 repeated-trial reliability；
- shadow -> read-only canary -> risk canary -> percentage rollout -> default；
- rollback drill；
- acceptance manifest 与 raw artifacts 归档。

**删除/收敛**

- production `legacy-v1` 和 `LegacyToolExecutionAdapter`；
- `Agent.functions` 作为 capability selection authority；
- required-tool endless correction；
- `case_resolved`, `case_not_resolved`, `transfer_to_*` capability definitions；
- `SkillRegistry` 向 mutable global Registry 注入/覆盖；
- recursive eager tool import；
- public/production `SkillRegistry.search_tools()` 和 MD5 fallback；
- `ToolModule` 独立 execution/cache/retry/trace authority；
-重复的 tool schema truth sources；
- migration session Adapter。

**Exit gate T8**

- Section 10 的 release gates 全部通过；
- deletion `rg`、import graph 和 sealed legacy harness tests 证明生产无旧 caller；
- rollback 使用 retained durable bundle 或关闭 admission，不重新启用被删旧 authority；
- governing design 可从 Proposed 改为 Accepted；本计划可改为 Implemented。

## 7. Test strategy

Interface 是测试表面。测试不得依赖 private ranker 的中间 class 名或调用次数，除非
该次数本身属于 pinned Budget/Effect contract。

### 7.1 ToolInteraction contract suite

`tests/test_tool_use/test_interaction_contract.py` 必须覆盖：

- canonical request determinism 与 directive digest；
- 相同 request 在不同 Selection Bundle digest 下不得共享 decision/cache；
- request 包含 bounded canonical `DecisionInputView`/receipt view，`advance()` 不做
  artifact I/O、clock read 或 hidden summarization；
- `BeginInteraction -> model` 正常路径；
- DIRECT、CLARIFY、DISCOVER、EXECUTE；
- CLARIFY wait suspend/resume 保持 Interaction ID，InputResolution 后先返回
  `CommitDecisionAndRequestNextTurnInputs` 并递增 decision epoch；只有带已提交 child
  inputs 的第二次调用才能 prepare model Effect；stage/subgoal/handoff 才创建新 Interaction；
- 每个 memory-governed model Effect 使用新 Decision Intent；DISCOVER、CLARIFY、
  ToolFeedback 后的 child turn 不保留旧 rendered Recall Context bytes，并绑定 parent
  Recall Decision Outcome digest；
- DISCOVER、ToolFeedback、InputResolution、protocol correction、tool preparation/
  tool dispatch rejection 全部通过相同两步 continuation；model rejection 先 wait/reject；
  在 outcome commit、child Intent/input/
  recall preallocation 每个 seam crash/replay 都只补 missing suffix；
- actor request/directive 不含 Run/Activity/fence/full private contract/actual Intent；
  Runtime journal envelope binding 可 read-back 且 outer Effect identity 不跨 Run；
- interaction × control 的全部合法/非法组合；
- discovery/correction step 上限；
- same failed call loop detection；
- exact toolset/turn-contract echo；
- unknown/not-exposed/stale alias/invalid args；
- wait/fail closed errors；
- COMPLETE 不直接生成 Run terminal；
- HANDOFF 只允许 pinned workflow role；
- uncommitted/stale/ambiguous receipt 不进入下一次 trajectory；
- artifact-backed ToolFeedback 和 inline token budget。
- 每次 `advance()` 恰好一个 Tool Decision Record，且无未来
  directive/auth/Effect/Invocation/memory-outcome fields；
- `ToolPreparationRejected` 的 denial/unavailable/budget/approval ->
  reselect/wait/fail，四类均 Effect/Invocation=0；
- `ToolDispatchAuthorizationRejected` -> `CONFIRMED_NOT_EXECUTED` 保留 Effect/Invocation、
  settlement 完整、Adapter entry=0，并可 reselect/wait/fail；
- `ModelPreparationRejected` 无 Effect/Invocation，
  `ModelDispatchAuthorizationRejected` 保留 not-executed Effect/Invocation/settlement；
  两者均 ToolFeedback=0，只能关闭 Intent 后 wait/reject。只有新 committed resolution
  才能以新 Intent 走两步续回合；
- Runtime retry exhausted 才生成 `RETRY_EXHAUSTED` ToolFeedback；Adapter retryable
  中间态不得驱动 selector 自行重试；
- memory card disposition coverage、mapping、Recall Decision Outcome draft/link；
- DecisionMemoryBinding 的 NOT_REQUESTED/null/zero-card 与
  EMPTY|DEGRADED|OK/snapshot/context 组合 validator；blocked recall 不进入 model；
- NOT_REQUESTED 只接受 actual Intent 中 admission-proof-backed
  `REGISTERED_NOT_REQUESTED`；`REQUIRED` Intent/profile-proof tamper 必须 fail closed；
- evaluator-private label/answer type 或 bytes 进入 request 时 fail closed。
- blocked diagnostic hint 只有 bounded summary/reason/remediation，不能 Inspect/
  Execute/fallback；hidden deny 不能进入任何 actor bytes。

同一个 contract suite 至少运行 static-parity、hybrid-trajectory 和 deterministic
fake policy artifacts；不通过 Python policy subclass 选择行为。

### 7.2 Catalog contract suite

同一套测试运行 legacy/skill/in-memory source Adapter：

- canonical sort/round-trip/digest；
- duplicate identical fragment 可幂等合并；
- same ID/different schema、binding、risk、description fail closed；
- callable/typed request schema 与 manifest expected digest 一致；
- required config/auth 只存名称/scope，不泄露值；
- malicious `authorized: true` 或 unknown field 被拒绝；
- source import failure 显式失败，不吞异常；
- catalog artifact 可在新进程重载并得到同一 digest；
- diff 输出新增/删除/行为变化/非行为 metadata 变化分类。

### 7.3 Policy and selection tests

- stage/frozen/auth/config/environment/data-flow/risk/budget filter 顺序；
- descriptor/Selection/Execution policy 的 union/intersection/min/deny precedence
  冲突矩阵，missing applicable allow 默认 deny；selection/final authorization 共用
  normalized-policy digest/reason order；
- 被过滤 candidate 无论 score 多高都不能暴露；
- disposition 三分法和两 lane rank：executable ranker 永不看到 hidden/diagnostic，
  diagnostic ranker 永不产生 schema/alias/Effect 或 promotion；
- small-set bypass；
- absolute/context-fraction schema budget 取更严格值；
- lexical exact name/parameter match；
- semantic paraphrase dense match；
- deterministic fusion/tie-break；
- dense index 与 exact catalog/ordered descriptor corpus coverage；stale index、
  catalog swap、partial index fail/degrade closed；
- pinned numeric runtime 的 clean-process/cross-worker query feature、fixed-point
  score、ranked IDs 和 directive byte golden；不匹配 worker fingerprint 拒绝 admission；
- hard negative 与 confused-with；
- adaptive top-k 与 required multi-tool set；
- dense unavailable 的每个显式 degradation；
- low-confidence expand/clarify/static-stage fallback；
- fallback 不能越过 original stage allowlist；
- ToolFeedback/subgoal/evidence/availability change re-selection；
- input map order、unrelated stats 不影响 active decision digest。
- Selection Bundle 的 tokenizer/analyzer/model/index/fusion/threshold/renderer 任一
  行为 digest 变化均改变正确 identity；
- narrowing override 只接受预冻结 development artifact，含 evaluator case/label
  字段即拒绝。
- classification join 对 input/recall/feedback/artifact 保守闭包；model argument claim
  只能 add；伪造/缺失 declassification receipt、summary/truncation laundering、
  `EVALUATOR_PRIVATE|CREDENTIAL_SECRET` egress 全部 fail closed；model 与 tool Effect
  的 prepare/dispatch data-flow digest mutation matrix 完整。

### 7.4 Provider protocol contract suite

Native 与 prompt-emulation Adapter 运行相同 cases：

- DIRECT no-tool；
- CLARIFY control；
- DISCOVER control；
- single EXECUTE proposal；multiple/parallel proposal 按 v1 contract 整体拒绝且零
  Effect；
- COMPLETE/HANDOFF；
- malformed/double-encoded JSON；
- unknown provider alias；
- missing/wrong turn-contract digest；
- provider returns text plus tool call；
- provider returns parallel dependent calls；
- required/auto/none capability matrix；
- provider-specific downgrade 显式进入 profile digest；
- canonical proposal round-trip 与 wire order。

不能正确表达 optional no-tool 的 provider profile 不得进入 `dynamic-auto-v1`。

### 7.5 Shadow inertness tests

对每个 active Agent 和 provider profile保存 golden fixture，比较 legacy/shadow：

- model request bytes/digest；
- schema order/tokens；
- tool choice/parallel；
- number of provider calls；
- actual tool/control sequence；
- context patch/handoff/stage output；
- active cache identity/hit；
- active Effect/receipt；
- exception 与 termination behavior。

另外注入 shadow catalog corruption、ranker error、timeout 和 oversized trace，证明
active bytes、Run event sequence、active Budget Envelope 不变且 shadow failure 有界
可见。测试还必须证明 active path 不写 mode-specific outbox event、不等待 audit
projector；selection worker 在 request artifact 提交后运行，且 production shadow 不发
remote/model Effect。隔离资源池下 p50/p95 active latency 必须通过预注册 overhead
SLO。projector 在 missed notification/crash/duplicate scan 下按 derived job ID
eventually-complete 且无重复 logical record。完整反事实 replay 使用独立 Run ID、
budget、journal 与 cache namespace。

### 7.6 Final authorization tests

`tests/test_runtime/test_tool_authorization.py` 至少覆盖：

- highest-ranked forbidden capability；
- capability exposed 后 credential revoked；
- provider alias collision；
- schema/binding/policy/toolset digest swap；
- canonical args 在 selection 后被篡改；
- stale Run state/event seq/Activity generation/fence；
- Budget Envelope insufficient；
- destructive approval missing/expired/wrong principal；
- private/evaluator data -> open-world destination；
- idempotency/reconcile contract incompatible；
- preparation denial 不创建 Effect/Physical Invocation/reservation；
- preparation acceptance 在一个 transaction 创建 Effect、`DISPATCHABLE` invocation、
  reservation，但 Adapter entry 仍为 0；
- prepare/dispatch 之间分别 revoke credential、remove config、expire approval、change
  availability/budget、open incident、advance state/generation/fence 或 tamper data-flow：
  dispatch transaction 必须提交 `CONFIRMED_NOT_EXECUTED`、settle
  reservation、发 closed trigger，且 Adapter entry=0；
- exact unchanged bindings 只有在原子 `DISPATCHABLE -> DISPATCHED` commit 后才允许
  Adapter entry；commit/reply crash 由 invocation read-back reconcile；
- model provider 与 semantic summarizer 的 confidential/restricted egress 使用同一
  preparation/dispatch authorization，未经 commit 不发送 bytes；
- model Effect 必须能在其 terminal Recall Decision Outcome 尚不存在时 dispatch，但须
  绑定 current Intent/actor slot/Recall Input/optional Context；伪造旧 Intent、错误 slot、
  foreign Context 或预先存在 Outcome 均拒绝；
- memory-informed accepted **tool** invocation 在 `MemoryToolDecisionLinked` 前不能
  获得 `DISPATCHED`，移除/篡改 link 会得到 dispatch rejection，link append/replay 幂等。

### 7.7 Tool Execution Adapter contract suite

同一套 contract 运行 in-process、subprocess、Docker、Browser 和 scripted fault
Adapter（不适用项必须显式声明）：

- one `invoke` = at most one physical dispatch；
- no hidden retry；
- request/capability/schema/binding/args digest validation；
- timeout、cooperative cancel、TERM/KILL 与 owned resource cleanup；
- query/reconcile known/not-executed/ambiguous；
- late evidence inbox；
- stale Adapter/worker 不能选择 receipt 或 settle；
- full output artifact + bounded ToolFeedback；
- Browser session identity/state isolation；
- Docker container/process ownership labels；
- non-cooperative in-process tool 被 contract 拒绝并要求 process Adapter。

### 7.8 Fault-injection seams

每个 case 至少 kill/crash 于：

1. Tool Decision Record 构建前/后；
2. model Effect prepared 前/后；
3. model receipt committed 后、proposal compile 前；
4. tool proposal validated 后、authorization 前；
5. continuation spec commit 后、child Intent/Input/Recall commit 前，以及其 commit 后、
   第二次 `advance()` 前；
6. authorization 后、Recall Decision Outcome/link 前；
7. Effect/`DISPATCHABLE` Physical Invocation/reservation transaction 后；
8. dispatch reauthorization transaction 前/commit 后、Adapter entry 前；
9. `DISPATCHED` 后、external Seam 前；
10. provider return 后、receipt commit 前；
11. receipt commit 后、artifact/ToolFeedback 前；
12. ToolFeedback commit 后、trajectory continuation spec/child input 前；
13. stage proposal 后、StageContinuation transition 前。

恢复断言：同一 logical Effect、完整 independent Physical Invocation history、至多一个
selected receipt、正确 worst-case settlement、无 stale commit、无重复 irreversible
side effect、只补缺失 suffix。

### 7.9 Cache and replay tests

- catalog/policy/Selection-Bundle/protocol/toolset/schema/Adapter/trajectory 任一行为
  digest 变化 cache miss；
- actor Recall Context digest 变化或 recall/no-recall 变化产生 cache miss；相同 actor
  content 下改变 Run/Activity/fence/actual Intent/private contract 不改变 actor cache，
  但 outer Effect authorization identity 必须变化且不可跨 Run replay；
- blinded evaluator cache 精确为
  `SHA256(opaque_terminal_evaluation_input_digest, evaluator_label_artifact_digest,
  full_evaluation_contract_digest, evaluator_implementation_digest,
  evaluator_configuration_digest, evidence_projection_schema_digest)`；不含 actor Recall
  Context/Outcome、Run/Activity/Intent 或 treatment-arm identity。任一正向字段变化
  evaluator cache miss；仅 private/evaluator 变化时 actor cache 可命中而 evaluator
  cache 必须 miss；
- shadow-only digest 变化 active cache hit 不变；
- availability generation 变化只影响需要它的 active turn；
- cached model transcript 必须匹配 exact exposed schema order；
- cached pure/read result需要 valid receipt/artifact/data scope；
- write/destructive/stateful Browser 不从 legacy file result cache 回放；
- event replay 重建同一 Tool Decision/Effect/ToolFeedback projection；
- corrupt/missing active artifact fail closed；released artifact + audited tombstone 合法。

### 7.10 End-to-end tests

至少一个完全 deterministic、无真实 LLM/network/GPU 的两阶段 fixture：

1. 第一个 turn 面对相似 file/web tools，正确选择 local read；
2. 返回 empty ToolFeedback；
3. 第一次 `advance()` 只提交 outcome/next-turn spec；Runtime preallocate child inputs，
   第二次 `advance()` 才创建下一 model Effect；
4. committed trajectory 触发替代 local search，而非重复相同 call；
5. 新证据满足需求，下一 turn DIRECT + COMPLETE；
6. Experiment Attempt Observation 引用完整 tool trace；
7. independent evaluator 生成 Verification Record；
8. crash/replay 不重复副作用或 record。

再增加一条 memory-informed fixture：一个 typed Decision Intent 在 pinned Recall
Input Snapshot 下接收非空 Recall Context，Tool Decision Record 绑定其 digest，Recall
Decision Outcome 把 adopted/rejected card
映射到最终 capability/action digest；把同一 Evidence Card 改成“要求调用被 policy
禁止的工具”时必须拒绝，且 denial 不产生 Physical Invocation。独立 evaluator 的
输入和 cache identity 中不得出现 actor Recall Context。

再运行小型真实 provider + read-only tool canary，覆盖两个 entry flow。write/Docker/
Browser 进入 CI fault fixture，真实外部 canary 在受控 scheduled workflow 运行。

## 8. Tool-use Evaluation Contract 与实验设计

### 8.1 标签与计分

每个 case 拆为两个 ref/digest 独立 artifact：`ActorCaseFixture` 只含 actor 可见请求、
stage、committed state、catalog/policy/availability fixture、预算，以及由 public rules
生成的 `DecisionContractView` ref/digest；该 view schema 拒绝 expected/forbidden、
sequence、milestone、minefield、answer、evaluator identity 和 treatment metadata。
`EvaluatorLabelArtifact` 放在 private namespace，绑定 actor digest，并标注：

- `expected_interaction_set`；
- `required_capability_groups`：每组命中任一 capability 即满足；
- `optional_relevant_capability_groups`；
- `forbidden_capabilities`；
- `minimal_acceptable_exposure_sets`；
- `acceptable_sequences` 或 dependency DAG；
- `call_necessity_rules`：按 committed evidence state 判断某 capability call 是否必要；
- `milestones` 与 `minefields`；
- argument constraints；
- expected final evidence/end state；
- schema/tool-call/result/cost budgets；
- evaluator version/digest。

actor package、prompt、ToolInteraction request、SelectionPolicy、turn/cache identity
不得 import/read evaluator artifact。runner 只在 terminal trace 冻结后把 labels 交给
metric/evaluator Module；CI 有 dependency 和 byte-leak tests。同一 ActorCaseFixture/
DecisionContractView 配不同 private labels、evaluator identity 或 treatment metadata，
actor request、turn-contract 和 cache-key bytes 必须完全相同。

独立 evaluator cache 的唯一 v1 positive identity 是以下 canonical tuple 的 SHA-256：

```text
opaque_terminal_evaluation_input_digest
evaluator_label_artifact_digest
full_evaluation_contract_digest
evaluator_implementation_digest
evaluator_configuration_digest
evidence_projection_schema_digest
```

runner 必须把六项和 resulting cache digest 写入 raw evaluation artifact/acceptance
manifest。Run/Activity/Decision Intent、actor Recall Context/Outcome 和 treatment-arm
identity 禁止作为独立字段。任一六项变化 mandatory miss；改变 private labels/
contract/evaluator 时 actor request/cache 必须保持命中条件不变，而 evaluator cache
必须失效。

核心集合指标：

```text
required_set_recall = satisfied_required_groups / all_required_groups
exposure_precision = exposed_relevant_capabilities / all_exposed_capabilities
excess_exposure = exposed_capabilities - minimal_acceptable_exposure
unnecessary_call_rate = unnecessary_executed_calls / all_executed_calls
forbidden_call_rate = forbidden_executed_calls / all_executed_calls
trace_completeness = terminally_accounted_attempts / all_provider_proposals
```

`MetricSpec-v1` 冻结以下唯一计算规则：

- 无 required group 的 direct/clarify case，`required_set_recall=null` 并从该指标
  macro denominator 排除；另由 direct/clarify accuracy 计分，不记成 recall 失败；
- `exposure_precision`：expected relevant 与 exposed 都空时为 1；exposed 空但
  required 非空时为 0；否则按 required+optional relevant union 计算；
- `excess_exposure=max(0, |exposed|-min_acceptable_size)`；miss 由 recall 单独惩罚；
- unnecessary call 由 frozen `call_necessity_rules` 对每个 committed pre-call state
  判定，不依赖事后模型主观打分；
- forbidden-call 零调用分母记 0；trace-completeness 零 tool-proposal case 记 1；
- 先按 Research Run 算，再按 registered case/seed pair 聚合；主报告 task-family
  macro，micro 只作诊断；multi-tool 同时评 set 与顺序。

`ReleaseCriteria-v1` 是机器可读 artifact，包含 primary/secondary metrics、方向、
margin/threshold、family harm guardrail、样本量/power、alpha、多重性、paired CI
estimator/bootstrap cluster、stopping/missing/invalid-run rules、latency/cost bound 和
MetricSpec/analyzer digests。T0 baseline 后、adaptive assignment/result 解盲前冻结；
analyzer 拒绝 CLI 临时覆盖。

### 8.2 Migration parity 与五个 selection arm

先做独立 migration-parity 实验：真实 legacy path 对 canonical static Adapter，保持
legacy provider/control bytes 一致，只证明迁移无行为变化；该实验不估计 selection
收益。

selection ablation 的五个 arm 全部使用同一个 canonical optional-tool/typed-control
provider profile，只改变 SelectionPolicy/Bundle：

```text
A CANONICAL_STATIC
B HARD_FILTER_STATIC
C DENSE_TOP_K
D HYBRID_ADAPTIVE
E HYBRID_TRAJECTORY
```

固定：

- model/provider/profile 与 sampling config；
- case、seed/arm order/randomization；
- Capability Catalog 与 concrete Tool Implementations；
- Evaluation Contract/evaluator；
- Budget Envelope、timeouts、output policy；
- prompt/history/input artifacts；
- environment/credential availability fixtures；
- cold/warm cache protocol；
- failure injection schedule。

每个 arm 使用不同 selection policy/Selection-Bundle digest，但不能看到其他 arm 的
cache、trace、ToolFeedback 或 derived statistics。arm assignment 与 analysis plan 在
正式运行前归档。

### 8.3 分层报告

至少报告：

- no-tool/direct；
- clarification；
- small compact stage set；
- over-budget large set；
- single-tool；
- multi-tool dependency；
- hard-negative confusion；
- availability/auth；
- risky/egress；
- error recovery；
- long-output；
- prompt injection；
- provided-idea/reference-ideation flow；
- provider profile；
- catalog size/distractor similarity。

不得只报告总体平均数掩盖危险工具或 multi-tool recall 退化。

### 8.4 Claim order

发布结论按以下顺序：

1. trace/catalog/protocol contract 正确；
2. safety/governance gate；
3. final valid end-state noninferiority；
4. selection diagnostics；
5. schema/result token、latency 和 cost 改善；
6. trajectory-aware 增益；
7. 只有 verified trace 规模和离线/在线实验足够后，才讨论 learned reranker、
   fine-tuning 或 RL。

不能用 relevance score 或 schema token reduction 替代 Verification pass。

## 9. Rollout、监控与回滚

### 9.1 配置固定

Research Run spec pin：

```yaml
tool_use:
  profile_ref: artifact://tool-profiles/dynamic-auto-v1.json
  profile_digest: "..."
  catalog_ref: artifact://tool-catalogs/catalog-v1.json
  catalog_digest: "..."
  selection_policy_ref: artifact://tool-policies/adaptive-v1.yaml
  selection_policy_digest: "..."
  selection_bundle_ref: artifact://tool-selection/bundle-v1.json
  selection_bundle_digest: "..."
  execution_policy_ref: artifact://tool-policies/execution-v1.yaml
  execution_policy_digest: "..."
  provider_protocol_ref: artifact://tool-protocols/native-v1.json
  provider_protocol_digest: "..."
  adapter_bundle_ref: artifact://runtime-adapters/tool-v1.json
  adapter_bundle_digest: "..."
  normalized_tool_configuration_digest: "..."
  release_criteria_ref: artifact://tool-evals/release-criteria-v1.json
  release_criteria_digest: "..."
  deployment_bundle_ref: artifact://deployments/tool-runtime-v1.json
  deployment_bundle_digest: "..."
```

full Evaluation Contract/Run/Activity/fence/actual Decision Intent identity 仍在 Runtime
spec/envelope，不进入 actor-visible Research Context Snapshot 或 actor cache。Snapshot
只带 sanitized `DecisionContractView` 与上述 normalized tool configuration 的 actor-safe
behavioral projection；private-only contract 变化创建新 Run，但不改变相同 actor content
的 transcript cache bytes。

进程环境变量只能选择新 Research Run 的已批准 bundle，不能改变 in-flight Run。

### 9.2 Rollout 阶段

1. all-stage shadow，至少覆盖预注册 case/run 数量；
2. internal deterministic/read-only canary；
3. 真实 provider read-only canary；
4. planning/external-search canary；
5. write/command/Docker/Browser risk canary；
6. 10% new Research Runs；
7. 50%；
8. 100% default；
9. 完成正式 A/B、rollback drill 后删除 legacy production path。

每档都需要覆盖 fault-free window 和预注册 task family，不以“运行了几天”替代样本
与事件数。

### 9.3 自动停止/回滚触发

以下 integrity/security 事件是紧急隔离，不允许“in-flight 继续 pinned bundle”：

- forbidden/destructive/egress authorization bypass > 0；
- unknown/ambiguous outcome 被渲染为 success > 0；
- stale fence/toolset/schema/args commit > 0；
- duplicate irreversible side effect > 0；
- trace completeness < 100%；
- cache cross-policy/cross-arm leakage > 0；
- catalog integrity/replay failure；
- ToolFeedback redaction/private-data canary 泄漏。

同一个 authenticated system-control transaction 关闭受影响 admission、建立 incident
epoch/scope、撤销受影响 worker fence 和尚未 `DISPATCHED` 的授权。受影响 Run 进入
durable design 规定的 quarantine：`WAITING_INPUT`、cancel/terminate/reconcile 或
typed failed disposition；incident scope 内新 `DISPATCHED`=0。只有确认不在 scope 的
健康 Run 才继续。

以下 scientific/performance regression 只停止新 adaptive admission：final
noninferiority 失败、p95 latency/cost 越界。健康 in-flight Run 保持其 pinned bundle，
避免中途改变实验条件。Provider malformed/unavailable 按 typed availability policy
进入 refresh/wait；若同时构成完整性风险则升级为 incident。

每个 deployment bundle 绑定 code revision、journal/event schema readers、upcasters、
canonical serializer、provider/Tool Adapters 和 compatibility matrix。发布至少保留
current、previous durable bundle，以及任何仍被 in-flight Run 引用的 bundle；只有
引用计数为 0、settlement 完成、replay/retention gate 通过后才 GC。Append-only event
不做 downgrade rewrite；旧 binary 无法解析新 schema 时停止 admission/进入
`WAITING_INPUT`，不能丢字段继续。删除 legacy 后，回滚目标只能是 retained previous
durable bundle，禁止恢复 mutable Registry/direct callable authority 来“救火”。

## 10. Release gates 与权威证据

### G1 — Trace truth

**要求**

- `trace_completeness == 1.0`；
- 每个 proposal/attempt 有唯一 terminal disposition；
- error/denial/empty/ambiguous 分类正确；
- raw trace 能重算 tokens/latency/cost/metrics。

**证据**

- `pytest -q tests/test_core_usage.py tests/test_workflow/test_flowcache.py tests/test_tool_use/test_shadow_inertness.py`
- baseline manifest、raw trace 和 analyzer digest。

### G2 — Catalog identity and completeness

**要求**

- active capability 100% canonicalized；
- collision/schema/binding drift 0；
- no secret/live handle in catalog；
- static policy 可重建每个 baseline Agent set；
- `ToolConfigurationValidator` 产生并验证 normalized catalog/policy/bundle/protocol/
  Adapter configuration digest；Catalog compiler 不拥有 cross-policy authority。

**证据**

- `python -m research_agent.inno.tool_use.catalog check`
- `pytest -q tests/test_tool_use/test_catalog_contract.py`
- catalog artifact、inventory 和 diff report。

### G3 — Decision and protocol correctness

**要求**

- pure determinism；
- bounded canonical views；Selection Bundle 完整绑定；
- closed interaction/control semantics；
- v1 one-tool-call-per-turn、preparation/dispatch-rejection closed 回流；
- model-vs-tool rejection trigger/lineage/continuation matrix 全覆盖，model rejection
  永不伪造 ToolFeedback；
- next-turn continuation 必须分成 outcome/input commit 与后续 prepare 两次调用；
- executable/diagnostic 两 lane 均先 policy classification 再独立 rank，diagnostic
  永不暴露 schema/alias 或执行；
- schema budget；
- evaluator label/input/cache isolation；
- all enabled provider profiles pass optional no-tool/control round-trip。

**证据**

- `pytest -q tests/test_tool_use/test_interaction_contract.py tests/test_tool_use/test_policy.py tests/test_tool_use/test_protocol_contract.py`
- provider compatibility matrix。

### G4 — Shadow inertness

**要求**

- active bytes/digests/effects/results 与 legacy一致；
- shadow failure 不影响 active lane；
- shadow 不进入 active cache、Run event sequence、Budget Envelope 或 dispatch；
- production shadow 只从 non-causal outbox selection-only 执行，无 remote/model
  call，且 active path 不等待；
- 隔离 worker pool 下的 p50/p95 active-latency overhead 通过预注册 SLO。

**证据**

- all-Agent golden report；
- both-flow shadow run artifacts；
- shadow fault injection report。

### G5 — Authorization and safety

**要求**

- forbidden exposure/call、authorization bypass、sensitive egress、approval bypass、
  stale commit、alias/schema/args swap 均为 0；
- model/tool preparation denial logical Effect/Physical Invocation = 0；tool dispatch rejection 保留
  已有 lineage、`CONFIRMED_NOT_EXECUTED`/settlement 完整且 Adapter entry=0；
- model/tool/summarizer egress 的 provenance/classification/declassification 重算无 bypass；
- prompt injection minefield触发 = 0；
- malicious Evidence Card/Recall Context 不得扩大 eligibility、approval、scope 或
  egress；对应 denial Physical Invocation = 0；
- memory-informed tool invocation 在 Recall Decision Outcome link 前 `DISPATCHED`=0；
- blocked diagnostic 的 capability identity、summary、reason、remediation 四组逐字段
  leak matrix 全过；visibility 无匹配/冲突/deny 时 actor bytes 均为 0。

**证据**

- `pytest -q tests/test_runtime/test_tool_authorization.py tests/test_tool_use/test_policy.py`
- security case Evaluation Contract report。

### G6 — Durable Effect correctness

**要求**

- one retry owner；
- every dispatch has Effect/invocation/reservation；
- `DISPATCHABLE -> DISPATCHED` 是唯一 Adapter-entry authorization；prepare/dispatch
  间 mutable-state race 全部 closed not-executed；
- receipt/reconcile/ambiguity/settlement 正确；
- continuation input/outcome/child Intent 与 Effect/dispatch fault seams 只补 missing suffix；
- Adapter 无 owned-resource leak。

**证据**

- `pytest -q tests/test_runtime/test_tool_effect_adapters.py tests/test_runtime/test_tool_effect_faults.py`
- scripted fault raw events、projection replay 和 budget report。

### G7 — Cache, Snapshot, and replay

**要求**

- 所有行为 digest 变化正确 miss；
- Selection Bundle 任一行为 asset 变化正确 miss；
- shadow-only 变化不污染 active；
- cross-arm/cross-policy leakage = 0；
- actor recall/no-recall 正确隔离，blinded evaluator identity 不泄露 recall/arm；
- 同一 actor fixture/DecisionContractView、不同 evaluator-private labels/contract
  digest 得到逐字节相同 actor request、turn contract 与 cache key；
- 同 actor content 下 Run/Activity/fence/actual Intent/private contract 变化不进入 actor
  cache，但 Runtime envelope/outer Effect identity 改变且 cross-Run Effect reuse=0；
- evaluator cache 精确绑定 terminal opaque input、labels、full contract、evaluator
  implementation/configuration 和 evidence projection schema；六项任一变化 miss；
- replay 产生相同 Tool Decision/Effect/ToolFeedback projection。
- Tool Decision Record 保持纯因果边界，later events 只在 projection join。

**证据**

- `pytest -q tests/test_tool_use/test_cache_identity.py tests/test_workflow/test_flowcache.py`
- replay/invalidation matrix artifact。

### G8 — End-state noninferiority and efficiency

**要求**

- paired Run-level valid-pass delta 的 95% CI 下界高于预注册 margin；默认 margin
  不得宽于 `-2` percentage points；
- required-capability-set recall 和 direct/clarify macro accuracy 不低于预注册
  baseline bound；
- over-budget stratum 的 exposed schema tokens 满足 policy 且 paired reduction > 0；
- small-set bypass 不增加 selector model/remote Effect；
- runtime/selection overhead 的 median/p95 bound 在 T0 后、正式结果前冻结；
- migration parity 与 common-profile selection ablation 分开，不混入 protocol/control
  差异；
- `ReleaseCriteria-v1`、MetricSpec、样本量/power/CI estimator 在解盲前可验证冻结；
- 任意 efficiency claim 同时报告 end-state、调用数、tokens、latency、cost 和方差。

**证据**

- `python -m benchmark.tool_use.run --manifest ...`
- `python -m benchmark.tool_use.analyze --manifest ...`
- preregistered analysis plan、randomization、raw results、power simulation 和
  Verification Records。

### G9 — Production convergence and deletion

**要求**

- 两个 entry flow 和全部 production Agent 通过目标路径；
- direct callable/control-as-tool/MD5/global overwrite/duplicate cache-retry-trace
  authority production caller = 0；
- rollback 不依赖 deleted legacy path；
- current/previous/in-flight deployment bundles 可重放；integrity incident 能关闭
  admission、revoke fence、quarantine/reconcile，受影响 scope 新 `DISPATCHED`=0；
- docs/index/status 与当前代码一致。

**证据**

- dependency/import tests；
- `rg` deletion manifest；
- full test suite；
- rollout/rollback drill；
- acceptance manifest。

## 11. Acceptance manifest

每个 release candidate 归档机器可读 manifest，至少包含：

```text
git_revision
python_dependency_os_provider_fingerprint
tool_interaction_schema_version_and_digest
capability_catalog_ref_and_digest
catalog_inventory_and_conflict_report_digest
selection_and_execution_policy_refs_and_digests
selection_bundle_ref_and_digest
provider_protocol_matrix_and_adapter_bundle_digest
normalized_tool_configuration_digest
deployment_bundle_and_schema_compatibility_matrix_digest
research_context_snapshot_and_cache_identity_schema_digest
actor_scope_runtime_authorization_envelope_linkage_digest
baseline_manifest_and_raw_trace_digest
shadow_golden_and_fault_report_digest
actor_case_corpus_and_private_evaluator_label_digests
evaluator_cache_identity_and_invalidation_report_digest
metric_spec_and_release_criteria_refs_and_digests
arm_randomization_and_preregistered_analysis_digest
model_tool_environment_budget_fingerprints
tool_decision_and_effect_trace_digest
memory_decision_outcome_binding_report_digest
authorization_security_report_digest
data_flow_provenance_declassification_report_digest
dispatch_reauthorization_and_not_executed_report_digest
adapter_contract_and_fault_matrix_digest
cache_replay_invalidation_report_digest
raw_usage_latency_cost_and_end_state_results_digest
noninferiority_and_efficiency_analysis_digest
rollout_stage_task_counts_and_incidents
rollback_drill_digest
legacy_deletion_and_dependency_scan_digest
known_waiting_input_and_ambiguous_effect_cases
```

每个 digest 必须解析到随 release candidate 保存的 immutable artifact；只有 hash
没有可取回内容不算证据。正式分析前归档 raw results、arm assignment 和 analysis
plan。手工删除失败 case、重分类 error、替换 catalog/tool output 或修改 evaluator
必须写 manifest deviation，并使对应 gate 失败或重跑。

## 12. Pull request sequence

建议 PR 顺序：

1. **Trace truth:** internal attempt trace、typed disposition、baseline capture。
2. **Canonical contracts:** serializer、deep-immutable values、supporting policy types。
3. **Catalog contracts:** canonical descriptors、legacy/skill Adapters、inventory。
4. **Selection assets:** bounded views、Selection Bundle、static policy、renderer。
5. **ToolInteraction core:** pure Interface、single-call protocol、feedback/rejection。
6. **Evaluation harness:** actor/private-label split、MetricSpec、runner/analyzer。
7. **Shadow Adapter:** non-causal outbox worker、MetaChain bridge、causal/budget
   inertness 与 active-latency overhead SLO。
8. **Typed control:** provider protocol、completion/wait/handoff、read-only canary。
9. **Hybrid selection:** lexical+dense/fusion、progressive disclosure、hard negatives。
10. **Trajectory:** committed feedback/subgoal/availability re-selection。
11. **Runtime authorization:** sealed transaction、Effect request、reservation。
12. **Memory linkage:** Recall Decision Outcome guard 与 crash/replay。
13. **Execution Adapters:** in-process/subprocess/Docker/Browser + fault suite。
14. **Typed output:** artifact/bounded feedback、legacy tool migrations。
15. **All-stage migration:** policies、两个 entry flow、control tool removal。
16. **Formal evaluation and rollout:** parity/ablation、fault、canary、incident/rollback。
17. **Deletion:** old production authorities、migration Adapter、stale docs/tests。

不要把 1--15 合成一次大改。每个 PR 必须有可独立 review 的 Interface-level
contract test 和明确 rollback point。

## 13. Definition of Done

- [ ] Phase 0 baseline manifest 与 raw traces 在行为修改前归档；
- [ ] active capability universe 100% 进入 canonical Capability Catalog；
- [ ] catalog 无 collision/schema/binding drift、secret 或 silent import failure；
- [ ] ToolInteraction 只有一个 pure `advance()` Interface，不读 artifact/clock/remote
      dependency，并在 pinned Selection Bundle 下通过 determinism suite；
- [ ] DIRECT/CLARIFY/DISCOVER/EXECUTE 与 COMPLETE/HANDOFF typed 且不混入 Tool Effect；
- [ ] executable 与 policy-approved blocked-diagnostic 两 lane 都先完成 closed policy
      classification 再独立 ranking；hidden deny 不进入 actor bytes，diagnostic 永不进入
      Inspect/Execute/fallback；diagnostic visibility/remediation 来自 content-digested
      ExecutionPolicy，no-match/conflict/deny fail closed，逐字段 private-capability leak=0；
- [ ] descriptor/Selection/Execution 通过一个 fail-closed policy algebra 合成，
      selection 与 final authorization 共用 normalizer/reason precedence；
- [ ] small-set bypass、schema budget、internal Catalog/Inspect/Execute views 和
      explicit degradation 可验证，且不读取 evaluator labels；
- [ ] MD5 或其他无语义的 silent fallback 已删除；
- [ ] dense index 绑定 exact catalog/descriptor corpus 和 deterministic numeric runtime；
      stale/partial/mismatched worker 被拒绝或显式降级，cross-worker byte golden 通过；
- [ ] 每次 `advance()` 恰有一个 causal-pure Tool Decision Record；每个 model turn 有
      exact toolset/turn-contract digest，later events 不回写 record；
- [ ] actor `ToolInteractionRequest` 只含 ActorTurnScope；Run/Activity/fence/full private
      contract/actual Intent 只在 RuntimeAuthorizationEnvelope，journal 双层 binding 可
      read-back，actor cache byte-isolated 且 Effect 不可跨 Run replay；
- [ ] memory-informed model decision 绑定 Decision Intent、Recall Input Snapshot 与
      optional Recall Context；model Effect 在 Outcome 前可 dispatch，settled `EXECUTE`
      proposal 的 tool Effect 另绑定 terminal Recall Decision Outcome；Evidence Card 不能
      改变 eligibility/approval/authorization，tool outcome link 前新 `DISPATCHED`=0；
- [ ] NOT_REQUESTED actor binding 只能由 actual Intent 的 verified
      `REGISTERED_NOT_REQUESTED` governance binding 投影；REQUIRED Intent 无降级通道；
- [ ] 每个 memory-governed model turn 使用新 Intent；child turn 删除旧 recall bytes、
      绑定 parent outcome，并按新 committed state 重新 recall/记录 not-requested；
- [ ] DISCOVER/feedback/input/protocol/tool preparation/tool dispatch rejection 需要续回合时的第一次
      `advance()` 只提交旧 outcome 与 NextTurnInputSpec；Runtime preallocate child
      Intent/Input/Recall 后第二次调用才可准备 model Effect，crash seams 不重复；
- [ ] shadow 通过 non-causal outbox 脱离 active critical path，active bytes/Run event
      sequence/Budget byte-inert，满足 overhead SLO，并覆盖两个 flow/全部 Agent；
- [ ] enabled provider profile 支持正确 optional no-tool 和 control protocol；
- [ ] 每个 external tool dispatch 是 Runtime Activity 下的 Effect/Physical Invocation；
- [ ] preparation transaction 只创建 Effect/`DISPATCHABLE` invocation/reservation；紧邻
      Adapter entry 的原子 dispatch transaction 重验全部 mutable/immutable authority，
      成功后才 `DISPATCHED`；
- [ ] v1 每个 model turn 最多一个 external tool call；tool preparation rejection 回流且
      Effect/Invocation=0；
- [ ] tool dispatch rejection 保留 Effect/Invocation，提交 `CONFIRMED_NOT_EXECUTED`、settle
      reservation、Adapter entry=0，并经 closed trigger 回流；
- [ ] model preparation/dispatch rejection 分别保持 zero-Effect 与 existing-not-executed
      lineage，ToolFeedback=0，关闭 Intent 后 wait/reject；新 model turn 只能来自新状态；
- [ ] retriever/ranker 无路径调用 execution Adapter；
- [ ] one retry owner、late receipt、ambiguity、reconcile、settlement contract 完整；
- [ ] in-process/subprocess/Docker/Browser/fault Adapter contract suites 全过；
- [ ] ToolFeedback typed、bounded、artifact-backed，`LEGACY_UNTYPED` 为 0；
- [ ] tool preparation rejection 四态与 Effect terminal/retry-exhausted status 闭合；
      selector 不拥有 retry；
- [ ] Decision Input/Recall/arguments/model requests/tool output/summaries 全部带 closed
      classification/provenance；conservative join、trusted declassification、model/tool
      prepare+dispatch egress tests 全过且 private/credential 泄漏为 0；
- [ ] ToolFeedback 与 Experiment Attempt Observation 的身份和命名分离；
- [ ] 每个 committed feedback/failure/evidence/subgoal/availability change 可触发重选；
- [ ] dependent calls 跨 committed ToolFeedback turns 串行正确；v1 未因 provider
      parallel flag 绕过 Runtime；
- [ ] Research Context Snapshot 包含 catalog/policy/Selection-Bundle/protocol/Adapter
      digests 和 actor-visible DecisionContractView；actor-turn cache 另绑定
      decision/recall/trajectory identity，且不绑定 evaluator-private contract digest；
- [ ] cross-arm/cross-policy/cache leakage 为 0；
- [ ] tool-use Evaluation Contract 覆盖 no-tool、clarify、hard negative、multi-tool、
      auth/risk/error/long-output/injection/trajectory；
- [ ] trace completeness 100%，safety/authorization/stale/duplicate violations 为 0；
- [ ] independent evaluator 不接收 actor Recall Context，evaluation cache 也不以其为
      输入；
- [ ] evaluator cache 正向绑定 opaque terminal input、private labels、full contract、
      evaluator implementation/configuration 与 evidence projection schema；任一变化
      miss，而 private-only 变化不扰动 actor cache；
- [ ] actor case 与 evaluator-private labels 物理隔离；MetricSpec/ReleaseCriteria、
      power/CI/threshold 在 adaptive 解盲前冻结；
- [ ] end-state noninferiority、selection、schema budget、latency/cost gates 全过；
- [ ] provided-idea 和 reference-ideation flow 都使用共同目标路径；
- [ ] `case_*`/`transfer_*` 不再是 Tool Capabilities；
- [ ] direct callable dispatch、global overwrite/eager import、public旧 search、重复
      ToolModule authority 与 migration session 已从 production 删除；
- [ ] rollout、integrity incident quarantine、replay-compatible durable rollback drill、
      acceptance manifest 和 raw artifacts 完成；
- [ ] governing design/index/README 状态与实际代码一致。

## 14. 明确非目标与后续项

本轮交付不要求：

- MCP registry/server marketplace、A2A 或跨组织 tool sharing；
- remote learned router、fine-tuning、RL；
- distributed/parallel tool DAG；
- schema compression；
- active Research Run 热安装新工具；
- 把 Runtime recovery 或 token reduction 描述成 research intelligence gain。

只有 T8 完成且 verified traces 足够后，后续 policy version 才可评估：remote reranker、
learned need-tool gate、tool dependency graph learning、并发 wave、programmatic calling
和 schema compression。每一项都必须作为独立 Intervention，在相同 Evaluation
Contract/Budget Envelope 下产生 Observation 与 Verification Record。
