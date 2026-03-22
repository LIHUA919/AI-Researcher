from research_agent.inno.util import run_command_in_container
from research_agent.constant import DOCKER_WORKPLACE_NAME
import os
import shutil
from pathlib import Path
import urllib.request

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
    source_path = f"../benchmark/process/dataset_candidate/{category}"
    if not os.path.exists(source_path):
        raise Exception(f"source path {source_path} not exists")
    
    try:
        # 复制整个目录内容到 dataset_candidate
        shutil.copytree(source_path, dataset_candidate_path)
        print(f"copy {source_path} to {dataset_candidate_path} success")
    except Exception as e:
        raise Exception(f"copy {source_path} to {dataset_candidate_path} failed: {str(e)}")
    ensure_dataset_candidate_compat(category, local_workplace)


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
