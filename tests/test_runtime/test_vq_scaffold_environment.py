from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import tarfile

from research_agent.inno.environment import utils


def test_vq_scaffold_installs_protocol_data_and_seed(tmp_path, monkeypatch):
    workplace = tmp_path / "workplace"
    dataset = workplace / "dataset_candidate"
    dataset.mkdir(parents=True)
    archive = dataset / "cifar-10-python.tar.gz"
    payload = tmp_path / "data_batch_1"
    payload.write_bytes(b"official-test-fixture")
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(
            payload,
            arcname="cifar-10-batches-py/data_batch_1",
        )
    monkeypatch.setattr(
        utils,
        "CIFAR10_ARCHIVE_MD5",
        hashlib.md5(archive.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        utils,
        "CIFAR10_ARCHIVE_SHA256",
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )

    utils.setup_project_scaffold("vq", str(workplace), seed=401)

    project = workplace / "project"
    assert (project / "protocol.py").is_file()
    assert (project / "run_training_testing.py").is_file()
    assert (project / "attempt_spec.py").is_file()
    repo_root = Path(__file__).resolve().parents[2]
    assert (project / "protocol.py").read_bytes() == (
        repo_root / "benchmark/real_smoke/one_layer_vq/train.py"
    ).read_bytes()
    for name in ("run_training_testing.py", "attempt_spec.py"):
        assert (project / name).read_bytes() == (
            repo_root / "benchmark/process/dataset_candidate/vq" / name
        ).read_bytes()
    assert (project / ".experiment_seed").read_text(encoding="utf-8") == "401"
    assert (
        project / "data/cifar-10-batches-py/data_batch_1"
    ).read_bytes() == b"official-test-fixture"

    monkeypatch.syspath_prepend(str(project))
    spec = importlib.util.spec_from_file_location(
        "scaffold_entrypoint",
        project / "run_training_testing.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    arguments = module._default_arguments()
    assert arguments[arguments.index("--seed") + 1] == "401"
    assert arguments[arguments.index("--epochs") + 1] == "2"
    assert arguments[arguments.index("--train-samples") + 1] == "8192"
