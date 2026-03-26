from research_agent.inno.environment.utils import dataset_source_path


def test_dataset_source_path_resolves_from_repo_root():
    source_path = dataset_source_path("vq")

    assert source_path.name == "vq"
    assert source_path.exists() is True
    assert source_path.joinpath("metaprompt.py").exists() is True
