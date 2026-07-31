# Experience Gain 下一轮改进计划

状态：调研结论与实验设计草案

日期：2026-07-29

范围：AI-Researcher 的经验记录、知识晋升、召回、闭环试验和 One-layer VQ 评测

配套交付：[Phase A 代码级实施规格](experience-gain-v3-phase-a-spec.md)

## 1. 执行摘要

上一轮实验可靠地证明了三件事：

1. 经验可以被记录、晋升和再次召回；
2. 30 次真实 CIFAR-10 训练都生成了可由独立评估器验证的原始证据；
3. 五个配对种子中，Treatment 的确在第 2、3 次迭代分别召回了 1、2 条知识，而 Control 始终为 0。

但它没有检验“经验是否能提升研究结果”。根因不是简单的“模型没学会”，而是处理组和对照组最终执行了同一份训练实现与同一套配置。经验只能改变提示词中的引用和父记录，不能改变真正运行的干预。因此，这是一项**闭环机制 smoke test**，不是一项有效的 Experience Gain 因果试验。

最重要的证据如下：

- 5 个种子、10 个 arm、30 次尝试全部通过外部原始证据验证；
- Control 与 Treatment 的平均 `codebook_utilization` 都是 `0.040625`，五个配对差值全部为 `0`；
- Treatment 的召回条数为 `[0, 1, 2]`，但 30 次执行的 `source_sha256` 只有一个唯一值；
- 30 条被晋升的 Knowledge Record 的 `lesson` 完全相同，都是“冻结合同已执行，科学解释交给独立评估器”；
- 30 个尝试记录的 `code_revision` 各不相同，但真正执行的源码摘要完全相同，说明当前 revision 混入了运行产物，不能代表执行差异；
- 10 个 trial 的结构化研究质量报告全部 `passed=false`、`evidence_coverage=0`，但 30 次经验仍全部通过知识晋升；
- 训练总时间约 109.42 秒，只占正式 trial 总墙钟时间 26,568.60 秒的约 0.41%；绝大部分时间消耗在重复的 Agent 全流程，而不是训练。

因此，下一轮不应该直接再跑一组 5-seed 对照实验。正确顺序是：

> 先建立真实可执行的干预 Seam，再证明召回会改变决策和执行配置，再校准一个对干预敏感的 VQ 预算与指标，最后才进行冻结记忆、使用新种子的确认性试验。

## 2. “收益尚未闭环”到底是什么意思

一条可主张收益的完整链路至少包含：

```text
历史证据
  → 提炼出可执行知识
  → 在相关决策点精确召回
  → 改变本轮干预选择
  → 改变实际执行的源码或配置
  → 外部评估器观察到可归因的结果差异
  → 新证据反过来更新或淘汰知识
```

上一轮实际走通的是：

```text
历史证据
  → 复制成通用模板句
  → 召回模板句
  → 假设记录多了 citation/parent
  → 冻结入口恢复同一份源码并执行同一配置
  → 得到同一分布的结果
```

所以“收益尚未闭环”不是说“收益很小”，而是说链路中最关键的两个因果箭头还没有成立：

1. `Recall → Decision change`
2. `Decision change → Executed intervention change`

只统计召回条数不能替代这两个操纵检查。

## 3. 上一轮实验审计

### 3.1 已经成立的结论

正式合并审计文件为本地生成的
`benchmark/runs/one_layer_vq_closed_loop_v2_final_20260727_combined_audit.json`（实验产物不纳入版本控制）。

| 项目 | 审计结果 |
|---|---:|
| 模型 | `openai/DeepSeek-V4-Pro` |
| 配对种子 | 401、502、603、704、805 |
| Trial | 10 |
| Attempt | 30 |
| 有效外部验证 | 30 / 30 |
| Control 均值 | 0.040625 |
| Treatment 均值 | 0.040625 |
| 五个 paired delta | 全部 0 |
| LLM 调用 | 1,335 |
| LLM token | 12,898,392 |
| 正式 trial 墙钟时间之和 | 26,568.600932 秒，约 7.38 小时 |
| 当时完整测试 | 330 passed |

这里能主张的是：

- 原始训练证据是真实且完整的；
- 账本、召回、重试和外部验证的 Plumbing 能运行；
- 在这个冻结实现下，提供当前形式的 recalled text 没有带来指标改善。

