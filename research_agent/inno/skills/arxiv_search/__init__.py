"""arxiv_search skill: Search and download papers from arXiv."""

from typing import Callable, List

from research_agent.inno.tools.arxiv_source import (
    download_arxiv_source,
    download_arxiv_source_by_title,
    extract_tex_content,
    search_arxiv,
)


def get_tools(**kwargs) -> List[Callable]:
    return [
        search_arxiv,
        download_arxiv_source,
        download_arxiv_source_by_title,
        extract_tex_content,
    ]
