"""code_search skill: GitHub repository and code search."""

from typing import Callable, List

from research_agent.inno.tools.inno_tools.code_search import (
    search_github_code,
    search_github_repos,
)


def get_tools(**kwargs) -> List[Callable]:
    return [search_github_repos, search_github_code]
