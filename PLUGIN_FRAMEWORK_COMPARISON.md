# Plugin System Framework Comparison & Implementation Patterns

**Date:** March 15, 2026
**Purpose:** Detailed analysis for Phase 2c - Tool Discovery & Dynamic Loading

---

## Executive Summary: Which Plugin System for AI-Researcher?

| Need | Recommendation | Reason |
|------|----------------|--------|
| **Current (monorepo)** | Filesystem + Registry ✓ Keep | Simple, effective, no dependencies |
| **External plugins** | Setuptools Entry Points | Standard, vetted packages, ecosystem support |
| **Runtime changes** | MCP Notifications Layer | Handles dynamic tool changes |
| **Cross-agent discovery** | A2A Agent Cards | Standardized, 50+ partners using |
| **Large tool catalogs** | Tool Search + Embeddings | Scale to hundreds/thousands of tools |

---

## 1. Setuptools Entry Points Pattern

### 1.1 Core Concept

**Location:** `setup.py` or `setup.cfg`

```python
# setup.py
setup(
    name="ai_researcher",
    entry_points={
        "ai_researcher.skills": [
            "arxiv_search = ai_researcher.skills.arxiv_search:Skill",
            "paper_search = ai_researcher.skills.paper_search:Skill",
        ]
    }
)
```

### 1.2 Discovery Flow

```
Installation (pip install package)
    ↓
setuptools reads entry_points from setup.py
    ↓
Creates metadata in: site-packages/ai_researcher-X.Y.dist-info/entry_points.txt
    ↓
At runtime, importlib.metadata reads entry_points.txt
    ↓
Plugin discoverable without executing code
```

### 1.3 Entry Points Discovery Code

```python
from importlib.metadata import entry_points

# Get all skills (Python 3.10+)
eps = entry_points(group="ai_researcher.skills")
for ep in eps:
    print(f"Found skill: {ep.name}")
    skill_class = ep.load()  # Import on-demand
    skill = skill_class()

# Legacy Python 3.9 compatibility
import importlib.metadata as metadata
eps = metadata.entry_points()
skills = eps.get("ai_researcher.skills", [])
```

### 1.4 Advantages vs. Filesystem Scanning

| Aspect | Filesystem | Entry Points |
|--------|-----------|--------------|
| Package install | pip install | ✓ Automatic discovery |
| Third-party plugins | Manual path config | ✓ Works everywhere |
| Version management | Manual | ✓ Via package versions |
| Distribution | Copy files | ✓ pip handles it |
| Development | Easy | ✓ pip install -e . works |
| Multiple projects | Paths conflict | ✓ Namespace isolation |
| Monorepo | Ideal | Less ideal |

### 1.5 When to Migrate to Entry Points

**Triggers:**
1. ✓ Multiple plugins distributed as separate packages
2. ✓ Third-party developers contributing plugins
3. ✓ Need for version management per plugin
4. ✓ Want ecosystem discovery (pip show)
5. ✓ Need reproducible environments (requirements.txt, poetry.lock)

**For AI-Researcher:** Consider for Phase 3+ when scaling beyond research team

---

## 2. Stevedore: Enterprise Plugin Manager

### 2.1 What It Does

**Stevedore** = Entry Points + Manager Classes

Solves the "what do I do with loaded plugins?" problem.

```python
from stevedore import driver

# Load single plugin as driver
mgr = driver.DriverManager(
    namespace="ai_researcher.skills",
    name="arxiv_search",
    invoke_on_load=True,  # Call __init__ during load
)
mgr.driver  # Returns loaded skill instance
```

### 2.2 Manager Types

#### DriverManager
- Single plugin implementation
- Example: "which email backend?" (SMTP vs. SendGrid vs. S3)
- Pattern: Select best match, ignore others

```python
mgr = driver.DriverManager(
    namespace="ai_researcher.backends",
    name="openai",  # or "anthropic" or "local"
)
backend = mgr.driver
results = backend.complete("prompt")
```

#### ExtensionManager
- Multiple plugins work together
- Example: All available tools for a task
- Pattern: Load all, use all

```python
mgr = extension.ExtensionManager(
    namespace="ai_researcher.skills",
    invoke_on_load=True,
)
for ext in mgr:
    print(f"Skill: {ext.name}")
    skill = ext.obj  # The loaded skill
```

#### HookManager
- Plugins implement hooks in callbacks
- Example: Pipeline stages
- Pattern: Call hooks in sequence

```python
mgr = hook.HookManager(
    namespace="ai_researcher.workflow_hooks",
)
mgr.run_hooks("pre_search", tool="arxiv_search")
mgr.run_hooks("post_search", tool="arxiv_search")
```

### 2.3 Comparison with AI-Researcher Current Approach

