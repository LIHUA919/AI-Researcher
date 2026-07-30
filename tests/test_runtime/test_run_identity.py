from pathlib import Path

from research_agent.runtime.run_identity import (
    isolated_container_name,
    isolated_workspace_root,
)


def test_top_level_cache_identity_isolates_workspace_and_container(tmp_path):
    baseline_cache = tmp_path / "runs" / "seed-7" / "baseline"
    closed_cache = tmp_path / "runs" / "seed-7" / "closed"

    baseline_workspace = isolated_workspace_root(
        tmp_path,
        instance_id="one_layer_vq",
        model="openai/gpt-4o",
        cache_path=baseline_cache,
    )
    closed_workspace = isolated_workspace_root(
        tmp_path,
        instance_id="one_layer_vq",
        model="openai/gpt-4o",
        cache_path=closed_cache,
    )

    assert baseline_workspace != closed_workspace
    assert baseline_workspace.parent == tmp_path / "workplace_paper"
    assert closed_workspace.parent == tmp_path / "workplace_paper"
    assert isolated_container_name("paper_eval", "one_layer_vq", baseline_cache) != (
        isolated_container_name("paper_eval", "one_layer_vq", closed_cache)
    )


def test_container_identity_is_docker_safe_and_bounded(tmp_path):
    name = isolated_container_name(
        "Paper Eval/With Spaces",
        "one_layer_vq",
        Path(tmp_path) / ("long-cache-" * 20),
    )

    assert len(name) <= 63
    assert name.replace("-", "").replace("_", "").isalnum()