这里不能主张的是：

- “经验学习对研究任务无效”；
- “DeepSeek-V4-Pro 无法从经验中学习”；
- “SimVQ 方法无效”；
- “更多种子也一定是零收益”。

这些更强的结论都要求处理组实际执行了不同的、由经验引导的干预。

### 3.2 核心设计缺陷：干预被冻死

[`run_infer_plan.py`](../../research_agent/run_infer_plan.py) 中的 `FROZEN_VQ_TEMPLATES` 把 `protocol.py` 和 `run_training_testing.py` 指向受信模板；`run_frozen_vq_protocol` 在每次训练前恢复这两个文件。

同时，[`ml_agent.py`](../../research_agent/inno/agents/inno_agent/ml_agent.py)：

- 明确要求模型不得修改冻结文件；
- 在 frozen mode 下移除了写文件和执行命令的工具。

这对保护评估完整性是合理的，但目前冻结层级过高。合同文本允许“Recall Context 有理由时做有记录的更改”，实现却没有留下任何可更改的配置入口。

审计 30 个 `evaluation_manifest.json` 后，执行源码摘要只有：

```text
33c707aee7fc0051690f104a8499478b70743faa652f9a53125b474231d6976a
```

即：处理组虽然看到了更多记忆，真正执行的训练程序没有变化。零差值是这一设计的预期结果，而不是对记忆价值的有效否证。

### 3.3 知识不是“可行动知识”

[`knowledge.py`](../../research_agent/inno/experience/knowledge.py) 当前直接把 `experience.analysis` 复制成 `KnowledgeRecord.lesson`。

冻结试验又在 [`run_infer_plan.py`](../../research_agent/run_infer_plan.py) 中把每次 analysis 固定为：

```text
Frozen evaluation contract executed. Scientific interpretation is deferred
to the independent evaluator over the preserved raw evidence.
```

因此 30 条被晋升的知识只有一个唯一 lesson。它没有说明：

- 在什么条件下；
- 哪个决策点；
- 把哪个旋钮从什么值改成什么值；
- 预期改变哪个指标；
- 实际效应和 guardrail 是什么；
- 哪些独立种子支持或反驳它。

当前 `KnowledgeGate` 还会因为同任务、同 outcome 的重复记录，把 confidence 每次提高 0.1。重复同一个负结果因此会被误当成更多独立支持，即使没有新的干预或新的因果信息。

### 3.4 召回相关性低且没有去重

[`retrieval.py`](../../research_agent/inno/experience/retrieval.py) 主要通过 query 与 lesson/conditions 的词面重叠排序，然后加入 outcome、confidence、recency 和较弱的 redundancy penalty。

本轮 15 个 treatment recall item 的 relevance 全部约为 `0.02272727`。完全相同的模板知识仍可被多次选择；系统没有先按“决策点和可用旋钮”做硬过滤，也没有按规则家族去重或执行 supersede。

结果是“召回数量增加”，但“能指导当前选择的信息量”没有增加。

### 3.5 科学证据有效，不等于研究经验可复用

示例结构化报告位于本地生成的
`benchmark/runs/one_layer_vq_closed_loop_v2_final_20260727_r19/seed-805/treatment/cache_one_layer_vq_openai__DeepSeek-V4-Pro/evals/report.json`，它
显示：

- 目标是 `deliver an executable research plan`；
- `passed=false`；
- `evidence_coverage=0.0`；
- 有效研究引用为 0。

10 个最终 trial 都是这一结果。但每次训练只要退出码正常、原始证据可验证、outcome 是 positive/negative，就仍可通过 `KnowledgeGate`。

当前系统混淆了两类质量：

1. **Scientific verification**：训练数据、指标和证据是否真实；
2. **Knowledge usability**：从这次运行提炼出的经验是否新颖、可行动、可归因、可复用。

两者都必须通过，才能晋升为长期语义知识。

### 3.6 Provenance 不能代表真实执行差异

[`experience_adapter.py`](../../research_agent/runtime/experience_adapter.py) 在 Flow 结束后对整个 project tree 计算 `code_revision`，只忽略极少数结果文件。

运行日志、生成产物、缓存或其他非源码内容都可能改变这个摘要。于是审计中出现：

- `attempt_code_revision`：30 个唯一值；
- 真正执行的 `source_sha256`：1 个唯一值。

