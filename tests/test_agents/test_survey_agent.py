import json
from pathlib import Path

from research_agent.inno.agents.inno_agent.survey_agent import _resolve_reference_paths


def test_resolve_reference_paths_uses_prepare_result_from_context():
    context_variables = {
        "prepare_result": {
            "reference_paths": ["/workplace/VQ-VAE", "/workplace/FSQ"],
        }
    }

    reference_paths = _resolve_reference_paths(context_variables, "workplace")

    assert reference_paths == ["/workplace/VQ-VAE", "/workplace/FSQ"]


def test_resolve_reference_paths_falls_back_to_cached_prepare_result(tmp_dir):
    prepare_stage = Path(tmp_dir) / "prepare_stage"
    prepare_stage.mkdir()
    prepare_result_path = prepare_stage / "prepare_result.json"
    prepare_result_path.write_text(
        json.dumps({"reference_paths": ["/workplace/pytorch-vqgan"]}),
        encoding="utf-8",
    )
    context_variables = {"prepare_artifact_dir": str(prepare_stage)}

    reference_paths = _resolve_reference_paths(context_variables, "workplace")

    assert reference_paths == ["/workplace/pytorch-vqgan"]
    assert context_variables["prepare_result"]["reference_paths"] == ["/workplace/pytorch-vqgan"]


def test_resolve_reference_paths_falls_back_to_workplace_root():
    reference_paths = _resolve_reference_paths({}, "workplace")

    assert reference_paths == ["/workplace"]
