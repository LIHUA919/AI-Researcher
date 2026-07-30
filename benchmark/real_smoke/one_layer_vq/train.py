from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import random
import subprocess
import time
from typing import Any, Mapping

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset, Subset
from torchvision import transforms
from torchvision.datasets import CIFAR10


def _quantize_latents(
    latents: torch.Tensor,
    *,
    codebook: torch.Tensor,
    latent_dim: int,
    commitment_weight: float,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    batch, channels, height, width = latents.shape
    if channels != latent_dim:
        raise ValueError(f"expected latent dimension {latent_dim}, got {channels}")
    channels_last = latents.permute(0, 2, 3, 1).contiguous()
    flattened = channels_last.view(-1, channels)
    distances = (
        flattened.square().sum(dim=1, keepdim=True)
        + codebook.square().sum(dim=1)
        - 2.0 * flattened @ codebook.t()
    )
    indices = distances.argmin(dim=1)
    quantized = F.embedding(indices, codebook).view(
        batch,
        height,
        width,
        channels,
    )
    quantization_loss = commitment_weight * F.mse_loss(
        channels_last, quantized.detach()
    ) + F.mse_loss(quantized, channels_last.detach())
    straight_through = channels_last + (quantized - channels_last).detach()
    return (
        straight_through.permute(0, 3, 1, 2).contiguous(),
        indices.view(batch, height, width),
        quantization_loss,
    )


class SimVQQuantizer(nn.Module):
    """Frozen code basis with one trainable linear codebook projection."""

    def __init__(
        self,
        *,
        codebook_size: int,
        latent_dim: int,
        commitment_weight: float,
    ) -> None:
        super().__init__()
        self.codebook_size = codebook_size
        self.latent_dim = latent_dim
        self.commitment_weight = commitment_weight
        self.code_basis = nn.Embedding(codebook_size, latent_dim)
        nn.init.normal_(
            self.code_basis.weight,
            mean=0.0,
            std=latent_dim**-0.5,
        )
        self.code_basis.weight.requires_grad_(False)
        self.code_projection = nn.Linear(latent_dim, latent_dim)
        nn.init.eye_(self.code_projection.weight)
        nn.init.zeros_(self.code_projection.bias)

    def forward(
        self,
        latents: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        codebook = self.code_projection(self.code_basis.weight)
        return _quantize_latents(
            latents,
            codebook=codebook,
            latent_dim=self.latent_dim,
            commitment_weight=self.commitment_weight,
        )


class VanillaVQQuantizer(nn.Module):
    """Standard VQ with independently trainable code vectors."""

    def __init__(
        self,
        *,
        codebook_size: int,
        latent_dim: int,
        commitment_weight: float,
    ) -> None:
        super().__init__()
        self.latent_dim = latent_dim
        self.commitment_weight = commitment_weight
        self.codebook = nn.Embedding(codebook_size, latent_dim)
        nn.init.normal_(
            self.codebook.weight,
            mean=0.0,
            std=latent_dim**-0.5,
        )

    def forward(
        self,
        latents: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        return _quantize_latents(
            latents,
            codebook=self.codebook.weight,
            latent_dim=self.latent_dim,
            commitment_weight=self.commitment_weight,
        )


class SimVQAutoencoder(nn.Module):
    def __init__(
        self,
        *,
        codebook_size: int,
        latent_dim: int,
        commitment_weight: float,
        variant: str = "simvq",
    ) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=4, stride=2, padding=1),
            nn.SiLU(),
            nn.Conv2d(32, 64, kernel_size=4, stride=2, padding=1),
            nn.SiLU(),
            nn.Conv2d(64, latent_dim, kernel_size=3, padding=1),
        )
        self.decoder = nn.Sequential(
            nn.ConvTranspose2d(
                latent_dim,
                64,
                kernel_size=4,
                stride=2,
                padding=1,
            ),
            nn.SiLU(),
            nn.ConvTranspose2d(
                64,
                32,
                kernel_size=4,
                stride=2,
                padding=1,
            ),
            nn.SiLU(),
            nn.Conv2d(32, 3, kernel_size=3, padding=1),
            nn.Sigmoid(),
        )
        quantizer_type = {
            "simvq": SimVQQuantizer,
            "vanilla": VanillaVQQuantizer,
        }.get(variant)
        if quantizer_type is None:
            raise ValueError(f"unknown quantizer variant: {variant}")
        self.quantizer = quantizer_type(
            codebook_size=codebook_size,
            latent_dim=latent_dim,
            commitment_weight=commitment_weight,
        )

    def forward(
        self,
        images: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        latents = self.encoder(images)
        quantized, indices, quantization_loss = self.quantizer(latents)
        return self.decoder(quantized), indices, quantization_loss


def build_optimizer(
    model: SimVQAutoencoder,
    *,
    learning_rate: float,
    projection_lr_multiplier: float,
) -> torch.optim.Adam:
    """Build disjoint base/projection groups for the Phase A Intervention."""

    if not isinstance(model.quantizer, SimVQQuantizer):
        raise ValueError(
            "projection_lr_multiplier requires the simvq quantizer variant"
        )
    if (
        isinstance(projection_lr_multiplier, bool)
        or not isinstance(projection_lr_multiplier, (int, float))
        or not math.isfinite(float(projection_lr_multiplier))
        or projection_lr_multiplier <= 0
    ):
        raise ValueError("projection_lr_multiplier must be finite and positive")
    projection_parameters = list(model.quantizer.code_projection.parameters())
    if not projection_parameters:
        raise RuntimeError("code_projection has no trainable parameters")
    projection_ids = {id(parameter) for parameter in projection_parameters}
    base_parameters = [
        parameter
        for parameter in model.parameters()
        if parameter.requires_grad and id(parameter) not in projection_ids
    ]
    base_ids = {id(parameter) for parameter in base_parameters}
    if base_ids & projection_ids:
        raise RuntimeError("optimizer parameter groups overlap")
    expected_ids = {
        id(parameter) for parameter in model.parameters() if parameter.requires_grad
    }
    if base_ids | projection_ids != expected_ids:
        raise RuntimeError("optimizer groups do not cover trainable parameters")
    return torch.optim.Adam(
        [
            {
                "name": "base",
                "params": base_parameters,
                "lr": learning_rate,
            },
            {
                "name": "code_projection",
                "params": projection_parameters,
                "lr": learning_rate * projection_lr_multiplier,
            },
        ]
    )


class HuggingFaceCIFAR10(Dataset):
    """Torch adapter for the canonical uoft-cs/cifar10 mirror."""

    def __init__(self, split, transform) -> None:
        self.split = split
        self.transform = transform

    def __len__(self) -> int:
        return len(self.split)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        row = self.split[index]
        return self.transform(row["img"].convert("RGB")), int(row["label"])


def _select_device(requested: str) -> torch.device:
    if requested != "auto":
        device = torch.device(requested)
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    if device.type == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("MPS was requested but is unavailable")
    return device


def _git_revision(repository_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _git_worktree_dirty(repository_root: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode != 0 or bool(completed.stdout.strip())


def _write_log(stream, event: str, **payload: Any) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **payload,
    }
    line = json.dumps(record, sort_keys=True)
    stream.write(line + "\n")
    stream.flush()
    print(line, flush=True)


def evidence_payload_digest(arrays: Mapping[str, np.ndarray]) -> str:
    """Digest named array evidence with explicit metadata and byte framing."""

    digest = hashlib.sha256()
    digest.update(b"ai-researcher/evidence-payload/v1\0")
    for name in sorted(arrays):
        array = np.ascontiguousarray(arrays[name])
        header = json.dumps(
            {
                "name": name,
                "dtype": array.dtype.str,
                "shape": list(array.shape),
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        body = array.tobytes(order="C")
        for field in (header, body):
            digest.update(len(field).to_bytes(8, "big"))
            digest.update(field)
    return digest.hexdigest()


def _installed_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            f"required distribution is unavailable: {distribution}"
        ) from exc


def validate_v3_execution_descriptors(
    args: argparse.Namespace,
    *,
    project_dir: Path,
    resolved_device: str,
) -> dict[str, Any] | None:
    """Bind claimed dataset/environment descriptors to the executing process."""

    spec = getattr(args, "_attempt_spec_payload", None)
    if spec is None:
        return None
    descriptors = spec.get("descriptors")
    if not isinstance(descriptors, dict):
        raise ValueError("V3 Attempt Spec descriptors must be an object")
    archive = project_dir.parent / "dataset_candidate/cifar-10-python.tar.gz"
    if not archive.is_file():
        raise FileNotFoundError(
            f"missing official CIFAR-10 archive for provenance: {archive}"
        )
    archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    config = spec["effective_config"]
    expected_dataset = {
        "dataset_id": config["dataset_id"],
        "archive_sha256": archive_sha256,
        "source": config["data_source"],
        "train_split": config["train_split"],
        "test_split": config["test_split"],
        "train_selector": {
            "name": "torch_randperm_without_replacement",
            "version": "1",
            "seed": config["seed"],
            "count": config["train_samples"],
        },
        "test_selector": {
            "name": "canonical_prefix",
            "version": "1",
            "count": config["test_samples"],
        },
        "transform": {
            "name": "torchvision.transforms.ToTensor",
            "version": "1",
        },
    }
    expected_environment = {
        "python": platform.python_version(),
        "numpy": _installed_version("numpy"),
        "torch": _installed_version("torch"),
        "torchvision": _installed_version("torchvision"),
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
        "requested_device": config["device_policy"],
        "resolved_device": resolved_device,
    }
    expected = {
        "dataset": expected_dataset,
        "environment": expected_environment,
    }
    if descriptors != expected:
        raise ValueError(
            "executed dataset/environment do not match Attempt Spec descriptors"
        )
    return expected


def build_evaluation_manifest(
    *,
    args: argparse.Namespace,
    repository_root: Path,
    resolved_device: str,
    evidence_payload_sha256: str,
    legacy_evidence_sha256: str,
    originals_sha256: str,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    """Build a legacy schema-1 or attested schema-2 evidence manifest."""

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "dataset_id": "cifar10",
        "dataset_source": args.data_source,
        "split": "test",
        "epochs_completed": args.epochs,
        "seed": args.seed,
        "codebook_size": args.codebook_size,
        "sample_count": args.test_samples,
        "train_sample_count": args.train_samples,
        "training_protocol": "deterministic_subset_without_replacement",
        "device": resolved_device,
        "model": f"{args.variant}_smoke_autoencoder",
        "quantizer_variant": args.variant,
        "latent_dim": args.latent_dim,
        "commitment_weight": args.commitment_weight,
        "learning_rate": args.learning_rate,
        "batch_size": args.batch_size,
        "code_revision": _git_revision(repository_root),
        "git_worktree_dirty": _git_worktree_dirty(repository_root),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "evidence_digest": legacy_evidence_sha256,
        "original_images_prefix_sha256": originals_sha256,
    }
    spec = getattr(args, "_attempt_spec_payload", None)
    if spec is None:
        return manifest

    proposal = spec["proposal"]
    effective_config = spec["effective_config"]
    provenance = spec["provenance"]
    descriptors = spec["descriptors"]
    if not isinstance(proposal, dict):
        raise ValueError("V3 Attempt Spec proposal must be an object")
    if not isinstance(effective_config, dict):
        raise ValueError("V3 Attempt Spec effective_config must be an object")
    if not isinstance(provenance, dict):
        raise ValueError("V3 Attempt Spec provenance must be an object")
    if not isinstance(descriptors, dict):
        raise ValueError("V3 Attempt Spec descriptors must be an object")
    proposal_record = proposal["record"]
    proposal_change = proposal["change"]
    if not isinstance(proposal_record, dict):
        raise ValueError("V3 proposal record must be an object")
    if proposal_change is not None and not isinstance(proposal_change, dict):
        raise ValueError("V3 proposal change must be an object or null")
    actual_effective_config = {
        "dataset_id": "cifar10",
        "data_source": args.data_source,
        "train_split": "train",
        "test_split": "test",
        "epochs": args.epochs,
        "train_samples": args.train_samples,
        "test_samples": args.test_samples,
        "batch_size": args.batch_size,
        "codebook_size": args.codebook_size,
        "latent_dim": args.latent_dim,
        "quantizer_variant": args.variant,
        "base_learning_rate": args.learning_rate,
        "device_policy": "auto",
        "projection_lr_multiplier": args.projection_lr_multiplier,
        "commitment_weight": args.commitment_weight,
        "seed": args.seed,
        "resolved_device": resolved_device,
    }
    if effective_config != actual_effective_config:
        raise ValueError(
            "executed arguments do not match the Attempt Spec effective config"
        )
    if started_at is None or completed_at is None:
        raise ValueError("V3 manifest requires execution timestamps")
    manifest.update(
        {
            "schema_version": 2,
            "attempt_spec_sha256": args._attempt_spec_sha256,
            "task_id": spec["task_id"],
            "contract": {
                "id": "one-layer-vq-cifar10-adaptive",
                "version": "3-phase-a",
                "digest": provenance["contract_digest"],
            },
            "provenance": {
                "proposal_digest": proposal["digest"],
                "intervention_digest": provenance["intervention_digest"],
                "config_digest": provenance["config_digest"],
                "source_digest": provenance["source_digest"],
                "dataset_digest": provenance["dataset_digest"],
                "environment_digest": provenance["environment_digest"],
                "evaluator_digest": provenance["evaluator_digest"],
                "manipulation_status": provenance["manipulation_status"],
            },
            "intervention": {
                "decision_point": proposal_record["decision_point"],
                "knob": (
                    proposal_change["name"] if proposal_change is not None else None
                ),
                "from": (
                    proposal_change["from"] if proposal_change is not None else None
                ),
                "to": (proposal_change["to"] if proposal_change is not None else None),
                "effective_knobs": {
                    "projection_lr_multiplier": effective_config[
                        "projection_lr_multiplier"
                    ],
                    "commitment_weight": effective_config["commitment_weight"],
                },
            },
            "effective_config": effective_config,
            "descriptors": descriptors,
            "optimizer": {
                "base_group": "base",
                "base_learning_rate": args.learning_rate,
                "projection_group": "code_projection",
                "projection_learning_rate": (
                    args.learning_rate * args.projection_lr_multiplier
                ),
            },
            "execution": {
                "started_at": started_at,
                "completed_at": completed_at,
                "exit_code": 0,
            },
            "evidence_payload_digest": evidence_payload_sha256,
        }
    )
    return manifest


def _load_cifar10(data_source: str, data_dir: Path, transform):
    if data_source == "torchvision":
        return (
            CIFAR10(
                root=data_dir,
                train=True,
                download=True,
                transform=transform,
            ),
            CIFAR10(
                root=data_dir,
                train=False,
                download=True,
                transform=transform,
            ),
        )
    if data_source == "huggingface":
        from datasets import load_dataset

        dataset = load_dataset(
            "uoft-cs/cifar10",
            cache_dir=str(data_dir),
        )
        return (
            HuggingFaceCIFAR10(dataset["train"], transform),
            HuggingFaceCIFAR10(dataset["test"], transform),
        )
    raise ValueError(f"unsupported data source: {data_source}")


def run(args: argparse.Namespace) -> Path:
    if args.epochs != 2:
        raise ValueError("the smoke protocol requires exactly two epochs")
    if args.test_samples < 1024:
        raise ValueError("the smoke protocol requires at least 1024 test samples")
    if args.train_samples < args.batch_size:
        raise ValueError("train_samples must be at least one batch")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_names = (
        "evaluation_arrays.npz",
        "evaluation_manifest.json",
        "run.log",
        "verification_result.json",
    )
    existing_evidence = [
        name for name in evidence_names if (output_dir / name).exists()
    ]
    if existing_evidence and not args.overwrite:
        raise FileExistsError(
            "refusing to overwrite existing evidence: " + ", ".join(existing_evidence)
        )
    data_dir = Path(args.data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    repository_root = Path(__file__).resolve().parents[3]
    device = _select_device(args.device)
    validate_v3_execution_descriptors(
        args,
        project_dir=Path(__file__).resolve().parent,
        resolved_device=str(device),
    )

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    transform = transforms.ToTensor()
    train_dataset, test_dataset = _load_cifar10(
        args.data_source,
        data_dir,
        transform,
    )
    if args.train_samples > len(train_dataset):
        raise ValueError("train_samples exceeds the CIFAR-10 training split")
    if args.test_samples > len(test_dataset):
        raise ValueError("test_samples exceeds the CIFAR-10 test split")

    subset_generator = torch.Generator().manual_seed(args.seed)
    train_indices = torch.randperm(
        len(train_dataset),
        generator=subset_generator,
    )[: args.train_samples]
    train_loader = DataLoader(
        Subset(train_dataset, train_indices.tolist()),
        batch_size=args.batch_size,
        shuffle=True,
        generator=torch.Generator().manual_seed(args.seed),
        num_workers=0,
        drop_last=False,
    )
    test_loader = DataLoader(
        Subset(test_dataset, list(range(args.test_samples))),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=0,
        drop_last=False,
    )

    model = SimVQAutoencoder(
        codebook_size=args.codebook_size,
        latent_dim=args.latent_dim,
        commitment_weight=args.commitment_weight,
        variant=args.variant,
    ).to(device)
    optimizer = build_optimizer(
        model,
        learning_rate=args.learning_rate,
        projection_lr_multiplier=args.projection_lr_multiplier,
    )
    log_path = output_dir / "run.log"
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    with log_path.open("w", encoding="utf-8") as log:
        _write_log(
            log,
            "run_started",
            device=str(device),
            seed=args.seed,
            epochs=args.epochs,
            train_samples=args.train_samples,
            test_samples=args.test_samples,
            data_source=args.data_source,
            variant=args.variant,
            codebook_size=args.codebook_size,
            latent_dim=args.latent_dim,
        )
        for epoch in range(1, args.epochs + 1):
            model.train()
            total_loss = 0.0
            total_reconstruction_loss = 0.0
            total_quantization_loss = 0.0
            for images, _ in train_loader:
                images = images.to(device)
                optimizer.zero_grad(set_to_none=True)
                reconstructions, _, quantization_loss = model(images)
                reconstruction_loss = F.mse_loss(reconstructions, images)
                loss = reconstruction_loss + quantization_loss
                loss.backward()
                optimizer.step()
                total_loss += float(loss.detach().cpu())
                total_reconstruction_loss += float(reconstruction_loss.detach().cpu())
                total_quantization_loss += float(quantization_loss.detach().cpu())
            batch_count = len(train_loader)
            _write_log(
                log,
                "epoch_completed",
                epoch=epoch,
                batches=batch_count,
                mean_loss=total_loss / batch_count,
                mean_reconstruction_loss=(total_reconstruction_loss / batch_count),
                mean_quantization_loss=(total_quantization_loss / batch_count),
            )

        model.eval()
        originals_parts = []
        reconstructions_parts = []
        indices_parts = []
        with torch.inference_mode():
            for images, _ in test_loader:
                images_device = images.to(device)
                reconstructions, indices, _ = model(images_device)
                originals_parts.append(
                    images.mul(255.0).round().clamp(0, 255).to(torch.uint8)
                )
                reconstructions_parts.append(
                    reconstructions.cpu()
                    .mul(255.0)
                    .round()
                    .clamp(0, 255)
                    .to(torch.uint8)
                )
                indices_parts.append(indices.cpu().to(torch.int32))

        originals = torch.cat(originals_parts).permute(0, 2, 3, 1).numpy()
        reconstructions = torch.cat(reconstructions_parts).permute(0, 2, 3, 1).numpy()
        indices = torch.cat(indices_parts).numpy()
        np.savez_compressed(
            output_dir / "evaluation_arrays.npz",
            original_images=originals,
            reconstructed_images=reconstructions,
            codebook_indices=indices,
        )
        evidence_payload_sha256 = evidence_payload_digest(
            {
                "original_images": originals,
                "reconstructed_images": reconstructions,
                "codebook_indices": indices,
            }
        )
        legacy_evidence_sha256 = hashlib.sha256(
            originals.tobytes() + reconstructions.tobytes() + indices.tobytes()
        ).hexdigest()
        originals_digest = hashlib.sha256(originals[:1024].tobytes()).hexdigest()
        completed_at = datetime.now(timezone.utc).isoformat()
        manifest = build_evaluation_manifest(
            args=args,
            repository_root=repository_root,
            resolved_device=str(device),
            evidence_payload_sha256=evidence_payload_sha256,
            legacy_evidence_sha256=legacy_evidence_sha256,
            originals_sha256=originals_digest,
            started_at=started_at,
            completed_at=completed_at,
        )
        (output_dir / "evaluation_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        _write_log(
            log,
            "run_completed",
            elapsed_seconds=time.monotonic() - started,
            evidence_digest=legacy_evidence_sha256,
            evidence_payload_digest=evidence_payload_sha256,
        )
    return output_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a real-data two-epoch SimVQ evidence smoke.",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--data-dir",
        default="benchmark/data/cifar10",
    )
    parser.add_argument(
        "--data-source",
        choices=("torchvision", "huggingface"),
        default="torchvision",
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--train-samples", type=int, default=8192)
    parser.add_argument("--test-samples", type=int, default=1024)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--codebook-size", type=int, default=128)
    parser.add_argument("--latent-dim", type=int, default=16)
    parser.add_argument(
        "--variant",
        choices=("simvq", "vanilla"),
        default="simvq",
    )
    parser.add_argument("--commitment-weight", type=float, default=0.25)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument(
        "--projection-lr-multiplier",
        type=float,
        default=1.0,
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    run(build_parser().parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
