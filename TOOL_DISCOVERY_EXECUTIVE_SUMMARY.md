# Tool Discovery & Dynamic Loading - Executive Summary

**Date:** March 15, 2026 | **Status:** Phase 2c Research Complete

## Quick Decision Table

| Question | Answer | Action |
|----------|--------|--------|
| **What is tool discovery?** | Runtime mechanism to find available tools/capabilities | Critical for scalable agent systems |
| **Best pattern for AI-Researcher now?** | Filesystem + Registry (current) | Keep & enhance with P1 upgrades |
| **When to switch to Entry Points?** | Phase 3+ if distributing external plugins | Document migration path |
| **How to scale from 50 to 500+ tools?** | Semantic search with embeddings | 85% token savings |
| **How do agents find each other's tools?** | A2A Agent Cards @ /.well-known/agent.json | Standard, 50+ partners |
| **Which framework: Stevedore vs Plux vs custom?** | Custom for now, Setuptools later | No breaking changes |

---

## Core Concepts (5-Minute Overview)

### Tool Discovery Levels

```
Level 1: Static Enumeration
├─ List all available tools upfront
├─ Suitable for <20 tools
└─ Current AI-Researcher approach

Level 2: Dynamic Availability
├─ Tools appear/disappear based on context (auth, workflow phase)
├─ Suitable for 20-100 tools
└─ LangGraph StateGraph support

Level 3: Semantic Search
├─ Find relevant tools via embeddings (query similarity)
├─ Suitable for 100-10,000 tools
├─ Claude Tool Search (2025)
└─ Reduces tokens ~85%

Level 4: Cross-Agent Discovery
├─ Find tools on remote agents via A2A
├─ Suitable for distributed systems
└─ A2A Agent Cards + registry
```

### Three Plugin Patterns Explained

| Pattern | When | Example |
|---------|------|---------|
| **Filesystem** | Monorepo, local development | AI-Researcher now (✓) |
| **Entry Points** | Distributed packages, package ecosystems | pytest plugins, AI-Researcher Phase 3 |
| **Registry** | Microservices, dynamic runtime changes | Cloud agents, Kubernetes |

---

## What AI-Researcher Does Well (Phase 1)

✓ **SkillLoader** - Two-phase design (scan → load)
✓ **SkillRegistry** - Clean registration with existing tools
✓ **Manifests** - Human-readable SKILL.md files
✓ **Dependencies** - Recursive resolution with optional distinction
✓ **Lazy Loading** - No performance penalty for unused skills
✓ **Backward Compatible** - Composes with existing Registry

---

## Critical Gaps to Close (Phase 2c Enhancements)

| Gap | Impact | Solution | Effort |
|-----|--------|----------|--------|
| **No parameter schema** | Claude can't know tool inputs | Add JSON Schema to SKILL.md | 4h |
| **No tool search** | Scales poorly above 50 tools | Embeddings + similarity search | 8h |
| **No A2A export** | Can't advertise capabilities to other agents | to_agent_card() method | 3h |
| **No change notifications** | Tools require restart to update | MCP notifications pattern | 6h |
| **No version management** | Can't handle skill version conflicts | Version constraints parsing | 5h |

**Total P1 Effort:** ~40 hours (1 week FTE)

---

## Implementation Roadmap

### Week 1: Foundation (P1 Enhancements)
- [ ] Add JSON Schema to SKILL.md format
- [ ] Implement tool search with embeddings
- [ ] Create examples & documentation
- [ ] Write unit tests for new features

### Week 2: Integration (P2 Enhancements)
- [ ] Export A2A Agent Card
- [ ] Add MCP notifications pattern
- [ ] Integration test with LangGraph
- [ ] Performance benchmarks

### Week 3+: Advanced (P3+)
- [ ] Version constraints in dependencies
- [ ] Multi-directory support
- [ ] Plugin approval workflow
- [ ] Security hardening for external plugins

---

## Key Technologies & Standards

### Proven & Recommended
- ✓ **LangGraph** - Workflow orchestration with dynamic tools
- ✓ **MCP** - Standard for tool/resource access
- ✓ **Claude API Tool Search** - Built-in dynamic discovery (2025)
- ✓ **A2A Protocol** - Agent-to-agent discovery standard

### Libraries for Enhancements
- **sentence-transformers** - Embedding model for tool search
- **importlib.metadata** - Entry points discovery (future)
- **stevedore** - Plugin manager (future)

### Standards Aligned With
- **Semantic Versioning** - Version management
- **JSON Schema** - Tool parameter specification
- **MCP 1.0** - Tool notifications
- **A2A 0.2.5+** - Agent discovery

---

## Quick Reference: File Locations

**Current Implementation:**
- Registry: `/research_agent/inno/skills/registry.py` (SkillRegistry)
- Loader: `/research_agent/inno/skills/loader.py` (SkillLoader)
- Models: `/research_agent/inno/skills/base.py` (Skill, SkillManifest)
- Tests: `/tests/test_skills/test_pilot_skills.py` (71 tests)

**Skills:**
- arxiv_search: `/research_agent/inno/skills/arxiv_search/`
- paper_search: `/research_agent/inno/skills/paper_search/`
- planning: `/research_agent/inno/skills/planning/`
- code_search: `/research_agent/inno/skills/code_search/`
- file_operations: `/research_agent/inno/skills/file_operations/`

**Research Documents:**
- `/TOOL_DISCOVERY_RESEARCH.md` - Comprehensive 10-part analysis
- `/PLUGIN_FRAMEWORK_COMPARISON.md` - Framework comparison & patterns

---

## API Design Examples (For Implementation)

