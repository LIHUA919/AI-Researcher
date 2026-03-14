"""Shared utilities for run_infer_plan and run_infer_idea.

This module consolidates the duplicated helper functions, argument parsing,
and data models that were previously copied between the two inference scripts.
"""

import argparse
import json
import logging
from typing import Dict, List

from pydantic import BaseModel, Field
from tqdm import tqdm

from research_agent.inno.tools.inno_tools.code_search import search_github_repos
from research_agent.inno.tools.inno_tools.paper_search import get_arxiv_paper_meta

logger = logging.getLogger(__name__)


def warp_source_papers(source_papers: List[dict]) -> str:
    return "\n".join(
        [
            f"Title: {sp['reference']}; You can use this paper in the following way: {sp['usage']}"
            for sp in source_papers
        ]
    )


def extract_json_from_output(output_text: str) -> dict:
    """Extract the first complete JSON object from *output_text*."""

    def find_json_boundaries(text: str):
        stack: list = []
        start = -1
        for i, char in enumerate(text):
            if char == "{":
                if not stack:
                    start = i
                stack.append(char)
            elif char == "}":
                stack.pop()
                if not stack and start != -1:
                    return text[start : i + 1]
        return None

    json_str = find_json_boundaries(output_text)
    if json_str:
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning("JSON parse error: %s", e)
            return {}
    return {}


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance_path", type=str, default="benchmark/gnn.json")
    parser.add_argument("--container_name", type=str, default="paper_eval")
    parser.add_argument("--task_level", type=str, default="task1")
    parser.add_argument("--model", type=str, default="gpt-4o-2024-08-06")
    parser.add_argument("--workplace_name", type=str, default="workplace")
    parser.add_argument("--cache_path", type=str, default="cache")
    parser.add_argument("--port", type=int, default=12345)
    parser.add_argument("--max_iter_times", type=int, default=0)
    parser.add_argument("--category", type=str, default="recommendation")
    args = parser.parse_args()
    return args


class EvalMetadata(BaseModel):
    source_papers: List[dict] = Field(description="the list of source papers")
    task_instructions: str = Field(description="the task instructions")
    date: str = Field(description="the date", pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_limit: str = Field(description="the date limit", pattern=r"^\d{4}-\d{2}-\d{2}$")


def load_instance(instance_path: str, task_level: str) -> Dict:
    with open(instance_path, "r", encoding="utf-8") as f:
        eval_instance = json.load(f)
    source_papers = eval_instance["source_papers"]
    task_instructions = eval_instance[task_level]
    arxiv_url = eval_instance["url"]
    meta = get_arxiv_paper_meta(arxiv_url)
    if meta is None:
        date = "2024-01-01"
    else:
        date = meta["published"].strftime("%Y-%m-%d")

    return EvalMetadata(
        source_papers=source_papers,
        task_instructions=task_instructions,
        date=date,
        date_limit=date,
    ).model_dump()


def github_search(metadata: Dict) -> str:
    github_result = ""
    for source_paper in tqdm(metadata["source_papers"]):
        github_result += search_github_repos(metadata, source_paper["reference"], 10)
        github_result += "*" * 30 + "\n"
    return github_result
