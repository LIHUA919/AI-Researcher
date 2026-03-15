# Tool Discovery & Dynamic Loading Mechanisms - Research Report

**Date:** March 15, 2026
**Context:** AI-Researcher Phase 2c Research
**Focus Areas:** Runtime tool discovery, plugin systems, agent capabilities, A2A integration

---

## Executive Summary

This research explores **tool discovery and dynamic loading mechanisms** crucial for building scalable AI agent systems. Key findings show:

1. **Multiple proven patterns** exist for runtime tool discovery (setuptools entry points, filesystem scanning, registry-based)
2. **LangGraph + MCP** represent the modern standard for dynamic capability binding
3. **A2A Agent Cards** provide standardized cross-agent discovery and capability advertising
4. **AI-Researcher's skill architecture** successfully implements filesystem-based discovery with clean separation between scanning and loading
5. **Security and versioning** require careful design when loading plugins dynamically

---

## Part 1: Tool Discovery Implementation Patterns

### 1.1 Overview of Approaches

#### A. Filesystem-Based Discovery (Current AI-Researcher Implementation)

**Mechanism:** Scan directories for manifest files (SKILL.md), parse metadata without importing, load modules on-demand.

**Advantages:**
- No external dependencies (setuptools not required)
- Full control over loading lifecycle
- Natural for monolithic codebases
- Two-phase design (scan → load) minimizes startup overhead
- Clear dependency management

**Disadvantages:**
- Not ideal for distributed, independently-deployed plugins
- Requires path resolution logic
- Less discoverable for external tooling

**Implementation in AI-Researcher:**

```python
# SkillLoader: Two-phase design
loader.scan()      # Reads SKILL.md files only (no imports)
loader.load(name)  # Imports Python module and resolves tools
```

Files:
- `/Users/lihua/projects/AI-Researcher/research_agent/inno/skills/loader.py` - Core scanning & loading
- `/Users/lihua/projects/AI-Researcher/research_agent/inno/skills/registry.py` - Registration & discovery
- `/Users/lihua/projects/AI-Researcher/research_agent/inno/skills/base.py` - Data models (Skill, SkillManifest)

#### B. Setuptools Entry Points

**Mechanism:** Plugins register themselves in `setup.py` with entry_points metadata. Package manager discovers entries via distribution metadata.

```python
# setup.py
entry_points={
    'myapp.plugins': [
        'plugin_a = myapp_plugin_a:Plugin',
        'plugin_b = myapp_plugin_b:Plugin',
    ]
}
```

**When to use:**
- Multi-package deployments (each plugin is separate package)
- Package ecosystems (e.g., pytest plugins, flask extensions)
- Third-party integrations (no monorepo required)

**Trade-offs:**
- Requires pip/poetry for installation
- Less flexible for runtime changes
- Better for distributed teams

#### C. Custom Registry Pattern

**Mechanism:** Central registry where plugins self-register at import time or via decorators.

```python
@register_tool
def my_tool():
    pass
```

**When to use:**
- Rapid prototyping
- Single-process applications
- Dynamic registration needed

**Trade-offs:**
- Simpler for small systems
- Doesn't scale to thousands of tools
- Requires careful import order management

#### D. Service Discovery Registry (Enterprise Pattern)

**Mechanism:** Central service (Consul, etcd, DNS) tracks available services and their capabilities.

**When to use:**
- Microservices architecture
- Runtime service addition/removal
- Enterprise deployments
- Geographic distribution

---

### 1.2 Tool Registry Management

#### Discovery vs. Availability

| Aspect | Discovery | Availability |
|--------|-----------|--------------|
| **Definition** | Can I find this tool? | Can I use this tool right now? |
| **Scope** | Metadata only | Runtime state + metadata |
| **Example** | Manifest lists "search_arxiv" | User has auth token, service is up |

#### Registry Patterns

**Pattern 1: Static Discovery, Lazy Loading**
```
scan() → get list of available tools
load() → instantiate specific tools when needed
```
*Used by:* AI-Researcher, LangChain plugins
*Benefit:* Minimal startup overhead

**Pattern 2: Dynamic Registry with Notifications**
```
Client queries: tools/list → {"tools": [...]}
Server notifies: tools/list_changed
Client refreshes tool list on-demand
```
*Used by:* MCP (Model Context Protocol)
*Benefit:* Handles runtime changes (auth, feature toggles)

