# 分布式Agent执行模式：框架与方案研究报告

**报告日期**: 2026年3月15日
**项目**: AI-Researcher
**研究主题**: 分布式环境中的Agent编排、协调与执行

---

## 目录
1. [框架对比总览](#框架对比总览)
2. [主流框架详解](#主流框架详解)
3. [核心概念与架构](#核心概念与架构)
4. [与LangGraph的集成](#与langgraph的集成)
5. [AI-Researcher应用建议](#ai-researcher应用建议)

---

## 框架对比总览

### 框架对比表

| 框架 | 设计目标 | 核心模型 | 执行范式 | 适用场景 | 学习曲线 |
|------|--------|--------|--------|--------|--------|
| **Ray** | 通用分布式计算 + AI/ML | Actor模型 + Task | 基于Actor + 任务 | 多Agent系统、多GPU推理、ML训练 | 中等 |
| **Celery** | 任务队列与异步处理 | 任务队列 | 基于消息队列的任务分发 | 定时任务、后台处理、轻量级工作流 | 低 |
| **Dask** | 大数据处理并行化 | 任务图 + 任务调度 | 延迟求值(Lazy Evaluation) | 数据处理、大规模计算、ETL | 中等 |
| **LangGraph** | Agent工作流编排 | 状态图(StateGraph) | DAG + 条件路由 | 多Agent推理、工作流自动化 | 中等 |
| **CrewAI** | 多Agent角色协作 | 角色-任务框架 | 顺序/并行执行 | 协作型Agent系统 | 低 |

### 快速对比维度

```
分布式能力        |  Ray  |  Celery  |  Dask  |  LangGraph  |  CrewAI
----------------+-------+----------+-------+-------------+--------
跨机器执行        |   ★★★ |    ★★★   |  ★★★  |    ★★☆     |   ★☆☆
故障恢复机制      |   ★★★ |    ★★★   |  ★★☆  |    ★★☆     |   ★☆☆
动态资源管理      |   ★★★ |    ★★☆   |  ★★☆  |    ★★☆     |   ★★☆
Agent状态管理     |   ★★★ |    ★★☆   |  ★☆☆  |    ★★★     |   ★★★
条件路由/工作流   |   ★★☆ |    ★★☆   |  ★★★  |    ★★★     |   ★★★
生产就绪度         |   ★★★ |    ★★★   |  ★★★  |    ★★★     |   ★★☆
AI/ML友好度       |   ★★★ |    ★★☆   |  ★★☆  |    ★★★     |   ★★★
```

---

## 主流框架详解

### 1. Ray - 通用分布式计算引擎

#### 概述
Ray是UC Berkeley开发的分布式框架，专门优化AI/ML工作负载。它提供低延迟、高吞吐的分布式执行能力。

**核心统计**：
- 237M+ 下载量
- 支持百万级任务/秒
- 子毫秒级延迟
- OpenAI、Google、Amazon等产业级应用

#### 核心抽象

```python
# 1. Tasks - 无状态函数执行
@ray.remote
def process_data(data):
    return transform(data)

future = process_data.remote(data)
result = ray.get(future)

# 2. Actors - 有状态对象
@ray.remote
class DataProcessor:
    def __init__(self):
        self.state = {}

    def process(self, data):
        self.state[id(data)] = data
        return transform(data)

processor = DataProcessor.remote()
result = processor.process.remote(data)
```

#### 架构特点

1. **分层架构**
   - 驱动程序层：提交任务和Actor
   - 调度层：GCS(Global Control Store) + 本地调度器
   - 执行层：Worker进程，支持GPU/CPU隔离
   - 存储层：对象存储(Object Store)，支持分布式缓存

2. **Actor模型实现**
   ```
   ┌─────────────────────┐
   │   Driver Process    │
   │  (提交任务/Actor)    │
   └──────────┬──────────┘
              │
   ┌──────────▼──────────┐
   │   Global Control    │  GCS - 全局控制与元数据
   │     Store (GCS)     │
   └──────────┬──────────┘
              │
   ┌──────────▼──────────┐
   │   Local Scheduler   │  智能任务调度
   └──────┬──────────┬───┘
          │          │
    ┌─────▼──┐  ┌───▼─────┐
    │ Worker1│  │ Worker2 │  分布式执行
    │ Actor A│  │ Task X  │
    └────────┘  └─────────┘
   ```

3. **RayServe - 模型服务部署**
   - 支持多模型并发服务
   - 自动扩展与批处理
   - 异步推理与流式响应
   - LLM原生支持

#### 优势与应用

| 优势 | 应用场景 |
|------|--------|
| 异构计算(CPU+GPU) | 多卡推理、LLM服务 |
| 灵活的Actor模型 | 有状态Agent系统 |
| 毫秒级调度 | 实时数据处理 |
| 生产级可靠性 | 企业部署 |

#### 故障恢复机制
- **对象恢复**: 缓存丢失时自动重放计算
- **任务重试**: 指数退避重试策略
- **检查点**: 周期性状态保存

---

### 2. Celery - 分布式任务队列

#### 概述
Celery是Python生态最成熟的任务队列框架，基于消息代理(Broker)的拉模型。

**应用案例**: Instagram、Spotify、Stripe等大型企业

#### 核心概念

```python
# 1. 定义任务
@app.task
def send_email(user_id, subject):
    user = User.get(user_id)
    return send(user.email, subject)

# 2. 发送任务
task = send_email.delay(user_id, subject)

# 3. 获取结果
result = task.get()
status = task.status

# 4. 复杂工作流
from celery import chain, group, chord

# 链式执行: 任务A → 任务B → 任务C
workflow = chain(
    task_a.s(x),
    task_b.s(),
    task_c.s()
)

# 并行执行: 任务A、B、C同时运行
parallel = group([
    task_a.s(x),
    task_b.s(y),
    task_c.s(z)
])

# 扇出-扇入: 并行后汇聚
result = chord([
    task_a.s(x),
    task_b.s(y)
])(task_aggregate.s())
```

#### 架构设计

```
Producer          Broker          Consumer (Worker)
(Django/Flask)   (RabbitMQ/Redis)  (Celery Worker)
     │                │                  │
     ├─────task───────▶│                  │
     │                 ├──deliver─────────▶
     │                 │                  │ 执行任务
     │                 │◀──result result───┤
     │◀────────result───┤                  │
```

#### 关键特性

1. **消息代理支持**
   - RabbitMQ (生产推荐)
   - Redis
   - SQS
   - SQLite (开发环境)

2. **高级工作流编排** - Selinon
   ```python
   # 条件分支
   if result_a > threshold:
       execute(task_b)
   else:
       execute(task_c)
   ```

3. **重试与超时**
   ```python
   @app.task(autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
   def resilient_task():
       pass
   ```

#### 优势
- 成熟稳定，生产级验证
- 极低学习曲线
- 丰富的监控工具(Flower)
- 灵活的调度(Beat + Cron)

#### 劣势
- 无原生状态管理
- 分布式追踪困难
- 单任务粒度控制有限

---

### 3. Dask - 并行数据处理

#### 概述
Dask将大数据处理问题转化为任务图，实现**延迟求值(Lazy Evaluation)**。

#### 核心概念

```python
import dask.dataframe as dd
import dask.array as da
from dask.distributed import Client

# 1. Lazy计算 - 构建计算图
df = dd.read_csv('data/*.csv')
result = df.groupby('category').sum().compute()  # compute触发执行

# 2. 分布式执行
client = Client(processes=True, n_workers=4, threads_per_worker=1)
futures = client.compute([task1, task2, task3])
results = client.gather(futures)

# 3. 任务图可视化
dask_object.visualize('task_graph.png')
```

#### 执行流程

```
DAG构建阶段          调度阶段           执行阶段
━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━  ━━━━━━━━━━━━
df.map(fn)      → 任务调度器    → Worker并行执行
  ↓               (分析依赖)      (数据本地性)
df.filter(p)    → 优化计划      → 结果聚合
  ↓               (融合操作)
df.groupby(k)
```

#### 分布式架构

```
┌──────────────────────────────────┐
│      Dask Distributed Client     │
│   (Task Graph Submission)        │
└───────────┬──────────────────────┘
            │
┌───────────▼──────────────────────┐
│   Distributed Scheduler          │  集中式调度
│  (Task Scheduling & Tracking)    │
└───────────┬──────────────────────┘
            │
    ┌───────┴───────┐
    │               │
┌───▼────┐     ┌───▼────┐
│Worker 1│     │Worker 2│  分布式执行
│ (CPU)  │     │ (CPU)  │
└────────┘     └────────┘
```

#### 优势
- 与pandas/numpy兼容的API
- 自动化任务图优化
- 灵活的调度策略
- 大数据处理友好

#### 局限
- 主要面向数据处理，非Agent系统
- 无原生状态管理

---

### 4. LangGraph - Agent工作流编排

#### 概述
LangGraph是Anthropic设计的Agent运行时框架，专门优化AI Agent的多步推理和工作流编排。

**关键指标**：
- 支持跨语言执行(Python、JS)
- 40% 企业应用预计2026年采用Agent
- 原生Claude集成

#### 核心概念

```python
from langgraph.graph import StateGraph, START, END
from typing import TypedDict

# 1. 定义状态
class ResearchState(TypedDict):
    query: str
    papers: list
    summary: str
    analysis: str

# 2. 构建图
graph = StateGraph(ResearchState)

# 3. 添加节点(Agent或工具)
def search_papers(state):
    papers = arxiv_search(state["query"])
    return {"papers": papers}

def analyze_papers(state):
    analysis = llm_analyze(state["papers"])
    return {"analysis": analysis}

graph.add_node("search", search_papers)
graph.add_node("analyze", analyze_papers)

# 4. 添加边(条件路由)
graph.add_edge(START, "search")
graph.add_edge("search", "analyze")
graph.add_edge("analyze", END)

# 5. 编译并执行
runnable = graph.compile()
result = runnable.invoke({
    "query": "diffusion models"
})
```

#### 分布式执行模式

```
┌────────────────────────────────────────┐
│        LangGraph StateGraph            │
├────────────────────────────────────────┤
│                                        │
│  ┌─────────────────────────────────┐  │
│  │  Remote Node (Machine A)        │  │
│  │  - Agent执行                    │  │
│  │  - API调用                      │  │
│  └─────────────────────────────────┘  │
│                 │                      │
│  ┌──────────────▼───────────────────┐ │
│  │  State Sync & Routing            │ │
│  │  - 共享状态一致性                 │ │
│  │  - 条件分支执行                   │ │
│  └──────────────┬───────────────────┘ │
│                 │                      │
│  ┌──────────────▼───────────────────┐ │
│  │  Remote Node (Machine B)        │  │
│  │  - 并行Agent                     │  │
│  │  - 工具调用                      │  │
│  └─────────────────────────────────┘  │
│                                        │
└────────────────────────────────────────┘
```

#### 多Agent协调模式

**1. 串行模式(Sequential)**
```
Agent A → Agent B → Agent C
(依次执行，传递状态)
```

**2. 并行模式(Parallel - Scatter-Gather)**
```
        ┌─→ Agent A ─┐
Agent   ┤─→ Agent B  ├─→ Aggregator → Result
        └─→ Agent C ─┘
```

**3. 分层模式(Hierarchical)**
```
┌─ Master Agent
│  ├─→ Specialized Agent 1
│  ├─→ Specialized Agent 2
│  └─→ Specialized Agent 3
└─→ Coordinator
```

#### 与分布式框架集成

```python
# 结合Ray的分布式执行
import ray
from langgraph.graph import StateGraph

@ray.remote
def run_agent_node(state):
    return agent.process(state)

# 自定义节点实现分布式运行
graph.add_node("distributed_search",
    lambda s: ray.get(run_agent_node.remote(s))
)
```

---

## 核心概念与架构

### 1. 分布式执行模型对比

#### Push模型 (Celery)
```
┌──────────┐      任务推送        ┌──────────┐
│ Producer ├──────────────────────▶ Broker   │
│          │      消息队列        │          │
└──────────┘                       └────┬─────┘
                                       │ 任务分发
                                   ┌───▼─────┐
                                   │ Worker  │ 拉取任务
                                   └─────────┘
```

**特点**：
- 消息驱动
- 异步非阻塞
- 原生支持任务重试

#### Pull模型 (Dask + Ray)
```
┌──────────┐      任务定义        ┌──────────┐
│ Driver   ├──────────────────────▶ Scheduler │
│          │      执行计划        │          │
└──────────┘                       └────┬─────┘
                                       │ 任务分配
                                   ┌───▼─────┐
                                   │ Worker  │ 主动拉取
                                   └─────────┘
```

**特点**：
- 数据驱动
- 任务图优化
- 智能调度

---

### 2. 负载均衡策略

#### Round-Robin (轮询)
- 等权分配任务
- 适合同质Worker

#### Weighted Round-Robin (加权轮询)
- 根据Worker能力加权
- 支持GPU/CPU差异

#### Dynamic Load Balancing (动态负载均衡)
```python
# Ray的例子
@ray.remote(num_gpus=1)
def gpu_task():
    pass

@ray.remote
def cpu_task():
    pass

# Ray自动根据资源可用性调度
```

#### Work Stealing (工作窃取)
- 闲置Worker主动获取其他Worker的任务
- 用于任务时间分布不均的场景

---

### 3. 故障恢复机制

#### Checkpoint-Based Recovery (检查点恢复)
```
运行状态 → 定期保存检查点 → 失败恢复
   │         │              │
   ├─T1      ├─CP1    失败──┼→ 恢复到CP1
   ├─T2      ├─CP2         │
   ├─T3      └─CP3         │
   └─失败                   └→ 重新执行T3
```

#### Replication (副本)
```
┌─────────┐
│ Task A  │
└──┬────┬─┘
   │    └──────┐
   ▼           ▼
┌──────┐   ┌──────┐
│Worker1│  │Worker2│ (副本)
└──────┘   └──────┘
```

#### Circuit Breaker Pattern (熔断器)
```
Healthy → Probing → Open
  ▲        │        │
  │        │        ▼
  │        └─────Recovering
  │              │
  └──────────────┘
```

---

### 4. 资源管理

#### Static Resource Allocation (静态分配)
```python
# Ray资源声明
@ray.remote(num_cpus=2, num_gpus=1, memory=2e9)
def gpu_intensive_task():
    pass
```

#### Dynamic Scaling (动态扩缩容)
```
Demand   ┌─────────────┐
  ▲      │             │      Scaling Out
  │      │   Active    │      ┌───┐
  │      │  Instances  │      │+2 │
  │      │             │      └───┘
  │      └─────────────┘
  │              │
  │              │ Idle
  │              ▼ Threshold
  │      ┌─────────────┐      Scaling In
  │      │             │      ┌───┐
  └──────│  Inactive   │      │-1 │
         │             │      └───┘
         └─────────────┘
```

#### Resource Pool Management
```
┌─────────────────────────────────┐
│  Cluster Resource Pool          │
├─────────────────────────────────┤
│                                 │
│ ┌──────┐  ┌──────┐  ┌──────┐   │
│ │ CPU  │  │ GPU  │  │Memory│   │
│ │Pool  │  │Pool  │  │Pool  │   │
│ └──────┘  └──────┘  └──────┘   │
│                                 │
│ Agent1  Agent2  Agent3          │
└─────────────────────────────────┘
```

---

## 与LangGraph的集成

### 1. LangGraph + Ray集成架构

#### 场景：多Agent研究系统

```python
"""
集成架构：利用Ray的分布式能力 + LangGraph的工作流编排
"""

import ray
from langgraph.graph import StateGraph
from typing import TypedDict

# 1. 初始化Ray集群
ray.init(num_cpus=8, num_gpus=2)

# 2. 定义分布式Agent
@ray.remote(num_cpus=1)
def literature_search_agent(state):
    """在远程Worker上运行的Agent"""
    query = state["research_query"]
    papers = arxiv_api_search(query)
    return {"papers": papers}

@ray.remote(num_cpus=2)
def analysis_agent(state):
    """GPU优化的Agent"""
    return analyze_papers(state["papers"])

# 3. 构建LangGraph工作流
class ResearchState(TypedDict):
    research_query: str
    papers: list
    analysis: str
    summary: str

graph = StateGraph(ResearchState)

# 关键：在LangGraph节点中调用Ray任务
def search_node(state):
    future = literature_search_agent.remote(state)
    result = ray.get(future)
    return result

def analysis_node(state):
    future = analysis_agent.remote(state)
    result = ray.get(future)
    return result

graph.add_node("search", search_node)
graph.add_node("analyze", analysis_node)

# 4. 路由和工作流定义
graph.add_edge("search", "analyze")

# 5. 执行
runnable = graph.compile()
result = runnable.invoke({
    "research_query": "diffusion models 2025"
})
```

#### 架构图

```
┌─────────────────────────────────────────────────────┐
│           LangGraph StateGraph                      │
│  (工作流编排、条件路由、状态管理)                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐    ┌──────────────┐             │
│  │  Search Node │    │ Analysis Node│             │
│  └──────┬───────┘    └──────┬───────┘             │
│         │                   │                     │
│         └─────────┬─────────┘                     │
│                   │                               │
│         ┌─────────▼────────┐                     │
│         │  Ray Integration │                     │
│         │  (Task Dispatch) │                     │
│         └─────────┬────────┘                     │
└─────────────────────┬──────────────────────────────┘
                      │
         ┌────────────┴────────────┐
         │                         │
    ┌────▼─────┐           ┌──────▼────┐
    │ Ray Task │           │ Ray Task  │
    │ Search   │           │ Analyze   │
    └──────────┘           └───────────┘
         │                       │
    ┌────▼─────┐           ┌──────▼────┐
    │ Worker 1 │           │ Worker 2  │
    │ (CPU)    │           │ (GPU)     │
    └──────────┘           └───────────┘
```

### 2. LangGraph + Celery集成

```python
"""
集成场景：异步后台任务处理 + Agent编排
"""

from celery import Celery, group, chain
from langgraph.graph import StateGraph

app = Celery('research_tasks')

# 1. Celery任务
@app.task
def fetch_papers(query):
    return arxiv_search(query)

@app.task
def process_paper(paper_id):
    return extract_metadata(paper_id)

@app.task
def aggregate_results(results):
    return summarize(results)

# 2. LangGraph工作流
graph = StateGraph(ResearchState)

def search_with_celery(state):
    # 异步发送Celery任务组
    job = group([
        fetch_papers.s(query)
        for query in state["queries"]
    ])()

    # 等待结果
    results = job.get()
    return {"papers": results}

def process_with_celery(state):
    # 链式任务：处理 → 聚合
    workflow = chain(
        group([
            process_paper.s(p_id)
            for p_id in [p["id"] for p in state["papers"]]
        ]),
        aggregate_results.s()
    )()

    result = workflow.get()
    return {"summary": result}

graph.add_node("search", search_with_celery)
graph.add_node("process", process_with_celery)
```

### 3. LangGraph + Dask集成

```python
"""
集成场景：大规模论文数据分析 + Agent工作流
"""

import dask.dataframe as dd
from dask.distributed import Client
from langgraph.graph import StateGraph

# 1. Dask分布式数据处理
def load_papers_distributed():
    df = dd.read_parquet('papers/*.parquet')
    return df

# 2. LangGraph工作流
class DataAnalysisState(TypedDict):
    papers_df: any  # Dask DataFrame
    analysis_results: dict

graph = StateGraph(DataAnalysisState)

def analyze_papers_distributed(state):
    client = Client(processes=False)  # 本地Dask集群

    df = state["papers_df"]

    # 分布式计算
    results = df.groupby('field').agg({
        'citations': 'mean',
        'year': 'max'
    }).compute()

    client.close()
    return {"analysis_results": results}

graph.add_node("analyze", analyze_papers_distributed)
```

---

## AI-Researcher应用建议

### 1. 现状分析

当前AI-Researcher项目已有：
- ✅ **Skill-Based Architecture** (Phase 1完成)
  - 模块化、可发现的工具集合
  - 10个试点Skill + 6个测试文件

- ✅ **LangGraph基础**
  - DAG工作流编排
  - 状态管理

- 🔄 **分布式需求**
  - 多Agent研究任务（文献搜索、分析、综合）
  - 论文处理的高计算需求
  - 可能的多机部署

### 2. 推荐架构设计

#### Phase 3: 分布式执行层 (建议实施)

```
┌─────────────────────────────────────────┐
│  AI-Researcher Distribution Framework   │
├─────────────────────────────────────────┤
│                                         │
│  ┌─────────────────────────────────┐   │
│  │   LangGraph Orchestration       │   │ ← 工作流编排
│  │  (多Agent DAG + 状态管理)        │   │
│  └────────────┬────────────────────┘   │
│               │                        │
│  ┌────────────▼────────────────────┐   │
│  │  Distributed Execution Layer    │   │ ← 新增
│  │  (选择Ray / Celery)             │   │
│  └────────────┬────────────────────┘   │
│               │                        │
│  ┌────────────▼────────────────────┐   │
│  │  Skill-Based Tools              │   │ ← 现有工具集
│  │  (arxiv_search, code_analysis..)│   │
│  └─────────────────────────────────┘   │
│                                         │
└─────────────────────────────────────────┘
```

### 3. 选型建议

#### 情景A：单机多核优先 → **Celery**
```python
# 最小化部署复杂度
# 适合：初期原型、轻量级研究任务
- 低延迟要求：否
- 交互式开发：是
- 异步任务队列：适合
- 多机扩展：不紧急
```

#### 情景B：多机高性能优先 → **Ray**
```python
# 未来扩展性最好
# 适合：生产部署、多GPU推理、复杂Agent
- 低延迟要求：是
- 异构计算：GPU推理
- 实时反馈：需要
- 分布式追踪：重要
```

#### 情景C：混合方案 → **LangGraph + Ray (推荐)**
```python
# 最灵活，充分利用现有投资
# 优点：
# - LangGraph处理工作流 + 条件路由
# - Ray处理分布式计算 + 资源管理
# - Skill复用现有工具
# - 逐步演进，不需大重构
```

### 4. 具体实施路线

#### 阶段1：集成框架(1-2周)

```python
# /research_agent/framework/distributed_executor.py

import ray
from langgraph.graph import StateGraph
from typing import Callable, Any

@ray.remote(num_cpus=2)
def execute_skill(skill_name: str, params: dict) -> dict:
    """在远程Worker上执行Skill"""
    from research_agent.inno.skills import SKILL_REGISTRY
    skill = SKILL_REGISTRY[skill_name]
    return skill.execute(**params)

class DistributedSkillExecutor:
    """LangGraph节点的分布式执行适配器"""

    def __init__(self, cluster_config: dict):
        ray.init(**cluster_config)

    def create_skill_node(self, skill_name: str) -> Callable:
        """为LangGraph创建分布式Skill节点"""
        def node(state):
            future = execute_skill.remote(skill_name, state)
            result = ray.get(future)
            return result
        return node
```

#### 阶段2：扩展Skill系统(2-3周)

```python
# /research_agent/inno/skills/base_skill.py (扩展)

class DistributedSkill(BaseSkill):
    """支持分布式执行的Skill基类"""

    @property
    def is_distributed(self) -> bool:
        return True

    @property
    def resource_requirements(self) -> dict:
        """声明所需资源"""
        return {
            "num_cpus": 2,
            "num_gpus": 0,
            "memory": 2e9
        }

    def can_parallelize(self) -> bool:
        """是否支持并行执行"""
        return False
```

#### 阶段3：添加监控与恢复(2-3周)

```python
# /research_agent/framework/fault_recovery.py

class DistributedResearchOrchestrator:
    """处理故障恢复、监控、重试"""

    def __init__(self, checkpoint_dir: str):
        self.checkpoint_dir = checkpoint_dir
        self.state_store = RedisStateStore()  # 分布式状态存储

    async def run_with_recovery(self, graph, initial_state):
        """运行Graph，支持检查点和恢复"""
        try:
            # 尝试恢复
            state = self.state_store.load(initial_state["task_id"])
        except:
            state = initial_state

        # 执行
        result = graph.invoke(state)

        # 保存检查点
        self.state_store.save(state["task_id"], result)

        return result
```

### 5. 与现有Skills的集成示例

#### 示例：分布式论文搜索工作流

```python
"""
场景：同时搜索多个来源的论文（arXiv、GitHub、Google Scholar）
原实现：顺序执行
优化：使用Ray并行执行多个搜索任务
"""

from langgraph.graph import StateGraph
from research_agent.inno.skills import arxiv_search, code_search
from research_agent.framework.distributed_executor import DistributedSkillExecutor

class MultiSourcePaperSearchState(TypedDict):
    query: str
    arxiv_papers: list
    github_papers: list
    scholar_papers: list
    merged_papers: list

# 初始化分布式执行
executor = DistributedSkillExecutor({
    "num_cpus": 8,
    "num_gpus": 0
})

# 构建工作流
graph = StateGraph(MultiSourcePaperSearchState)

# 添加分布式节点
arxiv_node = executor.create_skill_node("arxiv_search")
github_node = executor.create_skill_node("code_search")

graph.add_node("search_arxiv", arxiv_node)
graph.add_node("search_github", github_node)

# 并行执行两个搜索
graph.add_node("merge_results", merge_papers)

graph.add_edge("search_arxiv", "merge_results")
graph.add_edge("search_github", "merge_results")

# 执行
runnable = graph.compile()
results = runnable.invoke({
    "query": "diffusion models"
})
```

### 6. 资源规划

| 组件 | 建议配置 | 说明 |
|------|--------|------|
| Ray Head Node | 8 CPU, 16GB RAM | 协调节点 |
| Ray Worker (CPU) | 4 CPU, 8GB RAM | 文本处理 |
| Ray Worker (GPU) | 2 GPU, 16GB VRAM | 模型推理 |
| Redis (State Store) | 4GB RAM | 分布式状态存储 |
| 检查点存储 | 100GB SSD | 故障恢复 |

### 7. 监控指标

```python
# 需要追踪的关键指标
metrics = {
    "task_latency": "任务端到端延迟",
    "throughput": "单位时间完成任务数",
    "resource_utilization": "CPU/GPU/内存使用率",
    "failure_rate": "任务失败比例",
    "recovery_time": "故障恢复时间",
    "state_consistency": "分布式状态一致性"
}
```

---

## 关键决策矩阵

### 立即决策（Phase 3设计）

| 问题 | Ray | Celery | 建议 |
|------|-----|--------|------|
| 是否需要多GPU支持? | ✅ | ❌ | 需要→**Ray** |
| 是否需要低延迟(ms级)? | ✅ | ❌ | 需要→**Ray** |
| 是否优先简单部署? | ❌ | ✅ | 是→**Celery** |
| 是否需要异构计算? | ✅ | ❌ | 需要→**Ray** |
| 现有LangGraph投资? | ✅✅ | ❌ | 优化→**Ray+LangGraph** |

### 最终推荐

**选择: Ray + LangGraph混合方案**

**理由**:
1. ✅ 充分利用现有LangGraph投资
2. ✅ 支持未来GPU推理扩展
3. ✅ 毫秒级延迟满足交互式需求
4. ✅ Actor模型支持有状态Agent
5. ✅ 渐进式演进，无需大重构
6. ✅ 生产级可靠性

**实施难度**: ⭐⭐⭐ (中等)
**回报**: ⭐⭐⭐⭐⭐ (高)

---

## 参考资源

### 官方文档
- [Ray Documentation](https://docs.ray.io/)
- [LangGraph Documentation](https://www.langchain.com/langgraph)
- [Celery Documentation](https://docs.celeryq.dev/)
- [Dask Documentation](https://dask.org/)

### 关键论文与资源
- [Ray: A Distributed Framework for Emerging AI Applications (OSDI 2018)](https://arxiv.org/abs/1712.05889)
- [Event-Driven Multi-Agent Systems (Confluent, 2025)](https://www.confluent.io/blog/event-driven-multi-agent-systems/)
- [Distributed Agent Orchestration Patterns (2026)](https://healthark.ai/orchestrating-multi-agent-systems-with-lang-graph-mcp/)

### 在线工具
- Ray Dashboard: `ray://localhost:8265`
- Celery Flower: `http://localhost:5555`
- Dask Dashboard: `http://localhost:8787`

---

**文档版本**: v1.0
**最后更新**: 2026-03-15
**下一步**: 启动Phase 3实施计划
