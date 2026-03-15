# arxiv_search

## Name
arxiv_search

## Version
0.1.0

## Description
Search and download academic papers from arXiv. Provides tools for
querying the arXiv API by keyword or title, downloading LaTeX source
files, and extracting .tex content from tar.gz archives.

## Author
HKUDS

## Tools
- search_arxiv
- download_arxiv_source
- download_arxiv_source_by_title
- extract_tex_content

## Dependencies
- paper_search (optional)

## Required Config
- OPENAI_API_KEY

## Tags
- research
- academic
- arxiv
- papers

## Parameters
```json
{
  "search_arxiv": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Search query for arXiv papers"},
      "max_results": {"type": "integer", "description": "Maximum number of results to return"}
    },
    "required": ["query"]
  },
  "download_arxiv_source": {
    "type": "object",
    "properties": {
      "arxiv_id": {"type": "string", "description": "arXiv paper ID (e.g. 2301.00001)"},
      "download_dir": {"type": "string", "description": "Directory to save the source"}
    },
    "required": ["arxiv_id"]
  },
  "download_arxiv_source_by_title": {
    "type": "object",
    "properties": {
      "title": {"type": "string", "description": "Paper title to search and download"},
      "download_dir": {"type": "string", "description": "Directory to save the source"}
    },
    "required": ["title"]
  },
  "extract_tex_content": {
    "type": "object",
    "properties": {
      "tar_gz_path": {"type": "string", "description": "Path to the tar.gz archive"}
    },
    "required": ["tar_gz_path"]
  }
}
```

## Instructions
You have access to arXiv search tools. Use `search_arxiv` to find papers
by keyword (returns title, authors, abstract, PDF URL). Use
`download_arxiv_source_by_title` to download paper LaTeX source and
extract the full text. Results are saved to the local workspace.
