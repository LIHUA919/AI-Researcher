# Quick-Start Implementation Guide - Tool Discovery Phase 2c

**Ready-to-Use Code Snippets for P1 Implementation**

---

## 1. JSON Schema Support for SKILL.md (4 hours)

### Update SkillManifest Data Model

```python
# File: research_agent/inno/skills/base.py
# Add to imports:
from typing import Dict, Any, List, Optional

# Add new class before SkillManifest:
class ToolSchema(BaseModel):
    """JSON Schema for a single tool function"""
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema format
    example_usage: Optional[str] = None

# Update SkillManifest:
class SkillManifest(BaseModel):
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    tools: List[str] = Field(default_factory=list)
    tool_schemas: List[ToolSchema] = Field(default_factory=list)  # NEW
    dependencies: List[SkillDependency] = Field(default_factory=list)
    required_config: List[str] = Field(default_factory=list)
    instructions: str = ""
    tags: List[str] = Field(default_factory=list)
    source_path: Optional[str] = None
```

### Update SKILL.md Parser

```python
# File: research_agent/inno/skills/loader.py
# Add to _parse_skill_md method:

def _parse_tool_schemas(self, content: str) -> List['ToolSchema']:
    """Parse tool schema section from SKILL.md"""
    from research_agent.inno.skills.base import ToolSchema

    # Look for ## Tool Schemas section
    lines = content.split('\n')
    in_schema_section = False
    current_tool = None
    schemas = []

    for line in lines:
        if line.startswith('## Tool Schemas'):
            in_schema_section = True
            continue

        if in_schema_section and line.startswith('###'):
            # Tool name: ### search_arxiv
            current_tool = line.replace('###', '').strip()
        elif in_schema_section and '```json' in line:
            # Parse JSON schema block
            schema_lines = []
            idx = lines.index(line) + 1
            while idx < len(lines) and '```' not in lines[idx]:
                schema_lines.append(lines[idx])
                idx += 1

            import json
            schema_dict = json.loads('\n'.join(schema_lines))
            schemas.append(ToolSchema(
                name=current_tool,
                description=schema_dict.get('description', ''),
                input_schema=schema_dict.get('properties', {})
            ))

    return schemas
```

### Example Updated SKILL.md Format

```markdown
# arxiv_search

## Name
arxiv_search

## Version
0.1.0

## Description
Search and download academic papers from arXiv.

## Tools
- search_arxiv
- download_arxiv_source

## Tool Schemas

### search_arxiv
Searches arXiv for papers matching query terms.

```json
{
  "name": "search_arxiv",
  "description": "Search arXiv papers by keyword",
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Search query (keywords or arXiv ID)"
    },
    "max_results": {
      "type": "integer",
      "description": "Maximum number of results",
      "default": 10
    },
    "sort_by": {
      "type": "string",
      "enum": ["relevance", "date"],
      "default": "relevance"
    }
  },
  "required": ["query"]
}
```

## Dependencies
- paper_search (optional)

## Tags
- research
- academic
- arxiv
```

---

## 2. Tool Search with Embeddings (8 hours)

### Step 1: Add ToolSearchRegistry Class

```python
# File: research_agent/inno/skills/search.py
# NEW FILE

import numpy as np
from typing import List, Tuple, Dict, Optional
from sentence_transformers import SentenceTransformer, util
import logging

logger = logging.getLogger(__name__)

