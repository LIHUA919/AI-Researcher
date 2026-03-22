"""Shared utilities for run_infer_plan and run_infer_idea.

This module consolidates the duplicated helper functions, argument parsing,
and data models that were previously copied between the two inference scripts.
"""

import argparse
import json
import logging
import os
import re
from typing import Any, Dict, List

from pydantic import BaseModel, Field
from tqdm import tqdm

from research_agent.inno.tools.inno_tools.code_search import search_github_repos
from research_agent.inno.tools.inno_tools.paper_search import get_arxiv_paper_meta

logger = logging.getLogger(__name__)


def _read_json_file(path: str) -> Dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def update_stage_state(
    cache_path: str,
    stage_name: str,
    status: str,
    artifacts: Dict[str, str] | None = None,
    metadata: Dict | None = None,
) -> str:
    stage_state_path = os.path.join(cache_path, "stage_state.json")
    stage_state = _read_json_file(stage_state_path)
    stage_state[stage_name] = {
        "status": status,
        "artifacts": artifacts or {},
        "metadata": metadata or {},
    }
    with open(stage_state_path, "w", encoding="utf-8") as f:
        json.dump(stage_state, f, ensure_ascii=False, indent=4)
    return stage_state_path


def load_stage_state(cache_path: str | None) -> Dict:
    if not cache_path:
        return {}
    return _read_json_file(os.path.join(cache_path, "stage_state.json"))


def persist_stage_result(
    cache_path: str,
    stage_name: str,
    file_name: str,
    payload: Dict[str, Any],
) -> str:
    stage_dir = os.path.join(cache_path, f"{stage_name}_stage")
    os.makedirs(stage_dir, exist_ok=True)
    output_path = os.path.join(stage_dir, file_name)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)
    return output_path


def load_cached_stage_result(
    cache_path: str | None,
    stage_name: str,
    file_name: str,
) -> Dict:
    if not cache_path:
        return {}
    return _read_json_file(os.path.join(cache_path, f"{stage_name}_stage", file_name))


def build_project_manifest(local_root: str, workplace_name: str) -> Dict[str, Any]:
    project_root = os.path.join(local_root, workplace_name, "project")
    files: List[str] = []
    directories: List[str] = []
    if os.path.exists(project_root):
        for current_root, dirnames, filenames in os.walk(project_root):
            rel_root = os.path.relpath(current_root, project_root)
            if rel_root == ".":
                rel_root = ""
            for dirname in sorted(dirnames):
                directories.append(os.path.join(rel_root, dirname).strip("/"))
            for filename in sorted(filenames):
                files.append(os.path.join(rel_root, filename).strip("/"))

    return {
        "project_root": project_root,
        "exists": os.path.exists(project_root),
        "directories": directories,
        "files": files,
        "key_paths": {
            "main_script": os.path.join(project_root, "run_training_testing.py"),
            "model_dir": os.path.join(project_root, "model"),
            "training_dir": os.path.join(project_root, "training"),
            "testing_dir": os.path.join(project_root, "testing"),
            "data_dir": os.path.join(project_root, "data"),
        },
    }


