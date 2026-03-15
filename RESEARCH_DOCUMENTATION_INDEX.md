# Tool Discovery & Dynamic Loading Research - Documentation Index

**Phase 2c Research Complete** | March 15, 2026

## Quick Navigation

### For Decision Makers (15 min read)
→ **[TOOL_DISCOVERY_EXECUTIVE_SUMMARY.md](TOOL_DISCOVERY_EXECUTIVE_SUMMARY.md)**
- Quick decision table (when to use which pattern)
- Implementation roadmap with effort estimates
- Risk & security assessment
- Success metrics

### For Architects & Technical Leads (45 min read)
→ **[TOOL_DISCOVERY_RESEARCH.md](TOOL_DISCOVERY_RESEARCH.md)** (10 parts, 45 sections)
- Part 1: Implementation patterns (filesystem, entry points, registry, service discovery)
- Part 2: Plugin system comparison table
- Part 3: Dynamic tool discovery in modern agents (LangGraph, Claude API, MCP)
- Part 4: A2A Agent Cards & cross-agent discovery
- Part 5: Versioning & compatibility strategies
- Part 6: Security & sandboxing
- Part 7: AI-Researcher skill architecture analysis
- Part 8: Recommendations for Phase 2c enhancements
- Part 9: Integration map with existing systems
- Part 10: Key takeaways & references

### For Developers (120 min detailed reference)
→ **[PLUGIN_FRAMEWORK_COMPARISON.md](PLUGIN_FRAMEWORK_COMPARISON.md)** (9 sections)
- Section 1: Setuptools entry points (with code examples)
- Section 2: Stevedore (manager classes, when to use)
- Section 3: Plux (modern alternative, 2025)
- Section 4: Dynamic tool discovery patterns (embeddings, conditional availability, caching)
- Section 5: MCP integration patterns (notifications, server-side, client-side)
- Section 6: A2A Agent Card implementation (export, discovery, client)
- Section 7: Implementation timeline
- Section 8: Decision matrix (which pattern to use)
- Section 9: Tools & resources

### For Implementation (Ready-to-Code Guides)
**See sections in PLUGIN_FRAMEWORK_COMPARISON.md:**
- Tool search with embeddings (Section 4.1)
- Conditional tool availability (Section 4.2)
- Tool caching & invalidation (Section 4.3)
- MCP notifications (Section 5)
- A2A Agent Card export (Section 6)

---

## Document Characteristics

| Document | Purpose | Audience | Depth | Time |
|----------|---------|----------|-------|------|
| **Executive Summary** | Decision support | Managers, leads | 30,000 ft | 15 min |
| **Main Research** | Comprehensive analysis | Architects, tech leads | Ground level | 45 min |
| **Framework Comparison** | Implementation details | Developers, engineers | Code-level | 120 min |

---

## Key Sections by Topic

### Tool Discovery Patterns
- **Entry Points**: RESEARCH.md Part 1.1B + COMPARISON.md Section 1
- **Filesystem**: RESEARCH.md Part 1.1A (current AI-Researcher)
- **Custom Registry**: RESEARCH.md Part 1.1C
- **Service Discovery**: RESEARCH.md Part 1.1D + COMPARISON.md Section 4.3

### Plugin Systems
- **Setuptools**: COMPARISON.md Section 1 (4 pages)
- **Stevedore**: COMPARISON.md Section 2 (3 pages)
- **Plux**: COMPARISON.md Section 3 (2 pages)
- **Comparison Matrix**: RESEARCH.md Part 2.2, COMPARISON.md Section 2.4

### Dynamic Discovery at Scale
- **Tool Search**: RESEARCH.md Part 3.2 + COMPARISON.md Section 4.1
- **Embeddings Code**: COMPARISON.md Section 4.1 (copy-paste ready)
- **Conditional Availability**: COMPARISON.md Section 4.2
- **Caching**: COMPARISON.md Section 4.3