| Feature | AI-Researcher | Stevedore |
|---------|---------------|-----------|
| Discovery | Filesystem scan | Entry points |
| Lazy loading | ✓ Yes | ✓ Yes (invoke_on_load=False) |
| Manager class | Custom SkillRegistry | Built-in managers |
| Error handling | Custom | Built-in |
| Logging | Custom | Built-in structured logging |
| Testing | Test-specific paths | Easier mocking |

### 2.4 Adoption Decision

**Stevedore is overkill if:**
- Only using SkillRegistry (single manager type)
- Not distributing plugins separately
- Happy with current custom implementation

**Stevedore is useful if:**
- Migrating to setuptools entry points
- Need consistent error handling
- Want logging/debugging support
- Building tool ecosystem others will extend

**Recommendation for AI-Researcher:** Stick with current pattern, optionally switch to Stevedore when migrating to entry points.

---

## 3. Plux: Modern (2025) Plugin Framework

### 3.1 What's New

**Plux** = Modern alternative to Stevedore, developed by LocalStack

Key innovations:
- Automatic code discovery (no manual registration)
- Creates plugin index file
- Works with both setuptools and custom plugins
- Better for modern Python apps

### 3.2 Core Concept

```python
from plux import PluginFinder, PluginSpec

# Define a plugin spec
class SkillSpec(PluginSpec):
    """Specification for skills"""
    def __init__(self, name: str, impl):
        self.name = name
        self.impl = impl

# Auto-discover plugins in code
finder = PluginFinder()
specs = finder.discover(SkillSpec)

# Use discovered plugins
for spec in specs:
    skill = spec.impl()
```

### 3.3 Advantages over Entry Points

| Aspect | Entry Points | Plux |
|--------|------------|------|
| Declaration | setup.py | In code via PluginSpec |
| Index | In package metadata | Separate .plux.json |
| Discovery | Manual importlib.metadata | Automatic scanning |
| Type safety | Strings | Python classes |
| Development | Requires reinstall | Hot reload capable |

### 3.4 When to Use Plux

**Good for:**
- Modern Python 3.9+ applications
- Rapid prototyping with hot reload
- Type-safe plugin specs
- Projects wanting to avoid setup.py complexity

**Not ideal for:**
- Packages distributed via PyPI (setuptools better)
- Team unfamiliar with PluginSpec pattern
- Simple use cases (overkill)

**For AI-Researcher:** Could replace current SkillLoader, but no strong advantage over entry points

---

## 4. Dynamic Tool Discovery: Advanced Patterns

### 4.1 Pattern: Tool Search with Embeddings

**Problem:** Listing all 500 tools consumes 55k tokens. Most are irrelevant.

**Solution:** Search tools by semantic similarity

```python
from sentence_transformers import SentenceTransformer

class ToolSearchRegistry:
    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.tool_embeddings = {}  # {tool_name: embedding}

    def index_tools(self, tools: List[Tool]):
        """Create embeddings for all tools"""
        for tool in tools:
            description = f"{tool.name}: {tool.description}"
            embedding = self.model.encode(description)
            self.tool_embeddings[tool.name] = embedding

    def search(self, query: str, limit: int = 5) -> List[Tuple[str, float]]:
        """Find most relevant tools"""
        query_embedding = self.model.encode(query)

        # Compute similarity
        similarities = []
        for tool_name, tool_embedding in self.tool_embeddings.items():
            similarity = self.cosine_similarity(query_embedding, tool_embedding)
            similarities.append((tool_name, similarity))

        # Return top-k
        return sorted(similarities, key=lambda x: x[1], reverse=True)[:limit]

    @staticmethod
    def cosine_similarity(a, b):
        """Compute cosine similarity"""
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
```

**Benefit:** Reduce tokens from 55k to ~5k (85% reduction)

**Implementation:** This matches Claude's Tool Search feature from 2025

### 4.2 Pattern: Conditional Tool Availability

**Problem:** Some tools only available with authentication, or in certain workflow phases

**Solution:** Dynamic availability checking

```python
class ConditionalToolRegistry:
    def list_available_tools(self, context: Dict) -> List[str]:
        """List only tools available in current context"""
        available = []

        for tool_name, tool_spec in self.tools.items():
            # Check authentication
            if tool_spec.required_auth:
                if context.get("auth_token") is None:
                    continue

            # Check workflow phase
            if tool_spec.required_phase:
                if context.get("phase") != tool_spec.required_phase:
                    continue

            # Check feature flags
            if tool_spec.feature_flag:
                if not context.get("features", {}).get(tool_spec.feature_flag):
                    continue

            available.append(tool_name)

        return available

    def get_tools_for_state(self, state: Dict) -> Dict[str, Tool]:
        """Get only tools relevant to current state"""
        available_names = self.list_available_tools(state)
        return {name: self.tools[name] for name in available_names}
```

