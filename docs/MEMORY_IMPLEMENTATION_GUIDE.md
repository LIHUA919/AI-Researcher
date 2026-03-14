# Agent Memory & State Management - Implementation Decision Matrix

**Purpose:** Quick reference for selecting technologies and patterns for specific use cases in AI-Researcher

---

## 1. Technology Selection Decision Tree

### When Should You Use What?

```
┌─ What's your primary need?
│
├─ VECTOR SIMILARITY SEARCH
│  ├─ Prototyping/Research? → Chroma ✅ (local, free)
│  ├─ Production with scale? → Pinecone ✅ (managed, fast)
│  ├─ On-prem deployment? → Weaviate ✅ (self-hosted)
│  └─ Hybrid SQL + Vector? → PostgreSQL+pgvector ✅ (cost-effective)
│
├─ GRAPH RELATIONSHIPS
│  ├─ Research entity relationships? → Neo4j ✅ (graph DB)
│  ├─ Semantic with metadata? → Weaviate ✅ (hybrid search)
│  └─ Simple ontology? → Knowledge graph (custom) ✅
│
├─ MULTI-AGENT COORDINATION
│  ├─ Message passing? → Redis Pub/Sub ✅ (sub-ms latency)
│  ├─ State persistence? → Redis Streams ✅ (event sourcing)
│  ├─ Complex queries? → PostgreSQL ✅ (SQL)
│  └─ Real-time sync? → Redis + Streams ✅ (best combo)
│
└─ WORKFLOW STATE
   ├─ Single agent? → LangGraph State ✅ (TypedDict)
   ├─ Multi-agent? → LangGraph + Checkpointer ✅
   ├─ Persistence? → RedisSaver/SQLiteSaver ✅
   └─ Complex workflows? → LangGraph + Redis ✅
```

---

## 2. Memory Layer Selection by Use Case

### AI-Researcher: Paper Agent Pipeline

```
PIPELINE LAYER          MEMORY TYPE           TECHNOLOGY         LATENCY
─────────────────────────────────────────────────────────────────────────
Query Processing        Short-term session    Python objects      <1ms
                        (current task)        + LangGraph State

Context Retrieval       RAG memory            Chroma vector DB    20-50ms
(papers, code)          (semantic similarity) (existing)

Task History            Episodic memory       Chroma collection   20-50ms
(what we tried)         (temporal + outcome)  (new separation)

Established Facts       Semantic memory       Chroma collection   20-50ms
(what we know)          (factual + linked)    (new separation)

Research Graph          Relationships         Neo4j (optional)    5-20ms
(how papers relate)     (temporal + causal)   or Weaviate

Cross-Agent State       Coordination log      Redis Streams       1-10ms
(who did what)          (event sourcing)      (new)
```

---

## 3. Storage Technology Quick Reference

### Chroma (Already Integrated)
```yaml
Current Use: research_agent/inno/memory/rag_memory.py
Strengths:
  ✓ Already integrated (minimal migration)
  ✓ Works with local embeddings (SentenceTransformer)
  ✓ Works with OpenAI embeddings
  ✓ Python-native development
Weaknesses:
  ✗ Not optimized for billion-scale single instance
  ✗ Limited hybrid search (recently added, less mature)
Recommendation: KEEP for vector similarity search (papers, code)
```

### Redis (Add Next)
```yaml
New Addition: Multi-agent coordination
Strengths:
  ✓ Sub-millisecond latency
  ✓ Event sourcing (Streams)
  ✓ Pub/Sub messaging
  ✓ Caching layer
  ✓ Managed options available
Weaknesses:
  ✗ Not ideal for deep graph traversal
  ✗ Limited complex queries
Recommendation: ADD for event sourcing + state sync
```

### Neo4j (Optional, Later)
```yaml
Future Addition: Research knowledge graph
Strengths:
  ✓ Perfect for relationship representation
  ✓ Graph traversal (shortest path, etc.)
  ✓ Temporal tracking possible
  ✓ Community graph patterns
Weaknesses:
  ✗ Additional operational complexity
  ✗ Learning curve (Cypher queries)
  ✗ Separate from vector search
Recommendation: ADD in Phase 3 if needed for rich reasoning
```

---

## 4. Architecture Decision: Single-Agent vs Multi-Agent Memory

### Single-Agent (Current paper_agent)
```
Session Memory (LangGraph State)
    ↓
Agent Memory (Chroma)
    ↓
Long-term Storage (SQLite/JSON)

Pattern:
1. LangGraph state holds current conversation
2. Retrieve relevant docs from Chroma
3. Generate with context
4. Save results to storage
```

### Multi-Agent (paper_agent + research_agent)
```
Session Memory (Redis + LangGraph State)
    ↓
Event Bus (Redis Streams)
    ↓
Agent Memory (Chroma per agent OR shared)
    ↓
Shared Knowledge (PostgreSQL/Neo4j)

Pattern:
1. Each agent: LangGraph state (local)
2. Publish events to Redis Streams (actions taken)
3. Other agents subscribe and update local state
4. RAG from shared memory (vector DB)
5. Consolidate to shared knowledge graph (Neo4j, optional)
```

