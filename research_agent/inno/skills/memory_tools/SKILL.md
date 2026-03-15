# memory_tools

## Name
memory_tools

## Version
0.1.0

## Description
Agent-callable tools for memory operations: recall past knowledge,
store new facts, search conversation episodes, and inspect agent state.

## Author
Lihua

## Tools
- recall_memory
- store_memory
- search_episodes
- get_agent_state

## Parameters
```json
{
  "recall_memory": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Natural language query to search memory"},
      "top_k": {"type": "integer", "description": "Number of results to return"}
    },
    "required": ["query"]
  },
  "store_memory": {
    "type": "object",
    "properties": {
      "key": {"type": "string", "description": "Key to store the value under"},
      "value": {"type": "string", "description": "Value to store"},
      "shared": {"type": "boolean", "description": "If true, store in shared namespace"}
    },
    "required": ["key", "value"]
  },
  "search_episodes": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Search query for past episodes"},
      "agent_name": {"type": "string", "description": "Filter by agent name"}
    },
    "required": ["query"]
  },
  "get_agent_state": {
    "type": "object",
    "properties": {
      "agent_name": {"type": "string", "description": "Agent whose state to retrieve"}
    },
    "required": []
  }
}
```

## Tags
- memory
- state
- episodes
- knowledge

## Instructions
Use memory tools to persist and recall information across turns:
- `recall_memory(query)`: Search past episodes and facts for relevant info.
- `store_memory(key, value)`: Store a key-value pair in session state.
- `search_episodes(query)`: Search past conversation episodes.
- `get_agent_state()`: Get the current state snapshot for an agent.
