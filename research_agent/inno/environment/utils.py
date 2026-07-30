from research_agent.inno.util import run_command_in_container
from research_agent.constant import DOCKER_WORKPLACE_NAME
import os
import shutil
from pathlib import Path
import hashlib
import tarfile
import urllib.request


CIFAR10_ARCHIVE_MD5 = "c58f30108f718f92721af3b95e74349a"
CIFAR10_ARCHIVE_SHA256 = (
    "6d958be074577803d12ecdefd02955f39262c83c16fe9348329d7fe0b5c001ce"
)


def dataset_source_path(category: str) -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "benchmark" / "process" / "dataset_candidate" / category

def setup_metachain():
    cmd = "pip list | grep metachain"
    response = run_command_in_container(cmd)
    if response['status'] == 0:
        print("Metachain is already installed.")
        return
    cmd = f"cd /{DOCKER_WORKPLACE_NAME}/metachain && pip install -e ."
    response = run_command_in_container(cmd)
    if response['status'] == 0:
        print("Metachain is installed.")
        return
    else:
        raise Exception(f"Failed to install metachain. {response['result']}")


def setup_dataset(category: str, local_workplace: str):
    # 构建目标路径
    dataset_candidate_path = os.path.join(local_workplace, "dataset_candidate")
    
    # 检查目标目录是否存在
    if os.path.exists(dataset_candidate_path):
        print("dataset_candidate exists")
        ensure_dataset_candidate_compat(category, local_workplace)
        return
    
    # 检查源目录是否存在
    source_path = dataset_source_path(category)
    if not source_path.exists():
        raise Exception(f"source path {source_path} not exists")
    
    try:
        # 复制整个目录内容到 dataset_candidate
        shutil.copytree(source_path, dataset_candidate_path)
        print(f"copy {source_path} to {dataset_candidate_path} success")
    except Exception as e:
        raise Exception(f"copy {source_path} to {dataset_candidate_path} failed: {str(e)}")
    ensure_dataset_candidate_compat(category, local_workplace)


def setup_project_scaffold(
    category: str,
    local_workplace: str,
    *,
    seed: int,
) -> None:
    """Install the frozen real-data scaffold before an implementation agent runs."""
    if category != "vq":
        return

    workplace = Path(local_workplace)
    dataset_candidate = workplace / "dataset_candidate"
    archive = dataset_candidate / "cifar-10-python.tar.gz"
    if not archive.is_file():
        raise FileNotFoundError(f"missing official CIFAR-10 archive: {archive}")
    md5_digest = hashlib.md5()
    sha256_digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            md5_digest.update(chunk)
            sha256_digest.update(chunk)
    if md5_digest.hexdigest() != CIFAR10_ARCHIVE_MD5:
        raise ValueError("CIFAR-10 archive checksum does not match the official file")
    if sha256_digest.hexdigest() != CIFAR10_ARCHIVE_SHA256:
        raise ValueError("CIFAR-10 archive SHA-256 does not match the official file")

    project = workplace / "project"
    project.mkdir(parents=True, exist_ok=True)
    data_dir = project / "data"
    extracted = data_dir / "cifar-10-batches-py"
    if not extracted.is_dir():
        data_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as bundle:
            destination = data_dir.resolve()
            for member in bundle.getmembers():
                member_path = (destination / member.name).resolve()
                if destination not in member_path.parents and member_path != destination:
                    raise ValueError(f"unsafe CIFAR-10 archive member: {member.name}")
            bundle.extractall(data_dir)

    repo_root = Path(__file__).resolve().parents[3]
    protocol_source = repo_root / "benchmark/real_smoke/one_layer_vq/train.py"
    entrypoint_source = dataset_source_path(category) / "run_training_testing.py"
    spec_loader_source = dataset_source_path(category) / "attempt_spec.py"
    protocol_target = project / "protocol.py"
    entrypoint_target = project / "run_training_testing.py"
    spec_loader_target = project / "attempt_spec.py"
    if not protocol_target.exists():
        shutil.copy2(protocol_source, protocol_target)
    if not entrypoint_target.exists():
        shutil.copy2(entrypoint_source, entrypoint_target)
    if not spec_loader_target.exists():
        shutil.copy2(spec_loader_source, spec_loader_target)
    (project / ".experiment_seed").write_text(str(seed), encoding="utf-8")


def ensure_dataset_candidate_compat(category: str, local_workplace: str):
    """Backfill expected benchmark assets when prompts reference files not bundled locally."""
    if category != "vq":
        return

    dataset_candidate = Path(local_workplace) / "dataset_candidate"
    if not dataset_candidate.exists():
        return

    edm_dir = dataset_candidate / "edm"
    edm_dir.mkdir(parents=True, exist_ok=True)
    edm_readme = edm_dir / "README.md"
    if not edm_readme.exists():
        edm_readme.write_text(
            """# EDM Dataset Compatibility Notes

This workspace provides the CIFAR-10 evaluation assets needed by the benchmark prompts.

Available files:
- `../cifar10-32x32.npz`: reference statistics used for FID evaluation on CIFAR-10.
- `../cifar-10-python.tar.gz`: CIFAR-10 Python archive used by many PyTorch examples.

Recommended dataset handling:
1. If a training script expects the official CIFAR-10 tarball, use `../cifar-10-python.tar.gz`.
2. If a metric script expects EDM reference statistics, use `../cifar10-32x32.npz`.
3. If neither file is consumed directly, using `torchvision.datasets.CIFAR10(download=True)` is acceptable.

The original EDM repository is not vendored into this workspace. This README is a compatibility shim so the planning and implementation agents can resolve the benchmark paths consistently.
""",
            encoding="utf-8",
        )

    cifar_tarball = dataset_candidate / "cifar-10-python.tar.gz"
    if cifar_tarball.exists():
        return

    download_url = "https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz"
    try:
        urllib.request.urlretrieve(download_url, cifar_tarball)
    except Exception as error:
        placeholder = dataset_candidate / "cifar-10-python.tar.gz.README"
        placeholder.write_text(
            "Automatic download of CIFAR-10 tarball failed.\n"
            f"Expected URL: {download_url}\n"
            f"Error: {error}\n",
            encoding="utf-8",
        )


def ensure_legacy_workspace_aliases(local_workplace: str):
    """Create compatibility aliases for cached paths that include GitHub owner prefixes."""
    workplace = Path(local_workplace)
    alias_map = {
        "1Konny/VQ-VAE": "VQ-VAE",
        "dome272/VQGAN-pytorch": "VQGAN-pytorch",
        "CompVis/taming-transformers": "taming-transformers",
        "Nikolai10/FSQ": "FSQ",
        "leaderj1001/CLIP": "CLIP",
    }

    for legacy_path, target_name in alias_map.items():
        target = workplace / target_name
        if not target.exists():
            continue
        alias = workplace / legacy_path
        alias.parent.mkdir(parents=True, exist_ok=True)
        if alias.exists() or alias.is_symlink():
            continue
        alias.symlink_to(target)


def normalize_workplace_layout(local_workplace: str):
    """Flatten legacy nested `workplace/workplace/*` layouts into `workplace/*`."""
    workplace = Path(local_workplace)
    nested_workplace = workplace / "workplace"
    if not nested_workplace.is_dir():
        return

    current_entries = [entry.name for entry in workplace.iterdir() if entry.name != "workplace"]
    if current_entries:
        return

    for entry in nested_workplace.iterdir():
        shutil.move(str(entry), str(workplace / entry.name))
    nested_workplace.rmdir()
