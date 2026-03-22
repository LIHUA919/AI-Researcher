import json
from pathlib import Path

from research_agent.inno.tools.inno_tools.planning_tools import (
    plan_dataset,
    plan_testing,
    plan_training,
)
from research_agent.inno_common import ensure_plan_artifacts


def test_plan_tools_persist_stage_artifacts(tmp_path):
    artifact_dir = tmp_path / "plan_stages"
    context_variables = {"plan_artifact_dir": str(artifact_dir)}

    dataset_result = plan_dataset(
        dataset_description="CIFAR-10",
        dataset_location="/workplace/dataset_candidate/cifar-10-python.tar.gz",
        task_definition="train a VQ model",
        read_data_step="read",
        data_preprocessing_step="preprocess",
        data_dataloader_step="loader",
        context_variables=context_variables,
    )
    training_result = plan_training(
        training_pipeline="pipeline",
        loss_function="loss",
        optimizer="adam",
        training_configurations="2 epochs",
        monitor_and_logging="tensorboard",
        context_variables=context_variables,
    )
    testing_result = plan_testing(
        test_metric="reconstruction loss",
        test_data="cifar10 test split",
        test_code="evaluate()",
        context_variables=context_variables,
    )

    dataset_path = artifact_dir / "dataset_plan.json"
    training_path = artifact_dir / "training_plan.json"
    testing_path = artifact_dir / "testing_plan.json"
    index_path = artifact_dir / "plan_index.json"

    assert dataset_path.exists()
    assert training_path.exists()
    assert testing_path.exists()
    assert index_path.exists()

    dataset_payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert dataset_payload["dataset_description"] == "CIFAR-10"

    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert index_payload["dataset_plan"] == str(dataset_path)
    assert index_payload["training_plan"] == str(training_path)
    assert index_payload["testing_plan"] == str(testing_path)

    assert "plan_artifacts" in dataset_result.context_variables
    assert "plan_artifacts" in training_result.context_variables
    assert "plan_artifacts" in testing_result.context_variables


def test_ensure_plan_artifacts_synthesizes_missing_plan_outputs(tmp_path):
    artifact_dir = tmp_path / "plan_stages"
    context_variables = {
        "plan_artifact_dir": str(artifact_dir),
        "prepare_result": {
            "reference_paths": ["/workplace/VQGAN-pytorch", "/workplace/vqvae-pytorch"]
        },
        "model_survey": "Use a VQ bottleneck with a learnable linear transform W.",
    }

    updated = ensure_plan_artifacts(
        context_variables=context_variables,
        dataset_description="Use CIFAR-10 from `/workplace/dataset_candidate/cifar-10-python.tar.gz`.",
        idea_text="reduce representation collapse in VQ models",
        workplace_name="workplace",
    )

    assert (artifact_dir / "dataset_plan.json").exists()
    assert (artifact_dir / "training_plan.json").exists()
    assert (artifact_dir / "testing_plan.json").exists()
    assert updated["dataset_plan"]["dataset_location"] == "/workplace/dataset_candidate/cifar-10-python.tar.gz"
    assert "reference_paths" not in updated["training_plan"]
    assert "plan_artifacts" in updated


def test_ensure_plan_artifacts_preserves_existing_structured_plan(tmp_path):
    artifact_dir = tmp_path / "plan_stages"
    context_variables = {
        "plan_artifact_dir": str(artifact_dir),
        "dataset_plan": {"dataset_description": "existing"},
        "training_plan": {"training_pipeline": "existing"},
        "testing_plan": {"test_metric": "existing"},
    }

    updated = ensure_plan_artifacts(
        context_variables=context_variables,
        dataset_description="ignored",
        idea_text="ignored",
        workplace_name="workplace",
    )

    assert updated["dataset_plan"]["dataset_description"] == "existing"
    assert not (artifact_dir / "dataset_plan.json").exists()