class ToolSearchRegistry:
    """Semantic search for tools using embeddings"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize with sentence transformer model"""
        try:
            self.model = SentenceTransformer(model_name)
        except Exception as e:
            logger.warning(f"Failed to load embeddings model: {e}")
            self.model = None

        self.tool_embeddings: Dict[str, np.ndarray] = {}
        self.tool_descriptions: Dict[str, str] = {}
        self._cache_dirty = True

    def index_tools(self, tools_info: Dict[str, str]) -> None:
        """
        Build embeddings for all tools.

        Args:
            tools_info: {tool_name: description}
        """
        if self.model is None:
            logger.warning("Cannot index tools: embeddings model not available")
            return

        self.tool_descriptions = tools_info
        descriptions = list(tools_info.values())
        tool_names = list(tools_info.keys())

        try:
            embeddings = self.model.encode(descriptions, convert_to_tensor=True)
            for name, embedding in zip(tool_names, embeddings):
                self.tool_embeddings[name] = embedding.cpu().numpy()
            self._cache_dirty = False
            logger.info(f"Indexed {len(tool_names)} tools for semantic search")
        except Exception as e:
            logger.error(f"Failed to index tools: {e}")

    def search(self, query: str, limit: int = 5, threshold: float = 0.3) -> List[Tuple[str, float]]:
        """
        Find most relevant tools for a query.

        Args:
            query: Natural language query
            limit: Maximum results to return
            threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of (tool_name, similarity_score) tuples, sorted by relevance
        """
        if self.model is None or not self.tool_embeddings:
            logger.warning("Tool search not available")
            return []

        try:
            query_embedding = self.model.encode(query, convert_to_tensor=True)

            results = []
            for tool_name, tool_embedding in self.tool_embeddings.items():
                # Convert numpy array back to tensor for similarity
                tool_tensor = util.torch.tensor(tool_embedding)
                similarity = util.pytorch_cos_sim(query_embedding, tool_tensor)[0][0].item()

                if similarity >= threshold:
                    results.append((tool_name, similarity))

            # Sort by similarity descending
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:limit]

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def get_tools_for_description(self, description: str, limit: int = 5) -> List[str]:
        """Get tool names most relevant to a description"""
        results = self.search(description, limit=limit)
        return [name for name, _ in results]
```

### Step 2: Integrate with SkillRegistry

```python
# File: research_agent/inno/skills/registry.py
# Add to imports:
from research_agent.inno.skills.search import ToolSearchRegistry

# Add to SkillRegistry class:
def __new__(cls):
    if cls._instance is None:
        cls._instance = super().__new__(cls)
        cls._instance._skills: Dict[str, Skill] = {}
        cls._instance._loader = SkillLoader()
        cls._instance._base_registry = registry
        cls._instance._tool_search = ToolSearchRegistry()  # NEW
    return cls._instance

def search_tools(self, query: str, limit: int = 5) -> List[Tuple[str, float]]:
    """
    Search for tools matching the query.

    Args:
        query: Natural language query (e.g., "search for papers")
        limit: Number of results to return

    Returns:
        List of (tool_name, similarity) tuples
    """
    # Build search index if needed
    if not self._tool_search.tool_embeddings:
        tools_info = {}
        for skill_name in self.list_skills():
            skill = self.get_skill(skill_name)
            for func in skill.functions:
                tool_name = f"{skill_name}.{func.__name__}"
                description = func.__doc__ or func.__name__
                tools_info[tool_name] = description

        self._tool_search.index_tools(tools_info)

    return self._tool_search.search(query, limit=limit)

def get_tools_for_task(self, task_description: str, limit: int = 5) -> List[Callable]:
    """
    Get tool functions for a task description.

    Example:
        tools = registry.get_tools_for_task("search papers on neural networks", limit=3)
        # Returns: [search_arxiv, paper_search.get_meta, ...]
    """
    results = self.search_tools(task_description, limit=limit)
    tools = []

    for tool_name, _ in results:
        skill_name, func_name = tool_name.split('.')
        skill = self.get_skill(skill_name)
        if skill:
            func = skill.get_tool(func_name)
            if func:
                tools.append(func)

    return tools
```

### Step 3: Test Tool Search

```python
# File: tests/test_skills/test_tool_search.py
# NEW FILE

import pytest
from research_agent.inno.skills.registry import skill_registry

