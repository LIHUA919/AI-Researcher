# code_search

## Name
code_search

## Version
0.1.0

## Description
Search GitHub for public repositories and code snippets relevant to a
research topic. Supports date filtering and result limiting.

## Author
HKUDS

## Tools
- search_github_repos
- search_github_code

## Required Config
- GITHUB_AI_TOKEN

## Tags
- research
- code
- github
- search

## Parameters
```json
{
  "search_github_repos": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Search query for GitHub repositories"},
      "max_results": {"type": "integer", "description": "Maximum number of results"}
    },
    "required": ["query"]
  },
  "search_github_code": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Code search query"},
      "repo": {"type": "string", "description": "Repository name (owner/repo)"}
    },
    "required": ["query"]
  }
}
```

## Instructions
Use `search_github_repos` to find relevant GitHub repositories for a
research topic (supports date filtering via context_variables). Use
`search_github_code` to search for specific code patterns within a
repository.
