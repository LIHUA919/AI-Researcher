def test_vq_prepare_fallback_uses_local_frozen_project(tmp_path):
    from research_agent.inno_common import resolve_prepare_result

    workplace = tmp_path / "workplace"
    (workplace / "project").mkdir(parents=True)
    (workplace / "dataset_candidate").mkdir()
    cache_path = tmp_path / "cache"

    result = resolve_prepare_result(
        prepare_res="",
        context_variables={},
        local_root=str(tmp_path),
        workplace_name="workplace",
        category="vq",
        cache_path=str(cache_path),
    )

    assert result["reference_codebases"] == [
        "local/frozen-vq-protocol",
        "local/vq-dataset-candidate",
    ]
    assert result["reference_paths"] == [
        "/workplace/project",
        "/workplace/dataset_candidate",
    ]
    assert (cache_path / "prepare_stage" / "prepare_result.json").is_file()