**Pattern 3: Semantic Search**
```
Agent asks: "find me tools for searching papers"
Registry returns: ranked list by semantic similarity
```
*Used by:* Claude Tool Search, Spring AI
*Benefit:* Works with hundreds/thousands of tools without loading all definitions

---

## Part 2: Plugin System Comparison

### 2.1 Popular Python Plugin Frameworks

#### Stevedore (OpenStack)
- **Model:** Entry points + manager classes
- **Best for:** Large distributed systems
- **Complexity:** Medium
- **Maturity:** Production (10+ years)
- **Docs:** https://openstack.org/stevedore/

#### Plux (LocalStack, 2025)
- **Model:** Dynamic code scanning + index file
- **Best for:** Modern Python applications
- **Complexity:** Low
- **Features:**
  - Automatic discovery from code
  - Multi-package support
  - Version management
- **Docs:** https://pypi.org/project/plux/

#### Pluggy (pytest)
- **Model:** Hook specifications + hook implementations
- **Best for:** Plugin callback systems
- **Complexity:** Low-Medium
- **Maturity:** Very stable (pytest ecosystem)

#### Custom (AI-Researcher)
- **Model:** Filesystem manifest + on-demand loading
- **Best for:** Monolithic research codebases
- **Complexity:** Low
- **Advantages:** Complete control, no external dependencies

### 2.2 Framework Comparison Table

| Framework | Discovery | Loading | Versioning | Distribution | Ecosystem |
|-----------|-----------|---------|------------|--------------|-----------|
| **Setuptools Entry Points** | Metadata | Lazy | Via packages | ✓ Excellent | ✓ Large |
| **Stevedore** | Entry Points + Manager | Lazy | Via packages | ✓ Good | OpenStack |
| **Plux** | Code + Index | Lazy | Built-in | ✓ Good | Growing |
| **Pluggy** | Hook registry | Eager | Manual | Limited | pytest |
| **AI-Researcher Skills** | Filesystem scan | Lazy | Manual | Limited | Monorepo |

---

## Part 3: Dynamic Tool Discovery in Modern Agents

### 3.1 LangGraph: Runtime Tool Binding

**Key Feature:** Dynamic Tool Calling (introduced August 2025)

```python
# Tools are not fixed at agent creation
# Control which tools are available at different workflow steps

state = {
    "available_tools": [...],  # Changes per step
    "messages": [...]
}
```

**Benefits:**
- Tool availability changes based on workflow state
- Reduces token consumption (only load needed tools)
- Supports conditional routing

**Integration with MCP:**
- LangGraph StateGraph routes tasks between agents
- MCP ensures tool/resource access across agents
- Together they enable adaptive workflows

**Relevant:** Will be integrated with DAG workflow orchestration (Phase 2a)

### 3.2 Claude API: Tool Search & Tool Use Examples (2025)

**Three Beta Features:**

1. **Tool Search Tool** (Dynamic Discovery)
   - Search catalog of hundreds/thousands of tools
   - Load only 3-5 tools actually needed
   - ~85% reduction in token consumption
   - Uses embeddings to find relevant tools
   - Docs: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool

2. **Programmatic Tool Calling**
   - Claude writes code to orchestrate tools
   - Multiple tool calls in single code block
   - Processes outputs, controls context
   - More efficient than round-trip calls

3. **Tool Use Examples**
   - JSON Schema alone doesn't express usage patterns
   - Examples show when to include optional params
   - Clarify which parameter combinations make sense
   - Better than schema documentation

**Relevance:** AI-Researcher can expose Tool Search for agent capability discovery

### 3.3 MCP: Server-Driven Dynamic Discovery

**Standard Pattern for Tool Notifications:**

```
Server → Client: notifications/tools/list_changed
Client → Server: tools/list (refresh)
```

**Use Cases:**
- Authentication state changes → hide tools requiring credentials
- Feature availability varies → show tools based on permissions
- Resource availability changes → hide tools for unavailable services

**Key Advantage:** Clients don't need pre-coded knowledge of all tools

**Specification:** https://modelcontextprotocol.io/legacy/concepts/tools

---

## Part 4: A2A Agent Cards & Tool Discovery

### 4.1 Agent Card Structure (A2A Protocol)

**Definition:** Self-describing JSON manifest for agent capabilities

**Published at:** `/.well-known/agent.json`

**Core Fields:**

