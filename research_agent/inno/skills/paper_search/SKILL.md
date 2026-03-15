# paper_search

## Name
paper_search

## Version
0.1.0

## Description
Retrieve metadata for academic papers from arXiv, including title,
authors, abstract, categories, DOI, and publication date.

## Author
HKUDS (tools), Lihua (skill manifest & parameters)

## Tools
- get_arxiv_paper_meta

## Tags
- research
- academic
- metadata

## Parameters
```json
{
  "get_arxiv_paper_meta": {
    "type": "object",
    "properties": {
      "arxiv_url": {"type": "string", "description": "arXiv URL or paper ID"}
    },
    "required": ["arxiv_url"]
  }
}
```

## Instructions
Use `get_arxiv_paper_meta` with an arXiv URL or ID to retrieve paper
metadata including title, authors, abstract, publication date, and
categories.