---

## 5. Implementation Priority Matrix

### Effort vs Impact for AI-Researcher

| Feature | Effort | Impact | Priority | Timeline |
|---------|--------|--------|----------|----------|
| Separate episodic/semantic memory | 2-3h | High | 🔴 P0 | Week 1 |
| Memory consolidation pipeline | 4-6h | High | 🔴 P0 | Week 1-2 |
| Redis event sourcing | 6-8h | Very High | 🔴 P0 | Week 2-3 |
| Cross-agent state sync | 4-5h | Very High | 🔴 P0 | Week 3 |
| Intelligent retrieval ranking | 3-4h | Medium | 🟡 P1 | Week 2 |
| Neo4j integration | 8-12h | Medium | 🟡 P1 | Week 5+ |
| Memory analytics | 5-7h | Low | 🟢 P2 | Week 6+ |
| Forgetting policies | 4-6h | Medium | 🟡 P1 | Week 4 |

---

## 6. Code Integration Points

### What to Modify vs Create

#### Keep (No Changes)
```
research_agent/inno/memory/rag_memory.py
  └─ Core Vector DB integration
```

#### Wrap/Extend
```
research_agent/inno/memory/
  ├─ Create: multi_tier_memory.py (wraps rag_memory.py)
  ├─ Create: memory_consolidator.py
  ├─ Create: forget_policy.py
  └─ Extend: tool_memory.py (add episodic support)
```

#### Create New
```
research_agent/inno/coordination/
  ├─ Create: event_sourcing.py (Redis integration)
  ├─ Create: agent_event_bus.py
  └─ Create: state_synchronizer.py

research_agent/inno/knowledge_graph/
  ├─ Create: graph_memory.py (Neo4j, optional)
  ├─ Create: relationship_extractor.py
  └─ Create: temporal_reasoner.py
```

---

## 7. State Management Pattern: Before vs After

### BEFORE (Current)
```python
# Conversation held in memory during session only
class PaperAgent:
    async def process(self, query):
        # No persistent memory between sessions
        # Each run starts fresh
        relevant_papers = search_arxiv(query)
        # ... process ...
        return result  # Lost after session ends
```

### AFTER (Proposed)
```python
# Conversation + episodic learning across sessions
class PaperAgent:
    def __init__(self, project_path):
        self.state_graph = StateGraph(PaperAgentState)
        self.memory = MultiTierMemory(project_path)
        self.event_bus = AgentEventBus(redis_client)

    async def process(self, query):
        # 1. Recall similar past attempts
        past_attempts = self.memory.recall_similar_episodes(query)

        # 2. LangGraph workflow with state
        state = await self.state_graph.invoke({
            "messages": [{"role": "user", "content": query}],
            "past_context": past_attempts
        })

        # 3. Publish event for other agents
        self.event_bus.publish_event(
            agent_id="paper_agent",
            event_type="paper_processed",
            payload={"papers": state.get("papers"), "query": query}
        )

        # 4. Record in episodic memory
        self.memory.record_episode({
            "description": f"Processed query: {query[:50]}",
            "type": "paper_processing",
            "outcome": "success" if state.get("papers") else "no_results",
            "context": state,
            "learnings": self._extract_learnings(state)
        })

        return state
```

---

## 8. Quick Start: Adding Memory Consolidation

### Minimal Implementation (2 hours)

```python
# research_agent/inno/memory/consolidator.py

from research_agent.inno.memory.rag_memory import Memory
import json
from datetime import datetime, timedelta

class SimpleConsolidator:
    """Move old episodes to semantic memory"""

    def __init__(self, memory: Memory, llm):
        self.memory = memory
        self.llm = llm

    def consolidate_old_episodes(self, days_old=7):
        """Consolidate episodes older than N days"""

        # 1. Get episodes older than threshold
        all_episodes = self.memory.peek(
            collection='memory',
            n_results=1000
        )

        old_episodes = []
        for ep_batch in all_episodes.get('metadatas', []):
            for ep in ep_batch:
                created = datetime.fromisoformat(ep.get('created_at', ''))
                if (datetime.now() - created).days > days_old:
                    old_episodes.append(ep)

        # 2. Cluster by similarity (simple: by first words)
        clusters = self._cluster_episodes(old_episodes)

        # 3. For each cluster, extract key facts
        for cluster_id, episodes in clusters.items():
            # Use LLM to summarize cluster
            facts = self._extract_facts(episodes)

            # 4. Store facts as semantic memory
            for fact in facts:
                self.memory.add_query([{
                    "query": fact['statement'],
                    "response": json.dumps({
                        "source": "consolidation",
                        "confidence": 0.8,
                        "from_episodes": cluster_id
                    })
                }],
                collection='semantic_memory')

    def _cluster_episodes(self, episodes):
        """Simple clustering by embedding similarity"""
        # Quick implementation: group by first 50 chars
        clusters = {}
        for ep in episodes:
            key = ep.get('response', '')[:50]
            clusters.setdefault(key, []).append(ep)
        return clusters

    def _extract_facts(self, episodes):
        """Use LLM to extract facts from episode cluster"""
        episode_text = "\n\n".join([
            ep.get('response', '') for ep in episodes[:5]  # Limit context
        ])

        prompt = f"""
        Given these similar past experiences:
        {episode_text}

        What are 2-3 key generalizable facts to remember?
        Return as JSON: [{{"statement": "...", "confidence": 0.9}}]
        """

        response = self.llm.generate(prompt)
        try:
            return json.loads(response)
        except:
            return []


# Usage
consolidator = SimpleConsolidator(memory, llm)
consolidator.consolidate_old_episodes(days_old=7)
```