```json
{
  "name": "Research Agent",
  "description": "Academic paper research and analysis",
  "provider": "HKUDS",
  "serviceEndpoint": "https://api.example.com/a2a",

  "capabilities": {
    "skills": [
      {
        "name": "arxiv_search",
        "description": "Search arXiv papers",
        "tools": ["search_arxiv", "download_arxiv_source"],
        "tags": ["research", "academic"],
        "authRequired": "openai_api_key"
      }
    ],
    "features": ["streaming", "statefulness"],
    "supportedFormats": ["json-rpc"]
  },

  "authentication": {
    "type": "bearer",
    "required": ["OPENAI_API_KEY"]
  }
}
```

### 4.2 Discovery Mechanisms

#### Discovery Pattern 1: Direct Connection
```
Client asks Agent: GET /.well-known/agent.json
Agent responds: Agent Card with capabilities
```

#### Discovery Pattern 2: Registry-Based
```
Central Registry maintains Agent Cards
Client queries: GET /registry?tags=research
Registry returns: [Agent1, Agent2, ...]
Client evaluates and selects best agent
```

### 4.3 A2A Integration with Skills

**Mapping Skills to Agent Cards:**

```
SkillManifest (current)          Agent Card (A2A)
├─ name                          ├─ skill.name
├─ description                   ├─ skill.description
├─ tools: [list]                 ├─ skill.tools: [...]
├─ tags                          ├─ tags
├─ required_config               └─ authentication requirements
└─ instructions

Agent as A2A Server:
├─ Publishes: /.well-known/agent.json
├─ Lists Skills in capabilities section
└─ Tools as discoverable endpoints
```

### 4.4 Cross-Agent Tool Discovery (A2A)

**Workflow:**

1. **Client Agent** needs to search papers
2. **Discovers** via A2A: `GET /registry?tags=research`
3. **Evaluates** capabilities in Agent Card
4. **Calls** remote agent: `POST /a2a/tasks` with task description
5. **Remote Agent** selects appropriate skill (arxiv_search)
6. **Returns** results via A2A protocol

**Industry Adoption:** 50+ partners (Atlassian, Box, Cohere, LangChain, MongoDB, PayPal, Salesforce, ServiceNow)

**Specification:** https://a2a-protocol.org/latest/specification/

---

## Part 5: Versioning & Compatibility in Plugin Systems

### 5.1 Semantic Versioning for Plugins