def _persist_plan_artifact_bundle(artifact_dir: str, artifacts: Dict[str, Dict]) -> Dict[str, str]:
    os.makedirs(artifact_dir, exist_ok=True)
    index_payload: Dict[str, str] = {}
    for artifact_name, artifact_payload in artifacts.items():
        artifact_path = os.path.join(artifact_dir, f"{artifact_name}.json")
        with open(artifact_path, "w", encoding="utf-8") as f:
            json.dump(artifact_payload, f, ensure_ascii=False, indent=4)
        index_payload[artifact_name] = artifact_path

    index_path = os.path.join(artifact_dir, "plan_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_payload, f, ensure_ascii=False, indent=4)
    return index_payload


def _extract_first_dataset_location(dataset_description: str) -> str:
    match = re.search(r"(/workplace/[^\s`]+)", dataset_description or "")
    if match:
        return match.group(1)
    return "/workplace/dataset_candidate/cifar-10-python.tar.gz"


def ensure_plan_artifacts(
    context_variables: Dict,
    dataset_description: str,
    idea_text: str,
    workplace_name: str,
) -> Dict:
    existing_dataset_plan = context_variables.get("dataset_plan")
    existing_training_plan = context_variables.get("training_plan")
    existing_testing_plan = context_variables.get("testing_plan")
    if existing_dataset_plan and existing_training_plan and existing_testing_plan:
        return context_variables

    artifact_dir = context_variables.get("plan_artifact_dir")
    if not artifact_dir:
        return context_variables

    dataset_location = _extract_first_dataset_location(dataset_description)
    reference_paths = (
        (context_variables.get("prepare_result") or {}).get("reference_paths", [])
        or [f"/{workplace_name}"]
    )

    dataset_plan = existing_dataset_plan or {
        "dataset_description": "Use CIFAR-10 as the lightweight benchmark dataset for the VQ model experiment.",
        "dataset_location": dataset_location,
        "task_definition": (
            idea_text
            or "Train and evaluate a VQ-based autoencoding model that reduces representation collapse while preserving reconstruction quality."
        ),
        "data_processing": {
            "read_data": "Load CIFAR-10 from the official tarball or via torchvision.datasets.CIFAR10 with train/test splits.",
            "data_preprocessing": "Convert images to tensors, normalize to the range expected by the selected VQ implementation, and keep image resolution consistent across training and evaluation.",
            "data_dataloader": "Build shuffled training and deterministic test dataloaders with small batch sizes that fit GPU memory for the 2-epoch run.",
        },
    }
    training_plan = existing_training_plan or {
        "training_pipeline": (
            "Initialize encoder, decoder, codebook, and the new learnable linear transformation W; "
            "freeze the base codebook during the initial phase and train the model for exactly 2 epochs on CIFAR-10."
        ),
        "loss_function": (
            "Combine reconstruction loss with commitment loss and codebook-related quantization loss; "
            "track codebook utilization so the new transformation layer can be evaluated against representation collapse."
        ),
        "optimizer": "Use Adam with a learning rate around 1e-4 and separate parameter groups if the linear transformation W needs distinct optimization behavior.",
        "training_configurations": (
            f"Use one practical CIFAR-10 configuration for a short 2-epoch GPU run, checkpoint under /{workplace_name}/project, "
            "and reuse reference implementations from: " + ", ".join(reference_paths)
        ),
        "monitor_and_logging": "Log training loss, reconstruction quality, commitment/codebook terms, and codebook utilization statistics each epoch.",
    }
    testing_plan = existing_testing_plan or {
        "test_metric": "Evaluate reconstruction loss, codebook utilization, and FID-related outputs when applicable using the provided CIFAR-10 reference statistics.",
        "test_data": "Use the CIFAR-10 test split and the provided cifar10-32x32.npz reference statistics for evaluation.",
        "test_function": (
            "Run an end-to-end evaluation after the 2 training epochs, save metrics to disk, and verify the new transformation layer does not degrade reconstruction while improving codebook usage."
        ),
    }

    context_variables["dataset_plan"] = dataset_plan
    context_variables["training_plan"] = training_plan
    context_variables["testing_plan"] = testing_plan
    artifact_index = _persist_plan_artifact_bundle(
        artifact_dir,
        {
            "dataset_plan": dataset_plan,
            "training_plan": training_plan,
            "testing_plan": testing_plan,
        },
    )
    context_variables["plan_artifacts"] = artifact_index
    logger.warning(
        "Coding Plan Agent did not emit structured planning artifacts; synthesized fallback plan artifacts were written instead.",
    )
    return context_variables


def persist_survey_result(
    cache_path: str,
    task_id: str,
    query: str,
    survey_report: str,
) -> str:
    survey_stage_dir = os.path.join(cache_path, "survey_stage")
    os.makedirs(survey_stage_dir, exist_ok=True)
    survey_result_path = os.path.join(survey_stage_dir, "survey_result.json")
    with open(survey_result_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "task_id": task_id,
                "query": query,
                "survey_report": survey_report,
            },
            f,
            ensure_ascii=False,
            indent=4,
        )
    return survey_result_path


