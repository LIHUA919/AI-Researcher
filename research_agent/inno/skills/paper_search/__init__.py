"""paper_search skill: Retrieve arXiv paper metadata."""

from typing import Callable, List

from research_agent.inno.tools.inno_tools.paper_search import get_arxiv_paper_meta


def get_tools(**kwargs) -> List[Callable]:
    return [get_arxiv_paper_meta]