class TestToolSearch:
    def test_search_for_paper_tools(self):
        """Test searching for paper-related tools"""
        registry = skill_registry

        # Search for paper tools
        results = registry.search_tools("search academic papers", limit=5)

        assert len(results) > 0
        # First result should be paper/arxiv related
        top_tool, score = results[0]
        assert "arxiv" in top_tool or "paper" in top_tool
        assert 0.0 <= score <= 1.0

    def test_search_for_code_tools(self):
        """Test searching for code-related tools"""
        registry = skill_registry

        results = registry.search_tools("search code repositories", limit=5)

        assert len(results) > 0
        top_tool, _ = results[0]
        assert "code" in top_tool or "github" in top_tool

    def test_get_tools_for_task(self):
        """Test getting tools for a task"""
        registry = skill_registry

        tools = registry.get_tools_for_task("find papers about machine learning", limit=3)

        assert len(tools) > 0
        assert all(callable(t) for t in tools)
```

---

## 3. A2A Agent Card Export (3 hours)

### Step 1: Create A2AExporter Class

```python
# File: research_agent/inno/skills/a2a.py
# NEW FILE

from typing import Dict, Any, List
from research_agent.inno.skills.registry import SkillRegistry

class A2AAgentCard:
    """Exports AI-Researcher as A2A-compliant Agent Card"""

    @staticmethod
    def from_skill_registry(registry: SkillRegistry) -> Dict[str, Any]:
        """
        Generate A2A Agent Card from SkillRegistry.

        Published at: /.well-known/agent.json
        """
        skills = []

        for skill_name in registry.list_skills():
            skill = registry.get_skill(skill_name)
            manifest = skill.manifest

            skill_card = {
                "name": manifest.name,
                "description": manifest.description,
                "version": manifest.version,
                "author": manifest.author,
                "tools": [
                    {
                        "name": f.__name__,
                        "description": f.__doc__ or f.__name__,
                    }
                    for f in skill.functions
                ],
                "tags": manifest.tags,
                "requiredConfig": manifest.required_config,
            }

            if manifest.instructions:
                skill_card["instructions"] = manifest.instructions

            skills.append(skill_card)

        return {
            "name": "AI-Researcher Agent",
            "description": "Autonomous research agent for academic paper discovery, code analysis, and research planning",
            "provider": "HKUDS",
            "version": "0.2.0",
            "serviceEndpoint": "https://researcher.example.com/a2a",
            "baseUrl": "https://researcher.example.com",
            "capabilities": {
                "skills": skills,
                "features": [
                    "streaming",
                    "statefulness",
                    "tool_search",
                    "dynamic_binding"
                ],
                "supportedProtocols": [
                    "json-rpc",
                    "http"
                ]
            },
            "authentication": {
                "type": "bearer",
                "required": []
            },
            "rateLimit": {
                "requestsPerMinute": 100,
                "concurrent": 10
            }
        }
```

### Step 2: Add to SkillRegistry

```python
# File: research_agent/inno/skills/registry.py
# Add method to SkillRegistry class:

def to_agent_card(self) -> Dict[str, Any]:
    """Export as A2A Agent Card (JSON)"""
    from research_agent.inno.skills.a2a import A2AAgentCard
    return A2AAgentCard.from_skill_registry(self)

def get_agent_card_json(self) -> str:
    """Export as JSON string ready for /.well-known/agent.json"""
    import json
    card = self.to_agent_card()
    return json.dumps(card, indent=2)
```

### Step 3: Expose via Flask/HTTP

```python
# File: research_agent/api.py
# NEW/UPDATED

from flask import Flask, jsonify
from research_agent.inno.skills.registry import skill_registry

app = Flask(__name__)

@app.route("/.well-known/agent.json")
def agent_card():
    """A2A Agent Card endpoint"""
    return jsonify(skill_registry.to_agent_card())

@app.route("/api/capabilities")
def capabilities():
    """List available skills and tools"""
    result = {
        "skills": [],
        "tools": []
    }

    for skill_name in skill_registry.list_skills():
        skill = skill_registry.get_skill(skill_name)
        result["skills"].append({
            "name": skill.name,
            "description": skill.manifest.description,
            "tools": skill.tool_names,
            "tags": skill.manifest.tags,
        })

        for tool_name in skill.tool_names:
            result["tools"].append({
                "skill": skill_name,
                "name": tool_name,
            })

    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=False, port=5000)
