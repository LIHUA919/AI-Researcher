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

## Instructions
You have access to arXiv search tools. Use `search_arxiv` to find papers
by keyword (returns title, authors, abstract, PDF URL). Use
`download_arxiv_source_by_title` to download paper LaTeX source and
extract the full text. Results are saved to the local workspace.