这会给分析者造成“每次尝试实现都不同”的错误印象。下一版必须拆分：

- `source_digest`：受控执行源码；
- `intervention_digest`：本次可执行干预；
- `environment_digest`：依赖、硬件和运行环境；
- `dataset_digest`：数据及样本选择；
- `evidence_digest`：运行后原始证据。

源码与干预摘要应在执行前计算并写入不可变 manifest，而不是在整套 Flow 结束后对混杂目录取摘要。

### 3.7 成本结构失衡

[`improvement_cycle.py`](../../research_agent/runtime/improvement_cycle.py) 每次迭代都会调用同一个 `run_attempt`。而 [`run_infer_plan.py`](../../research_agent/run_infer_plan.py) 的 `run_attempt` 每次新建完整 `InnoFlow`，重复 prepare、survey、plan、implement、judge、submit、analyze。

审计结果：

| 成本指标 | 总计 | 每 trial 平均 | 每 attempt 平均 |
|---|---:|---:|---:|
| LLM token | 12,898,392 | 1,289,839 | 429,946 |
| LLM call | 1,335 | 133.5 | 44.5 |
| 正式墙钟 | 26,568.60 秒 | 44.28 分钟 | 14.76 分钟 |
| 实际训练 | 109.42 秒 | 10.94 秒 | 3.65 秒 |

训练只占墙钟约 0.41%。下一轮首先应该深化循环 Module，让一次研究准备可以服务多个实验尝试，而不是继续增加并行或 GPU。

### 3.8 当前 VQ smoke 对方法变化不够敏感

[`ONE_LAYER_VQ_REAL_TEST.md`](one-layer-vq-real-test.md) 已明确：

- 当前是 CIFAR-10、8192 个训练样本、2 epoch、codebook size 128；
- 初步 3-seed 中 vanilla 与 SimVQ-style 的平均 utilization 都是 5.208%；
- 这是 method smoke，不是论文复现。