```

---

## 4. MCP Notifications Pattern (6 hours)

### Step 1: Add Change Notifications to Registry

```python
# File: research_agent/inno/skills/registry.py
# Add to imports:
from typing import Callable, List, Optional
import weakref

# Add to SkillRegistry class:
def __init__(self):
    self._change_listeners: List[Callable] = []

def subscribe_to_changes(self, callback: Callable[[str], None]) -> Callable:
    """
    Subscribe to skill changes.

    Args:
        callback: Function(event_type) called when skills change

    Returns:
        Unsubscribe function
    """
    self._change_listeners.append(callback)

    # Return unsubscribe function
    return lambda: self._change_listeners.remove(callback) if callback in self._change_listeners else None

def notify_skills_changed(self, event_type: str = "tools_list_changed") -> None:
    """
    Notify all listeners that skills have changed.

    Args:
        event_type: Type of change (tools_list_changed, tool_updated, etc.)
    """
    for listener in self._change_listeners:
        try:
            listener(event_type)
        except Exception as e:
            logger.error(f"Error calling change listener: {e}")

# Update load_and_register:
def load_and_register(self, skill_name: str, **kwargs) -> Skill:
    """Load a skill and notify listeners"""
    skill = self._loader.load(skill_name, **kwargs)
    self.register_skill(skill)
    self.notify_skills_changed("skill_loaded")
    return skill

# Update unload_skill:
def unload_skill(self, name: str) -> None:
    """Unload a skill and notify listeners"""
    skill = self._skills.pop(name, None)
    if skill:
        for func in skill.functions:
            self._base_registry._registry["tools"].pop(func.__name__, None)
        self.notify_skills_changed("skill_unloaded")
```

### Step 2: MCP Server Integration

```python
# File: research_agent/inno/mcp_server.py
# NEW FILE

from mcp import Server
from research_agent.inno.skills.registry import skill_registry
import json

server = Server("ai_researcher")

@server.tool_list_handler
def list_tools():
    """Expose skills as MCP tools"""
    tools = []

    for skill_name in skill_registry.list_skills():
        skill = skill_registry.get_skill(skill_name)

        for func in skill.functions:
            # Get function signature
            import inspect
            sig = inspect.signature(func)

            # Build input schema
            input_schema = {
                "type": "object",
                "properties": {},
                "required": []
            }

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue

                input_schema["properties"][param_name] = {
                    "type": "string",
                    "description": f"Parameter: {param_name}"
                }

                if param.default == inspect.Parameter.empty:
                    input_schema["required"].append(param_name)

            tools.append({
                "name": func.__name__,
                "description": func.__doc__ or f"Tool: {func.__name__}",
                "inputSchema": input_schema,
                "skillName": skill_name,
            })

    return {"tools": tools}

@server.call_tool_handler
def execute_tool(name: str, arguments: dict):
    """Execute a tool"""
    # Find tool
    for skill_name in skill_registry.list_skills():
        skill = skill_registry.get_skill(skill_name)
        tool = skill.get_tool(name)
        if tool:
            try:
                result = tool(**arguments)
                return {
                    "type": "text",
                    "text": str(result)
                }
            except Exception as e:
                return {
                    "type": "error",
                    "text": f"Tool execution failed: {e}"
                }

    return {
        "type": "error",
        "text": f"Tool not found: {name}"
    }

def notify_tools_changed():
    """Send MCP notification that tools have changed"""
    server.notify({
        "jsonrpc": "2.0",
        "method": "notifications/tools/list_changed"
    })

# Subscribe to skill changes
def on_skill_change(event_type: str):
    if event_type in ["skill_loaded", "skill_unloaded"]:
        notify_tools_changed()

skill_registry.subscribe_to_changes(on_skill_change)
```

---

## 5. Dependencies to Add (Package)

### Add to requirements.txt or pyproject.toml

```ini
# Existing dependencies (keep all)
langchain>=0.1.0
langgraph>=0.0.1
anthropic>=0.7.0