**Implementation in LangGraph:**
```python
def determine_tools(state):
    """Conditional tool selection based on state"""
    if state["phase"] == "search":
        return {"tools": ["arxiv_search", "paper_search"]}
    elif state["phase"] == "analyze":
        return {"tools": ["code_search", "statistics"]}
```

### 4.3 Pattern: Tool Caching & Invalidation

**Problem:** Recomputing tool lists is expensive (especially with embeddings)

**Solution:** Cache with invalidation signals

```python
from functools import lru_cache
import hashlib

class CachedToolRegistry:
    def __init__(self):
        self._cache_key = None
        self._cached_embedding = None
        self._cache_version = 0

    def notify_tools_changed(self):
        """Called when tools are added/removed/updated"""
        self._cache_version += 1
        self._cached_embedding = None  # Invalidate

    @property
    def cache_key(self) -> str:
        """Hash of current tool set"""
        tool_names = sorted(self.tools.keys())
        content = "\n".join(tool_names)
        return hashlib.md5(content.encode()).hexdigest()

    def get_embeddings(self, refresh=False) -> Dict[str, np.ndarray]:
        """Get tool embeddings with caching"""
        if not refresh and self._cached_embedding and self._cache_key == self.cache_key:
            return self._cached_embedding

        # Recompute embeddings
        embeddings = {}
        for tool_name, tool in self.tools.items():
            description = f"{tool_name}: {tool.description}"
            embeddings[tool_name] = self.model.encode(description)

        self._cached_embedding = embeddings
        self._cache_key = self.cache_key
        return embeddings
```

**Integration with MCP:**
```python
# Server sends notification when tools change
server.notify_message({
    "jsonrpc": "2.0",
    "method": "notifications/tools/list_changed"
})

# Client refreshes on notification
client.on_tools_changed(() => {
    registry.notify_tools_changed()
    tools = registry.list_available()
})
```

---

## 5. MCP Integration Patterns

### 5.1 MCP Tool Lifecycle

```
MCP Client                     MCP Server
    │                              │
    ├─ tools/list ────────────────>│
    │                    read SKILL.md files
    │  <─────────── tools/listResult ─┤
    │  {tools: [...]}              │
    │                              │
    │  (later, tool added)         │
    │  <─── notifications/tools/list_changed ─┤
    │  (acknowledge)               │
    │  ─── tools/list ────────────>│
    │  <─────── tools/listResult ──┤
```

### 5.2 Server-Side: Tool Notifications

```python
from mcp import Server
from research_agent.inno.skills.registry import skill_registry

server = Server("ai_researcher")

@server.tool_list_handler
def list_tools():
    """Expose skills as MCP tools"""
    tools = []
    for skill_name in skill_registry.list_skills():
        skill = skill_registry.get_skill(skill_name)
        for tool_func in skill.functions:
            tools.append({
                "name": tool_func.__name__,
                "description": tool_func.__doc__,
                "input_schema": get_schema(tool_func),
            })
    return {"tools": tools}

@server.on_change_hook
def handle_skill_change(event):
    """Notify client when skills change"""
    if event.type == "skill_loaded":
        server.notify({
            "jsonrpc": "2.0",
            "method": "notifications/tools/list_changed"
        })
```

### 5.3 Client-Side: Responding to Notifications

```python
class ToolRegistry:
    def __init__(self, mcp_client):
        self.client = mcp_client
        self.tools_cache = {}
        self.subscribe_to_changes()

    def subscribe_to_changes(self):
        """Listen for tool change notifications"""
        self.client.on("notifications/tools/list_changed",
                       self.refresh_tools)

    def refresh_tools(self):
        """Refresh tool list on notification"""
        response = self.client.call("tools/list")
        self.tools_cache = {
            tool["name"]: tool
            for tool in response["tools"]
        }
```

---

## 6. A2A Agent Card Implementation

### 6.1 Export Skill Registry as Agent Card

```python
from typing import List, Dict, Any
from research_agent.inno.skills.registry import skill_registry

class A2AAgentCard:
    """Exports SkillRegistry as A2A Agent Card"""

    @staticmethod
    def from_skill_registry(registry) -> Dict[str, Any]:
        """Convert skill registry to Agent Card JSON"""
        skills = []

        for skill_name in registry.list_skills():
            skill = registry.get_skill(skill_name)
            manifest = skill.manifest

            skills.append({
                "name": manifest.name,
                "description": manifest.description,
                "version": manifest.version,
                "tools": manifest.tools,
                "tags": manifest.tags,
                "requiredConfig": manifest.required_config,
                "author": manifest.author,
                "instructions": manifest.instructions
            })

        return {
            "name": "AI-Researcher Agent",
            "description": "Autonomous research agent for academic paper discovery and analysis",
            "provider": "HKUDS",
            "version": "0.2.0",
            "serviceEndpoint": "https://researcher.example.com/a2a",
            "capabilities": {
                "skills": skills,
                "features": ["streaming", "statefulness"],
                "supportedProtocols": ["json-rpc"]
            },
            "authentication": {
                "type": "bearer",
                "required": []  # Could load from config
            }
        }
```