def load_cached_survey_result(cache_path: str | None) -> Dict:
    if not cache_path:
        return {}
    return _read_json_file(os.path.join(cache_path, "survey_stage", "survey_result.json"))


def load_cached_plan_result(cache_path: str | None) -> Dict:
    if not cache_path:
        return {}
    plan_report = _read_json_file(os.path.join(cache_path, "plan_stages", "plan_report.json"))
    if not plan_report:
        return {}

    plan_index = _read_json_file(os.path.join(cache_path, "plan_stages", "plan_index.json"))
    dataset_plan = _read_json_file(plan_index.get("dataset_plan", "")) if plan_index else {}
    training_plan = _read_json_file(plan_index.get("training_plan", "")) if plan_index else {}
    testing_plan = _read_json_file(plan_index.get("testing_plan", "")) if plan_index else {}

    if dataset_plan:
        plan_report["dataset_plan"] = dataset_plan
    if training_plan:
        plan_report["training_plan"] = training_plan
    if testing_plan:
        plan_report["testing_plan"] = testing_plan
    if plan_index:
        plan_report["plan_artifacts"] = plan_index
    return plan_report


def _is_valid_prepare_result(prepare_dict: Dict) -> bool:
    return all(
        key in prepare_dict and prepare_dict.get(key)
        for key in ("reference_codebases", "reference_paths", "reference_papers")
    )


def _persist_prepare_result(cache_path: str, prepare_dict: Dict) -> str:
    prepare_stage_dir = os.path.join(cache_path, "prepare_stage")
    os.makedirs(prepare_stage_dir, exist_ok=True)
    prepare_result_path = os.path.join(prepare_stage_dir, "prepare_result.json")
    with open(prepare_result_path, "w", encoding="utf-8") as f:
        json.dump(prepare_dict, f, ensure_ascii=False, indent=4)
    return prepare_result_path


def _build_vq_prepare_fallback(local_root: str, workplace_name: str) -> Dict:
    workplace_root = os.path.join(local_root, workplace_name)
    candidates = [
        (
            "CompVis/taming-transformers",
            os.path.join(workplace_root, "CompVis", "taming-transformers"),
            "Taming transformers for high-resolution image synthesis",
        ),
        (
            "dome272/VQGAN-pytorch",
            os.path.join(workplace_root, "VQGAN-pytorch"),
            "Taming transformers for high-resolution image synthesis",
        ),
        (
            "Shubhamai/pytorch-vqgan",
            os.path.join(workplace_root, "pytorch-vqgan"),
            "Taming transformers for high-resolution image synthesis",
        ),
        (
            "airalcorn2/vqvae-pytorch",
            os.path.join(workplace_root, "vqvae-pytorch"),
            "Neural discrete representation learning",
        ),
        (
            "Nikolai10/FSQ",
            os.path.join(workplace_root, "FSQ"),
            "Finite scalar quantization: VQ-VAE made simple.",
        ),
        (
            "1Konny/VQ-VAE",
            os.path.join(workplace_root, "1Konny", "VQ-VAE"),
            "Neural discrete representation learning",
        ),
    ]

    selected = []
    for codebase, local_path, paper in candidates:
        if os.path.exists(local_path):
            selected.append((codebase, f"/{os.path.relpath(local_path, local_root)}", paper))
        if len(selected) == 5:
            break

    return {
        "reference_codebases": [item[0] for item in selected],
        "reference_paths": [item[1] for item in selected],
        "reference_papers": [item[2] for item in selected],
    }