---

## 9. Common Pitfalls and Solutions

### Pitfall 1: Memory Growing Unbounded
```
Problem: Chroma collection keeps growing indefinitely
Solution: Consolidation + Forgetting policies
    - Consolidate old episodes (>7 days) to semantic memory
    - Remove duplicates and low-salience items
    - Archive to cheaper storage (SQLite, files)
```

### Pitfall 2: Slow Retrieval as Memory Grows
```
Problem: Semantic search becomes slow with 100K+ vectors
Solutions:
    1. Metadata filtering (filter by type before search)
    2. Collection separation (episodic vs semantic)
    3. Hierarchical retrieval (coarse → fine)
    4. Database optimization (indexing)
```

### Pitfall 3: Inconsistent State in Multi-Agent
```
Problem: paper_agent and research_agent have different views
Solutions:
    1. Event sourcing (single source of truth: event log)
    2. State synchronization (periodic updates)
    3. Conflict detection (Redis Streams ordering)
    4. Consensus mechanisms (voting, timestamp-based)
```

### Pitfall 4: Hallucinated References in Retrieved Context
```
Problem: LLM generates facts not in retrieved context
Solution: Enforce "answer only from context" prompt
    - Include citation tracking in memory
    - Use retrieval-augmented generation strictly
    - Track sources in metadata
```

---

## 10. Testing Memory Systems

### Unit Tests
```python
def test_episodic_memory():
    memory = MultiTierMemory("/tmp/test")

    # Record episode
    memory.record_episode({
        "description": "Tried arxiv search",
        "outcome": "found 5 papers",
        "learnings": ["search term syntax matters"]
    })

    # Recall similar
    results = memory.recall_similar_episodes("arxiv search")
    assert len(results['ids']) > 0

def test_consolidation():
    consolidator = SimpleConsolidator(memory, mock_llm)

    # Create old episodes
    # Run consolidation
    # Verify facts moved to semantic memory

def test_multi_agent_sync():
    event_bus = AgentEventBus(redis_client)

    # Agent 1 publishes event
    event_bus.publish_event("agent1", "paper_found", {...})

    # Agent 2 reads from stream
    events = event_bus.subscribe_to_events(['paper_found'])
    assert len(events) > 0
```

---

## 11. Monitoring and Observability

### What to Monitor

```yaml
Memory System Metrics:
  Storage:
    - Total vectors in Chroma
    - Episodic vs Semantic split
    - Vector memory growth rate

  Performance:
    - Retrieval latency (p50, p95, p99)
    - Consolidation runtime
    - Forgetting policy execution time

  Quality:
    - Retrieved result relevance (manual spot-check)
    - Consolidation fidelity (facts preserved?)
    - Duplicate ratio in memory

  Coordination (Multi-agent):
    - Event lag (time to propagate state)
    - Synchronization errors
    - Message queue depth

Dashboard: One table view per minute
```

---

## 12. Scaling Path

### 100 research papers (Current)
```
Storage: Chroma on disk (~50MB)
Retrieval: <50ms
Management: Manual
```

### 1,000 papers (Phase 1)
```
Storage: Chroma + PostgreSQL (~500MB)
Retrieval: <100ms
Management: Consolidation + forgetting
```

### 10,000 papers (Phase 2)
```
Storage: Chroma + PostgreSQL + Neo4j (~5GB)
Retrieval: 50-100ms (with filtering)
Management: Automated consolidation
Coordination: Redis event sourcing
```

### 100,000+ papers (Phase 3)
```
Storage: Pinecone + PostgreSQL + Neo4j
Retrieval: <50ms (managed vector DB)
Management: Tiered storage (hot/warm/cold)
Coordination: Redis + distributed event log
Scaling: Horizontal (multiple agent instances)
```

---

## Summary: Where to Start

### Week 1: Foundation
1. Create `MultiTierMemory` wrapper (wrap existing Chroma)
2. Separate episodic/semantic collections
3. Add basic consolidation pipeline
4. Write tests

### Week 2: Coordination
1. Add Redis (event sourcing)
2. Implement `AgentEventBus`
3. Connect paper_agent and research_agent
4. Test multi-agent state sync

### Week 3+: Enhancement
1. Add intelligent retrieval ranking
2. Implement forgetting policies
3. Optional: Neo4j integration

**Total Implementation Time: 100-150 hours (2.5-3.5 weeks)**

---

**Document Version:** 1.0
**Created:** March 2026
**For Project:** AI-Researcher