### Tool Search Addition
```python
# New API
registry.search_tools("search papers", limit=5)
# Returns: [("arxiv_search.search_arxiv", 0.94), ("paper_search.get_meta", 0.87), ...]

# Benefit: Reduce context window from 55k to ~5k tokens (85% savings)
```

### A2A Export Addition
```python
# New API
agent_card = registry.to_agent_card()
# Returns JSON ready for /.well-known/agent.json

# Benefit: Other agents can discover this agent's capabilities
```

### MCP Pattern Addition
```python
# New API
registry.notify_tools_changed()
# Notifies MCP client: notifications/tools/list_changed

# Benefit: Runtime tool updates without restart
```

---

## Decision: Current vs. Alternative Approaches

### Why Keep Current Filesystem Approach?

✓ **Simplicity**: No external dependencies, full control
✓ **Development**: Fast iteration, natural for monorepo
✓ **Testing**: Easy to test with temporary skill directories
✓ **Learning**: Team understands the code
✗ **Scaling**: Not ideal for distributed external plugins
✗ **Standards**: Less aligned with Python ecosystem

### When to Migrate to Setuptools Entry Points?

**Triggers:**
- Distributing skills as separate PyPI packages
- Third-party developers submitting plugins
- Need for version management per plugin
- Want pip to auto-discover skills

**Timeline:** Phase 3+ (probably 6+ months)

**Migration Path:**
1. Keep current SkillLoader API (no breaking changes)
2. Add entry_points support as alternative discovery method
3. Deprecate (but don't remove) filesystem scanning
4. Provide migration guide for external developers

---

## Competitive Analysis

### How Others Solve This

| System | Approach | Maturity |
|--------|----------|----------|
| **Claude Skills** | Skill cards + dynamic prompt generation | March 2025 ✓ |
| **Tool Search** | Embeddings-based tool discovery | February 2025 ✓ |
| **LangGraph** | StateGraph dynamic tool control | v1.0 stable ✓ |
| **MCP** | notifications/tools/list_changed | 1.0 stable ✓ |
| **A2A Protocol** | Agent Cards @ /.well-known/ | 0.2.5 stable ✓ |

**Takeaway:** All major platforms moving toward dynamic discovery. AI-Researcher should align with these patterns.

---

## Security Checklist

**Current (Appropriate for Research):**
- [ ] Skills loaded from trusted filesystem
- [ ] No external plugin sources
- [ ] No untrusted code execution

**If Expanding to External Plugins:**
- [ ] Plugin signing/verification
- [ ] MicroVM isolation for untrusted code
- [ ] Approval workflow before loading
- [ ] Resource limits (CPU, memory, network)
- [ ] Security audit of new plugins
- [ ] Disable dangerous syscalls via gVisor/seccomp

---

## Success Metrics (Post-Implementation)

1. **Context Window Efficiency**
   - Before: Tool definitions consume ~55k tokens
   - Target: Tool search reduces to ~5k tokens (85% savings)
   - Measurement: tokens_for_tool_defs in production

2. **Startup Time**
   - Target: No regression despite new features
   - Measurement: Time to first skill query

3. **Discoverability**
   - Target: Remote agents can see AI-Researcher capabilities
   - Measurement: A2A agent card properly formatted

4. **Compatibility**
   - Target: 100% backward compatible
   - Measurement: All existing tests still pass + 71 new tests

---

## Documentation Structure

**For Developers:**
- `TOOL_DISCOVERY_RESEARCH.md` - Deep dive (all patterns, standards, code examples)
- `PLUGIN_FRAMEWORK_COMPARISON.md` - Framework details & implementation patterns

**For Users:**
- Quick reference (this document)
- Skill development guide
- Agent integration guide

**For Decision Makers:**
- Effort estimates & timelines
- Risk assessment
- ROI analysis

---

## Next Steps

**Immediate (This Week):**
1. Review this executive summary with team
2. Decide on Phase 2c budget allocation
3. Estimate availability of P1 developer resources

**Week 1-2 (P1 Enhancements):**
1. Implement JSON Schema support
2. Add embedding-based tool search
3. Write comprehensive tests

**Week 2-3 (P2 Integration):**
1. Implement A2A Agent Card export
2. Add MCP notifications pattern
3. Integration tests with LangGraph

**Documentation:**
1. Skill development best practices
2. Tool search usage guide
3. A2A integration examples

---

## FAQ (Common Questions)

**Q: Do we need to rewrite anything?**
A: No. All changes are additive. Current code continues working.

**Q: How long to implement P1?**
A: ~40 hours (1 week FTE) for all P1 items.

**Q: Can we do this gradually?**
A: Yes. Start with JSON Schema (4h), then tool search (8h), then others.

**Q: What's the security risk?**
A: Low if keeping filesystem approach. Only a concern with external plugins (Phase 3+).

**Q: Does this lock us into any vendor?**
A: No. Following open standards (MCP, A2A, Semantic Versioning).

**Q: What if we don't do anything?**
A: Skills work fine as-is for small scale. Hits limits at 50+ tools (context window).

---

## References & Resources

**Must-Read:**
- Claude API Docs: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool
- MCP Spec: https://modelcontextprotocol.io/legacy/concepts/tools
- A2A Spec: https://a2a-protocol.org/latest/specification/
- LangGraph Docs: https://www.langchain.com/langgraph

**Nice-to-Read:**
- Plugin Systems in Python: https://oneuptime.com/blog/post/2026-01-30-python-plugin-systems/
- Semantic Versioning: https://semver.org/
- Setuptools Entry Points: https://packaging.python.org/guides/creating-and-discovering-plugins/

---

**Version:** 1.0
**Prepared by:** Phase 2c Research
**Status:** Ready for implementation planning