### Cross-Agent Integration
- **A2A Agent Cards**: RESEARCH.md Part 4 (comprehensive)
- **Agent Card Structure**: RESEARCH.md Part 4.1 + COMPARISON.md Section 6.1
- **Discovery Mechanisms**: RESEARCH.md Part 4.2
- **A2A Integration**: COMPARISON.md Section 6.1-6.3 (ready to implement)

### Versioning & Compatibility
- **Semantic Versioning**: RESEARCH.md Part 5.1
- **Dependency Management**: RESEARCH.md Part 5.2-5.4
- **Multi-Version Support**: RESEARCH.md Part 5.3

### Security
- **Current Assessment**: RESEARCH.md Part 6 + EXECUTIVE SUMMARY FAQ
- **MicroVM Approach**: RESEARCH.md Part 6.2
- **Defense-in-Depth**: RESEARCH.md Part 6.3
- **AI-Researcher Recommendations**: RESEARCH.md Part 6.4

### AI-Researcher Specific
- **Current Architecture**: RESEARCH.md Part 7.1 + EXECUTIVE.md Quick Reference
- **Strengths/Gaps**: RESEARCH.md Part 7.2-7.3 + EXECUTIVE.md Gaps
- **Enhancement Roadmap**: RESEARCH.md Part 8.1-8.4 + EXECUTIVE.md Roadmap

---

## Implementation Checklists

### P1 Priority (Week 1) - 40 hours
From RESEARCH.md Part 8.1:
- [ ] Add JSON Schema to SKILL.md format
- [ ] Implement tool search with embeddings
- [ ] Write unit tests
- [ ] Create usage examples

**Code snippets**: See COMPARISON.md Section 4.1 (copy-paste ready)

### P2 Priority (Week 2) - 30 hours
From RESEARCH.md Part 8.2:
- [ ] Implement MCP notifications pattern
- [ ] Add A2A Agent Card export
- [ ] Integration test with LangGraph

**Code snippets**: See COMPARISON.md Sections 5-6

### P3+ Priority (Future)
From RESEARCH.md Part 8.3-8.4:
- [ ] Version constraints in dependencies
- [ ] Multi-directory support
- [ ] Plugin approval workflow
- [ ] Migration to setuptools (Phase 3+)

---

## Decision Framework

### "Which Pattern Should I Use?"
→ See EXECUTIVE SUMMARY: Quick Decision Table (30 seconds)

### "Should We Migrate to Entry Points?"
→ PLUGIN_FRAMEWORK_COMPARISON.md Section 1.5 (Triggers & timeline)

### "How to Scale from 50 to 500 Tools?"
→ TOOL_DISCOVERY_RESEARCH.md Part 3.2 + Part 8.1

### "How Do Agents Find Each Other?"
→ RESEARCH.md Part 4 (A2A Protocol, 5 pages)

### "Is This Secure?"
→ EXECUTIVE SUMMARY FAQ + RESEARCH.md Part 6

### "What Effort/Timeline?"
→ EXECUTIVE SUMMARY: Roadmap (Week 1-3, 70 hours total)

---

## Code Examples Location

All working code examples can be found in:

**COMPARISON.md Section 4: Dynamic Tool Discovery Patterns**
- Tool search with embeddings (Python, ready to adapt)
- Conditional tool availability (Python, ready to adapt)
- Tool caching & invalidation (Python, ready to adapt)

**COMPARISON.md Section 5: MCP Integration**
- Server-side tool notifications (Python)
- Client-side change handling (Python)

**COMPARISON.md Section 6: A2A Implementation**
- Agent Card export (Python, uses SkillRegistry)
- REST endpoint (Flask example)
- Remote agent client (Python)

**RESEARCH.md Part 7: Appendix**
- Skill loading flow (step-by-step)
- Manifest parsing (example)
- Agent Card JSON (complete example)

---

## Key Findings Summary

### Current State (AI-Researcher Skills)
✓ Excellent two-phase design (scan → load)
✓ Clean integration with existing Registry
✓ Lazy loading, minimal startup overhead
✓ 100% backward compatible
✗ No semantic search (hits limits at 50+ tools)
✗ No A2A export capability
✗ No parameter schema (poor for tool understanding)