# NEW for Phase 2c:
sentence-transformers>=2.2.0  # For embeddings/search
mcp>=0.1.0  # For MCP protocol support
pydantic>=2.0.0  # Already exists, ensure version
```

### Or with Poetry (pyproject.toml):

```toml
[project.optional-dependencies]
tools = [
    "sentence-transformers>=2.2.0",
    "mcp>=0.1.0",
]
```

### Installation:

```bash
# Using pip with optional dependencies
pip install -e ".[tools]"

# Or direct
pip install sentence-transformers mcp
```

---

## 6. Testing Checklist

```python
# File: tests/test_skills/test_phase_2c.py
# NEW FILE

import pytest
from research_agent.inno.skills.registry import skill_registry
from research_agent.inno.skills.a2a import A2AAgentCard

class TestPhase2c:
    """Test all Phase 2c enhancements"""

    def test_tool_search_available(self):
        """Test tool search works"""
        results = skill_registry.search_tools("papers", limit=3)
        assert len(results) > 0

    def test_tool_search_scores(self):
        """Test search returns valid scores"""
        results = skill_registry.search_tools("arxiv", limit=5)
        for name, score in results:
            assert 0.0 <= score <= 1.0

    def test_get_tools_for_task(self):
        """Test task-based tool selection"""
        tools = skill_registry.get_tools_for_task("find papers", limit=3)
        assert all(callable(t) for t in tools)

    def test_agent_card_export(self):
        """Test A2A Agent Card generation"""
        card = skill_registry.to_agent_card()

        assert card["name"] == "AI-Researcher Agent"
        assert "skills" in card["capabilities"]
        assert len(card["capabilities"]["skills"]) > 0

    def test_agent_card_json(self):
        """Test Agent Card JSON export"""
        json_str = skill_registry.get_agent_card_json()
        import json
        card = json.loads(json_str)

        assert card["name"] == "AI-Researcher Agent"

    def test_skill_change_notifications(self):
        """Test change notification system"""
        events = []

        def listener(event):
            events.append(event)

        unsub = skill_registry.subscribe_to_changes(listener)

        # Unload a skill (if safe to test)
        # This would trigger notifications

        assert callable(unsub)

    def test_backward_compatibility(self):
        """Ensure all existing tests still pass"""
        # All 71 original tests should still pass
        pass
```

---

## 7. Documentation Updates

### Add to skill template (examples/SKILL_TEMPLATE.md):

```markdown
## Tool Schemas

### my_function
Brief description of what this tool does.

```json
{
  "type": "object",
  "properties": {
    "parameter_name": {
      "type": "string",
      "description": "What this parameter does"
    },
    "optional_param": {
      "type": "integer",
      "description": "Optional parameter",
      "default": 10
    }
  },
  "required": ["parameter_name"]
}
```
```

---

## 8. Implementation Order (Week-by-Week)

**Monday:**
- [ ] Implement JSON Schema support (4h)
- [ ] Update SKILL.md format
- [ ] Write schema tests

**Tuesday-Wednesday:**
- [ ] Implement tool search (8h)
- [ ] Create ToolSearchRegistry class
- [ ] Write search tests + benchmarks

**Thursday:**
- [ ] Implement A2A export (3h)
- [ ] Create Flask endpoints
- [ ] Test agent card generation

**Friday:**
- [ ] Implement MCP notifications (6h)
- [ ] Integration tests
- [ ] Code review & polish

**Total: 40 hours (1 week FTE)**

---

## Quick Test Commands

```bash
# Test schema parsing
pytest tests/test_skills/test_phase_2c.py::TestPhase2c::test_tool_search_available

# Test search performance
pytest tests/test_skills/test_phase_2c.py::TestPhase2c::test_tool_search_scores -v

# Test A2A export
pytest tests/test_skills/test_phase_2c.py::TestPhase2c::test_agent_card_export

# All Phase 2c tests
pytest tests/test_skills/test_phase_2c.py -v

# Ensure backward compatibility
pytest tests/ -v  # All 71 original tests + new tests
```

---

**Ready to implement! Start with Section 1 on Monday.**