而 [SimVQ 原论文](https://arxiv.org/abs/2411.02038) 的核心结果来自更大数据、训练预算和 codebook；论文常用的 ImageNet 128×128 设置训练 50 epoch，默认 codebook size 为 65,536。当前 2-epoch 小型 smoke 很可能只足以验证执行，不足以区分合理干预。

当前合同中的 `baseline: 0.95` 也明确只是为了强制三次等预算迭代，并非校准得到的期望值。所有 attempt 必然被标成 negative，系统因而没有正负干预对比可学。

## 4. 外部研究给出的设计约束

### 4.1 Reflexion：反馈必须回到下一次决策

[Reflexion](https://arxiv.org/abs/2303.11366) 的关键不是“存了一段反思”，而是 Actor、Evaluator、Self-Reflection 形成闭环：反思来自奖励和完整 trajectory，并在下一次 trial 被 Actor 消费以改变行为。

对本项目的约束：

- 记忆是否存在不是终点；
- 必须记录“记忆是否改变了下一次决策”；
- 评估信号、trajectory、反思和下一次行动要能逐条追踪。

### 4.2 ExpeL：从对比经验提炼，而不是复制单条分析

[ExpeL](https://arxiv.org/abs/2308.10144) 把训练阶段的经验收集与未见任务上的评估分开；它从成功/失败对比和多个成功 trajectory 中提炼 insight，并允许 ADD、EDIT、UPVOTE、DOWNVOTE，权重降到零时删除。论文消融还表明，结构化 insight 与相似成功轨迹可以互补，而未经约束的 raw reflection 可能因幻觉伤害效果。

对本项目的约束：

- episodic experience 和 semantic knowledge 必须分层；
- knowledge 应由多条对比证据蒸馏，而不是 `analysis` 的逐条复制；
- 支持、反驳、编辑、降权和遗忘都是一等操作；
- 确认性评估开始前冻结 memory，避免边测边学造成泄漏。

### 4.3 AWM：有用记忆应包含可执行动作结构

[Agent Workflow Memory](https://arxiv.org/abs/2409.07429) 学习并选择性提供可复用 workflow；workflow 不只是说明文字，还承载状态、推理与动作步骤。它支持从训练样例离线诱导，也支持在线诱导，并在 WebArena 上同时提升成功率和减少成功任务的步骤数。

对本项目的约束：

- Knowledge Record 要描述决策点和可执行动作；
- 召回后必须能映射到受控干预；
- 收益评估应同时测质量和效率。

### 4.4 MemoryAgentBench：召回不是 Test-Time Learning

[MemoryAgentBench](https://arxiv.org/abs/2507.05257) 将 memory 能力拆成准确召回、test-time learning、长程理解和选择性遗忘。其重要启示是：找回事实只证明 retrieval，test-time learning 要证明交互历史更新了行为策略。

对本项目的约束：

- Plumbing 指标和 Learning 指标必须分开报告；
- 要设计 zero-memory / full-memory gap 和选择性遗忘测试；
- “召回 2 条知识”本身不能作为 Experience Gain 的代理指标。

### 4.5 GEPA：反思应生成并比较可验证候选

[GEPA](https://arxiv.org/abs/2507.19457) 用轨迹反馈诊断问题、提出并测试修改，并维护 Pareto frontier。对本项目最有价值的不是照搬 prompt evolution，而是把“反思”落到可验证候选及多目标比较上。

对本项目的约束：

- 每条反思要落到一个候选干预；
- 候选必须执行和评估，而不是只修改自然语言假设；
- 质量、guardrail 与成本应共同进入 frontier。

## 5. 推荐的架构深化

以下候选通过 deletion test：如果删除它们，核心闭环、因果归因或结果可信度会消失；因此它们应成为有深度的 Module，而不是继续往 prompt 中追加文字。

### 5.1 Adaptive Experiment Module（P0）

**Files**

- `research_agent/runtime/improvement_cycle.py`
- `research_agent/run_infer_plan.py`
- `research_agent/inno/experience/models.py`
- VQ protocol 与 contract

**Problem**

当前循环 Module 的 Interface 只表达“重复运行并重新召回”，Implementation 却重跑完整研究 Flow。冻结 protocol 后，又没有任何合法干预 Seam，导致 recall 无法影响执行。

**Solution**

保持评估器、数据身份、codebook size 和核心训练源码冻结，但增加一个受 schema 约束、带摘要、可审计的 `intervention` artifact。Agent 只能从预声明旋钮中选择值，不能任意改评估或数据。

循环由以下步骤组成：

```text
recall
  → propose intervention
  → validate schema and allowed range
  → compare with previous intervention
  → execute frozen runner with intervention
  → verify raw evidence
  → reflect and update episodic record
```

**Benefits**

- 建立 `Recall → Decision → Execution` 的真实 Seam；
- 冻结科学评估的同时允许受控适应；
- 提高 Locality，避免一次旋钮变化牵动整个研究 Flow；
- 一个 Module 改善所有后续 closed-loop benchmark，Leverage 高。

### 5.2 Comparative Knowledge Distillation Module（P0）

**Files**

- `research_agent/inno/experience/knowledge.py`
- `research_agent/inno/experience/models.py`
- `research_agent/inno/experience/ledger.py`

**Problem**

当前 Implementation 把单次 `analysis` 直接变成知识；重复同 outcome 会提高 confidence，缺少干预多样性、独立种子和反证要求。

**Solution**

保留两层记录：

1. Episodic Experience：忠实记录每次 hypothesis、intervention、observation、verification；
2. Semantic Knowledge：从多条可比较经验中蒸馏出的规则。

每条 active semantic rule 至少应承载：

- 适用条件与决策点；
- 干预旋钮、from/to；
- 预期机制和指标方向；
- 观察到的主指标与 guardrail 效应；
- 独立种子数和 source experience IDs；
- 支持证据、反驳证据；
- active、superseded 或 rejected 状态。

晋升必须同时满足：

- 外部验证有效；
- 结构质量通过；
- 可行动；
- 相比现有规则有新信息；
- 支持来自独立种子或明确的 A/B 对比；
- 不把同一次干预的重复运行误算成独立支持。

纯负面 episode 可以留在 episodic ledger，但在形成“条件—动作—效应”对比前不得成为 active semantic knowledge。

**Benefits**

- 深化 Knowledge Module，使其隐藏证据合并和矛盾处理复杂度；
- 防止无意义模板污染长期记忆；
- 支持 edit、supersede、downvote 和 selective forgetting；
- confidence 重新具有可解释含义。

### 5.3 Decision-Point Retrieval Module（P1）

**Files**

- `research_agent/inno/experience/retrieval.py`
- `research_agent/runtime/research_pipeline.py`

**Problem**

当前排序以宽泛词面相似度为主，重复规则可同时出现，recall item 与本轮可修改旋钮之间没有强关联。

**Solution**

分两阶段检索：

1. 硬过滤：task/domain、dataset、model family、decision point、knob applicability、active state；
2. 软排序：语义相关性、独立支持度、效应大小、反证、recency 和 diversity。

同一 rule family 只返回一个 active 版本；最多返回 3 条互补规则。最终决策必须说明：

- 采用或拒绝了哪些 citation；
- 每条被采用 citation 映射到哪个旋钮变化；
- 未采用的高分规则为什么不适用。

关键词索引和 Chroma 是这一 Module 的两个 Adapter，应保持可替换，而不是让调用方理解两套检索细节。

**Benefits**

- 提高 retrieval precision 和可解释性；
- 减少重复 token；
- 为 selective forgetting 提供清晰位置；
- 让记忆采用率可直接测量。

### 5.4 Trial Provenance Module（P0）

**Files**

- `research_agent/runtime/experience_adapter.py`
- 外部 evaluator 与 manifest 生成逻辑

**Problem**

当前 `code_revision` 混入运行产物，无法区分“执行源码变化”“配置变化”和“证据变化”。

**Solution**

在执行前固化独立摘要：

- source；
- intervention/config；
- dataset/sample selection；
- environment/dependencies；
- evaluator/contract。

执行后单独固化 evidence digest。所有摘要写入外部评估器可见的 manifest。

增加 manipulation check：

- 相邻 attempt 的 intervention digest 相同，则标记 `no_effect_decision`；
- Pilot 阶段可直接停止无意义重复；
- Confirmatory 阶段仍保留该 pair，并按 intention-to-treat 计为零效果或 policy failure，不能事后删除。

**Benefits**

- 结果具备真正的可归因性；
- 能自动发现“提示变了、执行没变”；
- 避免运行产物伪装成代码变化；
- 为缓存、复现和对照审计提供稳定 Interface。

### 5.5 Benchmark Harness Module（P1）

**Files**

- `benchmark/run_one_layer_vq_closed_loop_v2.py` 的下一版
- contracts、auditor 和 evaluator

**Problem**

当前 memory 在线增长，任务准备和试验执行混在一起；虽然 arm 隔离较好，但没有开发/评估记忆分离，也没有 pre-run manipulation gate。

**Solution**

- development seeds 用于生成和筛选知识；
- evaluation seeds 永不进入开发 memory；
- 确认性阶段使用只读、带 digest 的 frozen memory snapshot；
- 每个 attempt 使用 clean workspace；
- 两个 arm 都收到相同的最近一次 raw observation；
- Treatment 额外收到 semantic memory，Control 不收到；
- 模型、温度、预算、arm order 和 evaluator 完全一致；
- evaluator 对 arm 身份盲化；
- 历史只通过显式 artifact 传入，禁止借助残留文件泄漏。

**Benefits**

- 将 Test-Time Learning 的因果对照变成 Harness 的默认能力；
- 防止边测边学和跨 arm 污染；
- 让失败能定位在 Plumbing、Policy 或 Outcome 层。

### 5.6 Stage Continuation Module（P1）

**Files**

- `research_agent/runtime/improvement_cycle.py`
- `research_agent/run_infer_plan.py`
- stage cache/state 管理

**Problem**

每个 attempt 都重跑完整 InnoFlow，导致 99% 以上时间花在不随干预变化的 Agent 阶段。

**Solution**

一次研究任务只执行一次 prepare、survey 和 method review。后续 attempt 从不可变 research context 继续，只运行：

```text
diagnose → choose intervention → execute → verify → reflect
```

把 target 设为：

- 每 attempt 不超过 5–7 次 LLM 调用；
- 每 trial 不超过 100k token；
- 相比当前 133.5 calls / 1.29M tokens 每 trial，调用减少至少 90%，token 减少至少 80%。

**Benefits**

- 大幅提高 Depth：循环 Module 隐藏 continuation、cache 和恢复逻辑；
- 降低成本后才能负担足够的新种子；
- 使预算真正用于候选比较，而不是重复写研究计划。

## 6. V3 实验设计

### 6.1 冻结什么，开放什么

继续冻结：

- evaluator 和 contract；
- 数据集身份、split 和样本顺序；
- seed；
- codebook size；
- train sample count；
- 原始证据格式；
- reconstruction guardrails；
- frozen runner 源码。

通过受控 `intervention` artifact 开放：

- projection learning-rate multiplier；
- commitment weight；
- basis / coefficient 的 trainability policy；
- basis initialization；
- latent normalization；
- 其他经过 sensitivity sweep 证明会影响指标且不改变任务定义的旋钮。

不开放 codebook size。主指标是 utilization ratio 时，更改分母会直接“做高”指标，构成 metric gaming。

每个 proposal 必须写清：

- 引用的 knowledge IDs；
- 决策点；
- 旋钮；
- from/to；
- 预期主指标方向；
- 可能伤害的 guardrail；
- proposal 和 config digest。

### 6.2 两个 arm 的最小公平差异

Control 与 Treatment 都获得：

- 相同任务；
- 相同即时 raw observation；
- 相同历史长度上限；
- 相同模型、温度和 token budget；
- 相同可用旋钮和 schema；
- 相同执行与验证工具。

唯一差异：

- Control：无 semantic memory；
- Treatment：可读取 development 阶段冻结的 semantic memory snapshot。

这比“Control 什么反馈都没有”更严格，因为它隔离的是长期经验的增益，而不是即时失败反馈的增益。

### 6.3 操纵检查

正式训练前必须自动回答：

1. Treatment 是否召回了适用规则？
2. 决策是否明确采用了至少一条规则？
3. citation 是否映射到实际 config change？
4. Treatment intervention digest 是否区别于自己的上一轮？
5. 在配对层面，Treatment policy 是否比 Control 更常选择已知更优干预？
6. evaluator manifest 是否观察到了相同的 digest？

Pilot 可以并行生成一个不执行的 shadow no-memory decision，用来估计 memory adoption；确认性试验不得根据 shadow 结果筛掉不理想样本。

### 6.4 指标分层

**Plumbing**

- recall precision；
- applicable recall rate；
- citation-to-action mapping rate；
- intervention adoption rate；
- distinct intervention rate；
- no-op rate；
- cross-arm leakage rate。

**Learning**

- 在 reconstruction guardrail 下的 best valid normalized codebook perplexity；
- final / best active-code utilization；
- improvement AUC；
- attempts-to-threshold；
- repeated-negative rate；
- treatment-control paired delta。

**Efficiency**

- token / valid improvement；
- calls / valid improvement；
- wall time / valid improvement；
- 无效重复的占比。

建议优先校准 `normalized codebook perplexity = perplexity / codebook_size` 作为候选主指标。utilization 对 codebook size 128 的步长是 1/128，且一个仅出现一次的 code 与高频稳定使用的 code 权重相同，灵敏度偏低。最终主指标必须在 sensitivity 阶段结束后、确认性数据揭盲前预注册。

### 6.5 分层 Gate 与停止条件

#### Gate 0：已知响应面的廉价任务

先用一个 hidden-response synthetic config task 验证 Test-Time Learning 机制：

- 环境中存在可学习的旋钮—奖励关系；
- Treatment 可访问结构化经验；
- Control 只访问即时 observation；
- 目标是证明 Treatment 会更新 policy 并更快接近已知最优值。

通过条件：

- memory 显著改变决策；
- 采用的规则能映射到实际 config；
- Treatment 在未见 seed 上优于 Control。

失败则停止，不进入 VQ。

#### Gate 1：VQ sensitivity / oracle sweep

不用 LLM 重型 Flow，直接对 development seeds 做小型网格或自适应 sweep：

- epoch：2 / 5 / 10 / 20；
- 预声明的若干安全旋钮；
- 固定 codebook size、数据和 guardrail。

目标是找到最小预算，使至少一个允许干预对候选主指标产生稳定、可检测的响应。鉴于论文实验常用 50 epoch，2 epoch 不应被默认视为足够。

通过条件：

- 至少一个旋钮在多个 development seeds 上产生方向稳定的效应；
- reconstruction guardrails 不被破坏；
- 指标的 seed 方差和最小有意义效应可估计。

失败则更换预算或任务，不做 memory A/B。

#### Gate 2：离线知识审计

通过条件：

- active semantic rules 中 exact duplicate 为 0；
- 100% 有可验证 source experience IDs；
- 至少 90% 能映射到一个允许旋钮；
- 每条确认性规则有独立种子支持或明确的 paired contrast；
- 矛盾证据会降低权重、阻止晋升或 supersede 旧规则；
- 失效规则不会被 retrieval 返回。

#### Gate 3：操纵 Pilot

建议先用 6–8 个新配对种子。

通过条件：

- 至少 80% Treatment 决策产生合法且非 no-op 的干预；
- 至少 80% 被采用 citation 映射到实际 config change；
- 所有执行 manifest 的 digest 与 proposal 一致；
- cross-arm / cross-seed leakage 为 0；
- LLM call 至少下降 90%，token 至少下降 80%；
- 指标显示足以支持样本量估计的非退化方差。

任一关键操纵条件失败，停止并修 Module，不得用更多种子补救设计缺陷。

#### Gate 4：确认性试验

- memory snapshot 冻结；
- 使用全新 evaluation seeds；
- 主指标、guardrails、停止规则和分析方法预注册；
- 所有 pair 按 intention-to-treat 保留；
- evaluator 对 arm 盲化；
- 同时报 paired effect、置信区间、有效率和资源成本。

若置信区间包含 0，或 manipulation check 失败，不主张 Experience Gain。

## 7. 样本量与统计分析

不要再次任意选择 5 个种子作为确认性规模。

推荐流程：

1. 用 8 个左右的 Pilot pair 估计配对差值标准差 `σΔ`；
2. 预先定义最小有意义效应 `δmin`；
3. 以双侧 `α=0.05`、power 0.8 粗算：

```text
n = ceil((1.96 + 0.84)^2 × σΔ² / δmin²)
```

4. 根据成本将确认性范围预先限制在 12–40 个 fresh pairs；
5. 报告 paired bootstrap 置信区间和 exact paired permutation test；
6. 若分布大量 ties 或零膨胀，同时报告 adoption/no-op 的二项指标；
7. Pilot seeds 不进入确认性结果，除非在看结果前明确预注册合并规则。

统计显著性不是唯一 Gate。如果 Treatment 根本没有改变干预，哪怕偶然出现 outcome 差异，也不能解释为记忆收益。

## 8. 推荐的实验臂

开发性 Pilot 可做四臂消融：

| Arm | 即时 raw observation | 通用 prose memory | 结构化 intervention memory | 成功 trajectory |
|---|---:|---:|---:|---:|
| A | 是 | 否 | 否 | 否 |
| B | 是 | 是，当前 legacy | 否 | 否 |
| C | 是 | 否 | 是 | 否 |
| D | 是 | 否 | 是 | 是 |

目的：

- A vs B：确认当前通用模板是否确实无效；
- A vs C：测结构化语义知识的净收益；
- C vs D：测成功 trajectory 是否提供额外信息。

确认性试验只保留 A 和开发阶段预先选定的最佳 Treatment，避免多重比较和成本膨胀。

## 9. 实施路线图

### Phase A：先打通真实因果 Seam（2–3 engineer-days）

- 引入 schema 化 intervention artifact；
- 拆分 provenance digests；
- 在执行前做 no-op / duplicate manipulation check；
- manifest 记录 intervention digest；
- 增加单元与集成测试。

验收：

- 同一 source、不同 config：source digest 相同，config digest 不同；
- 生成日志或产物不能改变 source digest；
- recalled rule 能导致实际执行 config 改变；
- evaluator 能看到并核对 config digest。

### Phase B：校准响应面与预算（2–4 days）

- 不运行完整 Agent Flow；
- 对安全旋钮和 2/5/10/20 epoch 做 development sweep；
- 选择有响应且 guardrail 合格的最小预算；
- 冻结候选主指标与 `δmin`。

验收：

- 至少存在一种已知更优和一种已知更差干预；
- 指标不是全 ties；
- 能构造隐藏响应面 Gate 0 和 VQ Gate 1 的 oracle。

### Phase C：深化知识与检索（3–5 days）

- episodic / semantic 分层；
- comparative distillation；
- promotion quality gate；
- rule family dedupe、supersede 和 forgetting；
- decision-point retrieval；
- 构建只读 development memory snapshot。

验收：

- 通用无动作 lesson 被拒绝；
- 重复同一 experience 不提高独立支持度；
- 反证可以降权或 supersede；
- retrieval 只返回适用、不同规则；
- trace replay 能重现同一决策输入。

### Phase D：Pilot 与 Gate 审计（1–2 days + compute）

- 先 Gate 0；
- 再 6–8 对 VQ Pilot；
- 自动生成 manipulation、quality、cost 三类报告；
- 根据 Pilot 方差计算确认性样本量。

### Phase E：确认性试验

只有 Gate 0–3 全部通过才启动。否则继续修设计，不再靠长时间运行掩盖不可识别问题。

## 10. 测试清单

### Provenance

- [ ] source digest 只覆盖受控执行源码；
- [ ] config digest 对任一允许旋钮变化敏感；
- [ ] output/log/cache 变化不影响 source digest；
- [ ] proposal、runner、manifest、evaluator 中的 digest 一致；
- [ ] clean workspace 下可复现。

### Knowledge promotion

- [ ] generic/no-action lesson 被拒绝；
- [ ] invalid external evidence 被拒绝；
- [ ] structural evidence coverage 不合格时不晋升 semantic rule；
- [ ] 重复干预不会虚增 independent support；
- [ ] contradiction 会阻止、降权或 supersede；
- [ ] negative episode 可保留但不会自动变 active rule。

### Retrieval

- [ ] 按 decision point 和 knob applicability 硬过滤；
- [ ] rule family 去重；
- [ ] inactive/superseded rule 不返回；
- [ ] citation 能映射到动作；
- [ ] selective forgetting 有回归测试。

### Manipulation

- [ ] Treatment recall 可改变 decision；
- [ ] decision 可改变执行 config；
- [ ] no-op 被明确记录；
- [ ] shadow counterfactual 只用于 Pilot 诊断；
- [ ] Confirmatory 不删除 no-op pair；
- [ ] arm 和 seed 之间无隐式文件泄漏。

### Efficiency

- [ ] prepare/survey/method review 每个任务只运行一次；
- [ ] 每 attempt 最多 5–7 次 LLM 调用；
- [ ] 每 trial 不超过 100k token；
- [ ] 超预算自动停止并保留可诊断记录。

## 11. 明确不做什么

- 不直接重跑第三轮相同的 5-seed immutable-config 实验；
- 不再把召回条数当作 Experience Gain；
- 不仅因为 external verification valid 就晋升知识；
- 不用不可达的 0.95 baseline 单纯强制重试；
- 不在每个 attempt 重跑完整研究 Flow；
- 不在确认性阶段让 memory 随 evaluation seeds 增长；
- 不通过改变 codebook size、数据或 seed 来做高 utilization；
- 不事后删除 Treatment 没采用记忆的 pair；
- 不在操纵检查失败时用更多样本弥补。

## 12. 优先级与最终建议

推荐顺序不是“先优化 prompt”，而是：

1. **P0：Adaptive Experiment Module + Trial Provenance Module**

   让经验第一次真正能够改变可执行干预，并证明它确实改变了。

2. **P0：Comparative Knowledge Distillation Module**

   阻止模板句进入长期记忆，建立条件—动作—效应知识。

3. **P1：Stage Continuation Module**

   把单 trial 成本降一个数量级，释放足够的种子预算。

4. **P1：Decision-Point Retrieval + Benchmark Harness**

   冻结开发知识，以严格对照验证 Test-Time Learning。

5. **最后才是确认性 VQ A/B。**

一句话决策：

> 下一步最值得实现的不是“更多记忆”，而是“一个受控、可审计、会被记忆改变的实验干预 Interface”；在它通过操纵 Gate 前，不应再启动长时间正式跑。

## 13. 一手资料

- [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366)
- [ExpeL: LLM Agents Are Experiential Learners](https://arxiv.org/abs/2308.10144)
- [Agent Workflow Memory](https://arxiv.org/abs/2409.07429)
- [Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions / MemoryAgentBench](https://arxiv.org/abs/2507.05257)
- [GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning](https://arxiv.org/abs/2507.19457)
- [Addressing Representation Collapse in Vector Quantized Models with One Linear Layer / SimVQ](https://arxiv.org/abs/2411.02038)
