# AI-Researcher

Autonomous scientific discovery agent framework with modular skill architecture, agent memory system, and multi-agent orchestration.

> **Based on [HKUDS/AI-Researcher](https://github.com/HKUDS/AI-Researcher)** - original framework by Jiabin Tang, Lianghao Xia, Zhonghang Li, Chao Huang (HKU Data Science Lab). See [Citation](#citation) below.

## What This Fork Adds

This fork extends the original AI-Researcher with:

- **Skill-Based Architecture** - Modular, discoverable, on-demand tool bundles with SKILL.md manifests
- **Tool Discovery** - JSON Schema for tool parameters, embedding-based semantic search, A2A Agent Card export
- **Agent Memory System** - SessionState, MemoryStore, AgentNamespace, EventLog, memory consolidation
- **MemoryAwareMetaChain** - Opt-in wrapper adding memory to MetaChain without modifying core.py

## Project Structure

```
research_agent/
  inno/
    core.py              # MetaChain agent loop (unchanged from upstream)
    registry.py          # Base tool/agent registry
    types.py             # Agent, Response, Result types
    skills/              # [NEW] Skill framework
      base.py            #   SkillManifest, Skill, SkillDependency
      loader.py          #   Two-phase discovery: scan() -> load()
      registry.py        #   SkillRegistry + search + events + A2A
      search.py          #   Embedding-based tool search
      events.py          #   Skill lifecycle event bus
      agent_card.py      #   A2A Agent Card export
      arxiv_search/      #   Skill: arXiv paper search (tools: HKUDS)
      paper_search/      #   Skill: paper metadata (tools: HKUDS)
      code_search/       #   Skill: GitHub code search (tools: HKUDS)
      file_operations/   #   Skill: file system ops (tools: HKUDS)
      planning/          #   Skill: ML experiment planning (tools: HKUDS)
      memory_tools/      #   Skill: agent memory operations (NEW)
    memory/              # Memory subsystem
      rag_memory.py      #   Chroma-based vector memory (from upstream)
      code_memory.py     #   Code file indexing (from upstream)
      paper_memory.py    #   Paper content indexing (from upstream)
      tool_memory.py     #   API/tool indexing (from upstream)
      session_state.py   #   [NEW] Typed context_variables with history
      store.py           #   [NEW] Unified 3-tier memory interface
      consolidation.py   #   [NEW] Episode-to-fact extraction
      agent_namespace.py #   [NEW] Cross-agent state isolation
      event_log.py       #   [NEW] Append-only event sourcing
      meta_chain_wrapper.py  # [NEW] Memory-aware MetaChain wrapper
    agents/              # Agent implementations (from upstream)
    tools/               # Tool implementations (from upstream)
    environment/         # Docker/browser environments (from upstream)
    workflow/            # DAG workflow engine (from upstream)
paper_agent/             # Paper writing agent (from upstream)
benchmark/               # Benchmark instances (from upstream)
tests/                   # 155 tests passing
```

## Quick Start

### Requirements

- Python >= 3.11
- Docker (for code execution environment)

### Installation

```bash
git clone https://github.com/LIHUA919/AI-Researcher.git
cd AI-Researcher

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install
pip install -e .
playwright install
```

### API Keys

```bash
export ANTHROPIC_API_KEY=your_key      # or OPENAI_API_KEY
export COMPLETION_MODEL=anthropic/claude-3-5-sonnet-20241022
export CHEEP_MODEL=anthropic/claude-3-5-haiku-20241022
export GITHUB_AI_TOKEN=your_github_token
```

### Run Level 1: Generate Research Ideas

```bash
# Pull Docker image
docker pull tjbtech1/metachain:amd64_latest

# Run
cd research_agent
export BASE_IMAGES=tjbtech1/metachain:amd64_latest
export DOCKER_WORKPLACE_NAME=workplace_paper

python run_infer_idea.py \
  --instance_path ../benchmark/final/vq/one_layer_vq.json \
  --container_name paper_eval \
  --model $COMPLETION_MODEL \
  --workplace_name workplace \
  --cache_path cache \
  --port 12372 \
  --max_iter_times 0 \
  --category vq
```

### Run Level 2: Generate Implementation Plan

```bash
python run_infer_plan.py \
  --instance_path ../benchmark/final/vq/one_layer_vq.json \
  --container_name test_eval \
  --task_level task1 \
  --model $COMPLETION_MODEL \
  --workplace_name workplace \
  --cache_path cache \
  --port 12380 \
  --max_iter_times 0 \
  --category vq
```

### CLI Quick Test

```bash
ai-researcher agent --model gpt-4o --agent_func get_dummy_agent --query "Hello"
```

## Tests

```bash
pytest tests/ -v
# 155 tests passing (skills: 83, memory: 52, core: 20)
```

## Architecture

### Skill System (Phase 1 + Stage 1)

Skills are modular tool bundles discovered from SKILL.md manifests:

```python
from research_agent.inno.skills import skill_registry

# Discover available skills
skill_registry.loader.scan()
print(skill_registry.list_available())
# ['arxiv_search', 'paper_search', 'code_search', 'planning', 'file_operations', 'memory_tools']

# Load on demand
skill = skill_registry.load_and_register("arxiv_search")

# Semantic search
results = skill_registry.search_tools("find academic papers")

# Export A2A Agent Card
card = skill_registry.to_agent_card(name="AI-Researcher")
print(card.to_json())
```

### Memory System (Stage 2)

Opt-in memory wrapping MetaChain without modifying core.py:

```python
from research_agent.inno.core import MetaChain
from research_agent.inno.memory.store import MemoryStore
from research_agent.inno.memory.meta_chain_wrapper import MemoryAwareMetaChain

# Standard MetaChain (unchanged)
chain = MetaChain()

# Add memory (opt-in)
store = MemoryStore(project_path="/workspace")
mem_chain = MemoryAwareMetaChain(chain, store)

# Session state with change tracking
store.session.set("topic", "GNN", agent_name="IdeaAgent")
store.session.history("topic")  # all changes with timestamps

# Agent namespace isolation
from research_agent.inno.memory.agent_namespace import AgentNamespace
ns = AgentNamespace("IdeaAgent", store.session)
ns.set("plan", "my plan")          # only IdeaAgent sees this
ns.set_shared("paper_count", 5)    # all agents see this
```

## Benchmark

Benchmark data from the original HKUDS/AI-Researcher project is included in the `benchmark/` directory, covering categories: `vq`, `gnn`, `diffu_flow`, `recommendation`, `reasoning`.

## Citation

This project is based on AI-Researcher by HKUDS. If you use this work, please cite the original paper:

```tex
@misc{airesearcher,
      title={{AI-Researcher: Autonomous Scientific Innovation}},
      author={Jiabin Tang and Lianghao Xia and Zhonghang Li and Chao Huang},
      year={2025},
      eprint={2505.18705},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2505.18705},
}
```

## License

Apache-2.0 (see [LICENSE](./LICENSE)). Original copyright HKUDS.