**Standard:** Semantic Versioning 2.0.0 (https://semver.org/)

```
MAJOR.MINOR.PATCH
└─ 1.2.3

MAJOR: Backward incompatible API changes
MINOR: New features (backward compatible)
PATCH: Bug fixes
```

**Current AI-Researcher:** All pilot skills at version 0.1.0 (pre-release)

### 5.2 Dependency Management

**Current Implementation:**

```yaml
# SKILL.md
dependencies:
  - arxiv_search
  - paper_search (optional)
```

**Loader Logic:**
- Required dependencies must load successfully
- Optional dependencies fail gracefully
- Transitive dependencies resolved recursively

**Enhancement Opportunities:**
- Add version constraints: `arxiv_search>=0.2.0,<1.0.0`
- Conflict detection: prevent incompatible versions
- Version pinning per workflow

### 5.3 Multi-Version Support

**Pattern from Kestra (2025):**
- Multiple versions of same skill on same instance
- Pin specific versions per workflow
- Isolate versions to prevent conflicts

**Benefits:**
- Gradual migration (old + new versions coexist)
- A/B testing different skill versions
- Rollback capability

**Challenges:**
- Tool name conflicts across versions
- Dependency resolution complexity
- State migration

### 5.4 Compatibility Constraints

**Best Practices:**

1. **Specify version ranges** in dependencies
2. **Test against** minimum and maximum versions
3. **Document** breaking changes clearly
4. **Provide migration guides** for major versions
5. **Use feature flags** for gradual rollouts

---

## Part 6: Security & Sandboxing in Dynamic Loading

### 6.1 Security Challenges with Dynamic Loading

**Problem:** Unlike traditional applications where developers review every line, **dynamic plugin loading** executes untrusted code.

**Attack Vectors:**
1. **Malicious plugins:** Plugin source code could be compromised
2. **Supply chain attacks:** Dependency poisoning
3. **Prompt injection parallels:** Plugins could be manipulated via input
4. **Data exfiltration:** Plugins could steal secrets or data

### 6.2 Isolation Technologies

#### MicroVMs (Strongest)
- Each workload in own kernel
- Prevents container escape vulnerabilities
- **Trade-off:** Higher resource overhead
- **Best for:** Untrusted code

#### gVisor (Medium)
- User-space kernel mediating syscalls
- Weaker than MicroVMs but better than containers
- **Trade-off:** Performance overhead
- **Good for:** Restricted but trusted code

#### Containers (Weak)
- Process isolation via Linux namespaces + cgroups
- Shared kernel vulnerability risk
- **Trade-off:** Minimal overhead
- **Good for:** Known/trusted plugins

### 6.3 Defense-in-Depth Strategy

1. **Sandboxing:** Isolate execution environment
2. **Signed artifacts:** Verify plugin provenance
3. **Approval gates:** Human review before loading
4. **Monitoring:** Log all plugin activities
5. **Least privilege:** Minimal permissions per plugin

### 6.4 AI-Researcher Recommendations

**Current State:**
- Skills loaded from trusted filesystem locations
- No external plugin sources
- Suitable for research environments

**If expanding to external plugins:**
1. Implement plugin signing/verification
2. Use setuptools entry points (curated packages)
3. Require approval workflow for new plugins
4. Run in containers at minimum, MicroVMs ideal
5. Monitor resource usage (CPU, memory, network)

**Resources:**
- https://northflank.com/blog/how-to-sandbox-ai-agents
- https://developer.nvidia.com/blog/practical-security-guidance-for-sandboxing-agentic-workflows-and-managing-execution-risk/

---

## Part 7: AI-Researcher Skill Discovery Architecture Analysis

### 7.1 Current Implementation

**Files:**
- Loader: `/Users/lihua/projects/AI-Researcher/research_agent/inno/skills/loader.py`
- Registry: `/Users/lihua/projects/AI-Researcher/research_agent/inno/skills/registry.py`
- Base Models: `/Users/lihua/projects/AI-Researcher/research_agent/inno/skills/base.py`
- Tests: `/Users/lihua/projects/AI-Researcher/tests/test_skills/test_pilot_skills.py`

**Architecture Strengths:**

1. **Clean Separation of Concerns**
   - Scanning phase (metadata only)
   - Loading phase (module imports)
   - Registration phase (tool injection)

2. **Lazy Loading**
   - No performance penalty for unused skills
   - Minimal startup overhead
   - On-demand resource allocation

3. **Dependency Tracking**
   - Recursive dependency resolution
   - Optional vs. required distinction
   - Clear error reporting

4. **Integration with Existing Registry**
   - Composable with existing tool system
   - Tools exported to existing @register_tool decorator
   - Backward compatible

5. **Manifest-Based Metadata**
   - Human-readable SKILL.md files
   - Version info, author, tags
   - Instructions for agents
   - No schema/type information needed

### 7.2 Comparison with Other Approaches

**vs. Setuptools Entry Points:**
- ✓ No external package manager needed
- ✓ Simpler for monorepo
- ✗ Less suitable for external plugins

**vs. Dynamic Registry:**
- ✓ Explicit scanning control
- ✓ Clear loading lifecycle
- ✗ Less dynamic (requires restart for new skills)

**vs. Stevedore:**
- ✓ Simpler, fewer dependencies
- ✗ Less mature, fewer features
- ✗ Limited to package-based plugins

### 7.3 Current Limitations & Enhancement Opportunities

| Limitation | Impact | Enhancement |
|-----------|--------|------------|
| No version constraints | Can load incompatible skills | Add `skill>=0.2.0` syntax |
| No tool schema info | Claude can't know parameter types | Add JSON Schema to SKILL.md |
| No auth/config validation | Silent failures at runtime | Validate config before load |
| No runtime notifications | Changes require restart | Add list_changed notifications |
| No tool search/ranking | Only enumeration possible | Add semantic search via embeddings |
| No versioning conflict detection | Multiple versions could collide | Namespace or version pinning |

---

## Part 8: Recommendations for AI-Researcher Phase 2c

### 8.1 Tool Discovery Enhancement (Short-term)

**1. Add Schema to Skill Manifests**
```yaml
## Tools
- search_arxiv
  description: Search arXiv papers by keyword
  parameters:
    query:
      type: string
      description: Search query
    limit:
      type: integer
      default: 10
```

**Benefit:** Claude can understand parameter types without importing

**2. Implement Tool Search**
```python
skill_registry.search_tools("search papers", limit=5)
# Returns: [("arxiv_search.search_arxiv", 0.94), ...]
```

**Benefit:** Reduce tokens for large tool sets, match Claude's Tool Search feature

**3. Add Configuration Validation**
```python
loader.load("arxiv_search",
            config={"OPENAI_API_KEY": "sk-..."})
# Validates required_config before loading
```

**Benefit:** Catch configuration errors early, provide better error messages

### 8.2 Dynamic Discovery (Medium-term)

**1. Implement MCP Pattern**
```python
skill_registry.notify_tools_changed()  # Client polls /tools/list
```

**Benefit:** Matches MCP standard, allows runtime tool changes

**2. Add A2A Agent Card Export**
```python
agent_card = skill_registry.to_agent_card()
# {
#   "name": "AI-Researcher Agent",
#   "capabilities": {"skills": [...]}
# }
```

**Benefit:** Enables cross-agent discovery, integration with A2A protocol

**3. Support Multiple Skill Directories**
```python
loader = SkillLoader(skill_dirs=[
    "/builtin/skills",
    "/user/skills",
    "/third-party/skills"
])
```

**Benefit:** Hierarchical skill discovery, user extensions

### 8.3 Versioning & Compatibility (Medium-term)

**1. Add Version Constraints**
```yaml
dependencies:
  - arxiv_search>=0.2.0,<1.0.0
  - paper_search
```

**2. Implement Compatibility Matrix**
```python
# Check if skill versions are compatible
validator = VersionValidator()
validator.check_compatibility(
    skill_versions={"arxiv": "0.3.0", "paper": "0.2.0"}
)
```

**3. Support Multi-Version Loading**
```python
loader.load("arxiv_search", version="0.2.0")
loader.load("arxiv_search", version="0.3.0")
# Different versions coexist
```

### 8.4 Agent Capability Binding (Long-term)

**Integration with LangGraph + A2A:**

```python
# Step 1: Create StateGraph with dynamic tools
def determine_tools(state):
    """Select tools based on workflow step"""
    if state["phase"] == "search":
        return {"available_tools": ["arxiv_search", "paper_search"]}
    elif state["phase"] == "analyze":
        return {"available_tools": ["code_search", "arxiv_search"]}

# Step 2: Export as Agent Card for A2A
agent_card = skill_registry.to_agent_card()
# Other agents can discover and call this agent

# Step 3: Call remote agent tools
client = A2AClient()
result = client.call_agent_task(
    agent_url="https://remote-agent/a2a",
    task="search recent papers on transformers",
    tools_to_use=["arxiv_search"]
)
```

---

## Part 9: Integration Map

### 9.1 Tool Discovery in AI-Researcher Architecture

```
┌─────────────────────────────────────────────────────┐
│ LangGraph StateGraph (Phase 2a)                     │
│ - DAG workflow orchestration                        │
│ - Conditional routing: which tools per step?        │
└────────────┬────────────────────────────────────────┘
             │ Determines available tools
             ▼
┌─────────────────────────────────────────────────────┐
│ Skill Registry + Discovery (Current)                │
│ - Tool discovery: list_available()                  │
│ - Tool loading: load_and_register()                 │
│ - Capability binding: get_tool_schema()             │
└────────────┬────────────────────────────────────────┘
             │ Binds tools to Claude API
             ▼
┌─────────────────────────────────────────────────────┐
│ Claude API Tool Use (Current)                       │
│ - Function calling with JSON Schema                 │
│ - Tool search (dynamic discovery, 2025)             │
│ - Programmatic tool calling (2025)                  │
└────────────┬────────────────────────────────────────┘
             │ Results flow back
             ▼
┌─────────────────────────────────────────────────────┐
│ A2A Agent Protocol (Phase 2c)                       │
│ - Agent Card export: /.well-known/agent.json        │
│ - Cross-agent discovery: registry lookups           │
│ - Remote task invocation: A2A client calls          │
└─────────────────────────────────────────────────────┘
```

### 9.2 Tool Discovery Pipeline

```
Research Question
    │
    ▼
Determine Required Tools
(LangGraph: conditional routing)
    │
    ▼
Query Skill Registry
(search_tools by tags/keywords)
    │
    ├─ Local tools found?
    │  └─ Load skill + bind to Claude
    │
    └─ Local tools insufficient?
       └─ A2A discovery: query agent registry
          └─ Call remote agent + integrate results
```

---

## Part 10: Key Takeaways & References

### 10.1 Core Principles

1. **Two-Phase Loading:** Scan metadata separately from module imports
2. **Lazy Evaluation:** Only load tools when needed
3. **Registry Pattern:** Centralize tool discovery and registration
4. **Version Awareness:** Track compatibility constraints
5. **Dynamic Binding:** Tools can change based on workflow state
6. **Sandboxing:** Isolate untrusted plugin code
7. **Standardization:** Align with MCP and A2A protocols

### 10.2 Recommended Reading

**Plugin Systems:**
- [How to Build Plugin Systems in Python](https://oneuptime.com/blog/post/2026-01-30-python-plugin-systems/view)
- [Creating and discovering plugins - Python Packaging](https://packaging.python.org/guides/creating-and-discovering-plugins/)
- [Stevedore Documentation](https://openstack.org/stevedore/)

**Dynamic Tool Discovery:**
- [Claude API Tool Search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- [MCP Tools Specification](https://modelcontextprotocol.io/legacy/concepts/tools)
- [MCP Dynamic Tool Discovery](https://www.speakeasy.com/mcp/tool-design/dynamic-tool-discovery)

**Agent Architecture:**
- [LangGraph Documentation](https://www.langchain.com/langgraph)
- [LangGraph Dynamic Tool Calling](https://changelog.langchain.com/announcements/dynamic-tool-calling-in-langgraph-agents)
- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)

**Security:**
- [Sandboxing AI Agents (2026)](https://northflank.com/blog/how-to-sandbox-ai-agents)
- [NVIDIA Security Guidance for Agentic Workflows](https://developer.nvidia.com/blog/practical-security-guidance-for-sandboxing-agentic-workflows-and-managing-execution-risk/)

### 10.3 Implementation Checklist for AI-Researcher

- [ ] Add JSON Schema support to SKILL.md format
- [ ] Implement tool semantic search (embeddings)
- [ ] Add version constraint parsing
- [ ] Export A2A Agent Card
- [ ] Implement MCP notifications pattern
- [ ] Add configuration validation
- [ ] Support multiple skill directories
- [ ] Create tool discovery examples/tutorials
- [ ] Add security guidance for external plugins

---

## Appendix: Code Examples

### A.1 Current Skill Loading Flow

```python
# Step 1: Scan (no imports)
loader = SkillLoader()
manifests = loader.scan()  # Returns: {"arxiv_search": SkillManifest(...), ...}

# Step 2: Load (import module)
skill = loader.load("arxiv_search")  # Returns: Skill with functions=[search_arxiv, ...]

# Step 3: Register (inject into base registry)
skill_registry = SkillRegistry()
skill_registry.register_skill(skill)

# Step 4: Use (call tools)
tools = skill_registry.get_skill_tools("arxiv_search")
result = tools[0](query="transformers")  # Call search_arxiv
```

### A.2 Manifest Parsing

```python
# Current SKILL.md format
# Name: arxiv_search
# Version: 0.1.0
# Description: Search academic papers
# Tools:
# - search_arxiv
# - download_arxiv_source
# Dependencies:
# - paper_search (optional)

# Parsed into:
manifest = SkillManifest(
    name="arxiv_search",
    version="0.1.0",
    description="Search academic papers",
    tools=["search_arxiv", "download_arxiv_source"],
    dependencies=[SkillDependency(skill_name="paper_search", optional=True)]
)
```

### A.3 A2A Agent Card Example

```json
{
  "name": "AI-Researcher Agent",
  "description": "Autonomous research agent for academic paper discovery and analysis",
  "provider": "HKUDS",
  "version": "0.2.0",
  "serviceEndpoint": "https://researcher.example.com/a2a",

  "capabilities": {
    "skills": [
      {
        "name": "arxiv_search",
        "description": "Search and analyze academic papers from arXiv",
        "tools": [
          "search_arxiv",
          "download_arxiv_source",
          "extract_tex_content"
        ],
        "tags": ["research", "academic", "papers"],
        "requiredConfig": ["OPENAI_API_KEY"]
      },
      {
        "name": "code_search",
        "description": "Search GitHub repositories",
        "tools": ["search_github_repos"],
        "tags": ["code", "github", "research"]
      }
    ],
    "features": ["streaming", "statefulness"],
    "supportedProtocols": ["json-rpc"]
  },

  "authentication": {
    "type": "bearer",
    "required": ["OPENAI_API_KEY"]
  }
}
```

---

**Document Version:** 1.0
**Last Updated:** March 15, 2026
**Status:** Ready for Phase 2c Implementation