def resolve_prepare_result(
    prepare_res: str,
    context_variables: Dict,
    local_root: str,
    workplace_name: str,
    category: str,
    cache_path: str | None = None,
) -> Dict:
    prepare_dict = context_variables.get("prepare_result") or extract_json_from_output(prepare_res)
    if _is_valid_prepare_result(prepare_dict):
        if cache_path:
            _persist_prepare_result(cache_path, prepare_dict)
        return prepare_dict

    if cache_path:
        cached_prepare_path = os.path.join(cache_path, "prepare_stage", "prepare_result.json")
        if os.path.exists(cached_prepare_path):
            with open(cached_prepare_path, "r", encoding="utf-8") as f:
                cached_prepare = json.load(f)
            if _is_valid_prepare_result(cached_prepare):
                return cached_prepare

    if category == "vq":
        fallback_prepare = _build_vq_prepare_fallback(local_root, workplace_name)
        if fallback_prepare["reference_codebases"]:
            if cache_path:
                prepare_stage_dir = os.path.join(cache_path, "prepare_stage")
                os.makedirs(prepare_stage_dir, exist_ok=True)
                _persist_prepare_result(cache_path, fallback_prepare)
                fallback_path = os.path.join(prepare_stage_dir, "prepare_result_fallback.json")
                with open(fallback_path, "w", encoding="utf-8") as f:
                    json.dump(fallback_prepare, f, ensure_ascii=False, indent=4)
            return fallback_prepare

    return {}


def load_cached_prepare_result(cache_path: str | None) -> Dict:
    if not cache_path:
        return {}
    cached_prepare_path = os.path.join(cache_path, "prepare_stage", "prepare_result.json")
    if not os.path.exists(cached_prepare_path):
        return {}
    with open(cached_prepare_path, "r", encoding="utf-8") as f:
        cached_prepare = json.load(f)
    return cached_prepare if _is_valid_prepare_result(cached_prepare) else {}


def build_survey_result(
    survey_res: str,
    context_variables: Dict,
) -> str:
    notes = context_variables.get("notes") or []
    normalized_notes = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        if not note.get("definition"):
            continue
        normalized_notes.append(
            {
                "definition": note.get("definition", ""),
                "math_formula": note.get("math_formula", ""),
                "code_implementation": note.get("code_implementation", ""),
                "reference_papers": note.get("reference_papers", []),
                "reference_codebases": note.get("reference_codebases", []),
            }
        )

    if not normalized_notes:
        return survey_res

    merged_notes = "\n\n".join(
        [
            "\n".join(
                [
                    f"## Academic Definition\n{note['definition']}",
                    f"## Math Formula\n{note['math_formula']}",
                    f"## Reference Papers\n{note['reference_papers']}",
                    f"## Code Implementation\n{note['code_implementation']}",
                    f"## Reference Codebases\n{note['reference_codebases']}",
                ]
            )
            for note in normalized_notes
        ]
    )
    return (
        "I have merged the notes for the innovation.\n"
        "The notes are as follows:\n"
        f"{merged_notes}"
    )


def build_plan_result(
    plan_res: str,
    context_variables: Dict,
) -> str:
    dataset_plan = context_variables.get("dataset_plan")
    model_plan = context_variables.get("model_plan")
    model_survey = context_variables.get("model_survey")
    training_plan = context_variables.get("training_plan")
    testing_plan = context_variables.get("testing_plan")

    has_structured_plan = any(
        section
        for section in (dataset_plan, model_plan, model_survey, training_plan, testing_plan)
    )
    if not has_structured_plan:
        return plan_res

    def _serialize(section):
        if not section:
            return ""
        if isinstance(section, str):
            return section
        return json.dumps(section, ensure_ascii=False, indent=4)

    model_section = model_plan or model_survey or ""
    return (
        "I have reviewed the existing resources and understand the task, and here is the "
        "plan of the dataset, model, training and testing process:\n\n"
        "# Dataset Plan\n"
        f"{_serialize(dataset_plan)}\n\n"
        "# Model Plan\n"
        f"{_serialize(model_section)}\n\n"
        "# Training Plan\n"
        f"{_serialize(training_plan)}\n\n"
        "# Testing Plans\n"
        f"{_serialize(testing_plan)}"
    )


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