### 6.2 Expose as /.well-known/agent.json

```python
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/.well-known/agent.json")
def agent_card():
    """Expose A2A Agent Card"""
    card = A2AAgentCard.from_skill_registry(skill_registry)
    return jsonify(card)

@app.route("/a2a/tasks", methods=["POST"])
def handle_task():
    """Handle A2A task requests"""
    task = request.json

    # Use skill registry to execute task
    result = execute_task_with_skills(task, skill_registry)
    return jsonify({"result": result})
```

### 6.3 Client: Discover and Call Remote Agent

```python
from a2a import A2AClient

class RemoteSkillRegistry:
    """Discover and use skills from remote A2A agents"""

    def __init__(self):
        self.client = A2AClient()
        self.remote_agents = {}

    def discover_agents(self, tags: List[str]) -> List[Dict]:
        """Query agent registry"""
        agents = self.client.registry.search(tags=tags)
        return agents

    def call_remote_skill(self, agent_url: str, task: str) -> Any:
        """Execute task on remote agent"""
        result = self.client.call_task(
            agent_url=agent_url,
            task=task,
        )
        return result

# Usage
remote_registry = RemoteSkillRegistry()

# Find agents that can search papers
agents = remote_registry.discover_agents(tags=["research", "academic"])

# Call first agent that matches
result = remote_registry.call_remote_skill(
    agent_url=agents[0]["serviceEndpoint"],
    task="Search for papers on transformers published in 2024"
)
```

---

## 7. Implementation Timeline for AI-Researcher

### Phase 2c (Current): Tool Discovery Foundation
- [x] Understand tool discovery patterns
- [x] Analyze current skill architecture
- [ ] Add tool search with embeddings
- [ ] Add A2A Agent Card export
- [ ] Document patterns for future developers

### Phase 2d (Next): Dynamic Tool Availability
- [ ] Implement MCP tool notifications
- [ ] Add conditional tool availability
- [ ] Support dynamic tool binding with LangGraph
- [ ] Create tests for tool availability scenarios

### Phase 2e (Future): Multi-Agent Discovery
- [ ] Implement A2A client
- [ ] Add remote agent discovery
- [ ] Support cross-agent task invocation
- [ ] Create federation examples

### Phase 3+ (Scaling): External Plugin Distribution
- [ ] Migrate to setuptools entry points (if needed)
- [ ] Create plugin development guide
- [ ] Set up plugin registry/marketplace
- [ ] Add plugin signing/verification

---

## 8. Decision Matrix: Which Pattern to Use?

```
Question 1: Are plugins distributed as separate packages?
    ├─ NO → Go to Q2
    └─ YES → Use setuptools entry points + Stevedore

Question 2: Need runtime tool change notifications?
    ├─ NO → Use current filesystem approach
    └─ YES → Add MCP notifications layer

Question 3: More than 100 tools in catalog?
    ├─ NO → Use list_available() with simple enumeration
    └─ YES → Implement tool search with embeddings

Question 4: Need cross-agent discovery?
    ├─ NO → Stop here, you're good
    └─ YES → Export A2A Agent Card + implement client

Question 5: Need version management per tool?
    ├─ NO → Current approach works
    └─ YES → Add version constraints to dependencies
```

---

## 9. Recommended Resources & Tools

### Python Plugin Frameworks
- **Stevedore:** https://openstack.org/stevedore/ (mature, enterprise)
- **Plux:** https://pypi.org/project/plux/ (modern, 2025)
- **Pluggy:** Used by pytest, https://pluggy.readthedocs.io/
- **Entry Points:** https://packaging.python.org/guides/creating-and-discovering-plugins/

### Vector Search / Embeddings
- **Sentence Transformers:** https://www.sbert.net/
- **FAISS:** Facebook's vector search (fast, scalable)
- **LangChain Embeddings:** https://python.langchain.com/docs/guides/embeddings/
- **Anthropic API:** embeddings endpoint (March 2026)

### Agent Protocols
- **A2A Protocol:** https://a2a-protocol.org/latest/specification/
- **MCP Specification:** https://modelcontextprotocol.io/
- **LangGraph:** https://www.langchain.com/langgraph

### Monitoring & Observability
- **OpenTelemetry:** Standard for instrumentation
- **Prometheus:** Metrics collection
- **Jaeger:** Distributed tracing for multi-agent systems

---

**Document Version:** 1.0
**Last Updated:** March 15, 2026
**Ready for:** Implementation planning & Phase 2c handoff
