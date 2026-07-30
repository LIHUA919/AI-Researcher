from benchmark.process.dataset_candidate.vq import metaprompt


def test_vq_prompt_describes_available_data_and_task_aligned_metrics():
    assert "torchvision.datasets.CIFAR10" in metaprompt.DATASET
    assert "not image data" in metaprompt.DATASET
    assert "cifar-10-python.tar.gz" not in metaprompt.DATASET
    assert "codebook utilization" in metaprompt.EVALUATION.lower()
    assert "reconstruction" in metaprompt.EVALUATION.lower()
    assert "diffusion models" not in metaprompt.BASELINE.lower()
    assert "same architecture" in metaprompt.BASELINE.lower()