### Recommended Enhancements
1. **JSON Schema** for tool parameters (4 hours)
2. **Embedding-based search** for tool discovery (8 hours)
3. **A2A Agent Card export** for cross-agent discovery (3 hours)
4. **MCP notifications** for runtime changes (6 hours)

**Total**: 40 hours (1 week) for all P1 items

### Integration Opportunity
- **LangGraph** controls which tools available per workflow step
- **MCP** standard for tool communication
- **A2A** protocol for agent-to-agent discovery
- **Claude Tool Search** can use our tool index with embeddings

---

## Standards & References

**Industry Standards Used:**
- Semantic Versioning (https://semver.org/)
- MCP 1.0 (https://modelcontextprotocol.io/)
- A2A 0.2.5+ (https://a2a-protocol.org/)
- JSON Schema for parameters

**Key Technologies:**
- **Sentence Transformers** for embeddings
- **LangGraph** for workflow orchestration
- **Claude API** for tool use
- **setuptools** for entry points (future)

**Adoption Leaders:**
- 50+ companies on A2A (Atlassian, PayPal, Salesforce, etc.)
- Major frameworks: LangChain, OpenAI, Anthropic
- Standard tool communication: MCP

---

## Questions This Research Answers

1. **How do tool discovery systems work?** → RESEARCH Part 1
2. **Which plugin system should we use?** → COMPARISON Section 2.4
3. **Can we scale from 50 to 500+ tools?** → RESEARCH Part 3.2
4. **How do agents discover each other's capabilities?** → RESEARCH Part 4
5. **What's the security model?** → RESEARCH Part 6
6. **How does AI-Researcher compare to standards?** → RESEARCH Part 7
7. **What enhancements are recommended?** → RESEARCH Part 8 + EXECUTIVE
8. **What's the implementation effort?** → EXECUTIVE.md Roadmap
9. **Which frameworks should we integrate with?** → RESEARCH Part 9
10. **Where's the code to start?** → COMPARISON.md Sections 4-6

---

## How to Use These Documents

**Step 1: Understand (30 min)**
- Read EXECUTIVE SUMMARY
- Skim RESEARCH Part 1 + Part 4

**Step 2: Plan (20 min)**
- Review EXECUTIVE SUMMARY Roadmap
- Check RESEARCH Part 8 Recommendations
- Get effort estimates

**Step 3: Implement (Multiple weeks)**
- Use COMPARISON.md Section 4-6 for code
- Reference RESEARCH.md for standards/patterns
- Update MEMORY.md with progress

**Step 4: Integrate (Ongoing)**
- Connect with LangGraph (RESEARCH Part 9)
- Expose A2A Agent Card (COMPARISON Section 6)
- Enable MCP notifications (COMPARISON Section 5)

---

## Document Statistics

| Metric | Value |
|--------|-------|
| **Total Pages** | ~100 (if printed) |
| **Total Words** | ~35,000 |
| **Code Examples** | 25+ |
| **Implementation Patterns** | 8 |
| **Framework Comparisons** | 5 |
| **Architecture Diagrams** | 3 |
| **Decision Matrices** | 4 |
| **Time to Read All** | 180 minutes |
| **Time to Skim** | 30 minutes |

---

## Next Steps

1. **This Week (Planning)**
   - [ ] Decision maker reads EXECUTIVE SUMMARY
   - [ ] Team leads read RESEARCH.md Part 7-8
   - [ ] Developers skim COMPARISON.md

2. **Next Week (Execution)**
   - [ ] Implement P1 items (40 hours)
   - [ ] Write tests
   - [ ] Update skill manifests with schema

3. **Week 3 (Integration)**
   - [ ] Add A2A export
   - [ ] MCP notifications
   - [ ] LangGraph integration test

---

**Research Completed:** March 15, 2026
**Status:** Ready for implementation
**Prepared by:** Phase 2c Research Team
**Next Checkpoint:** Implementation plan approval
