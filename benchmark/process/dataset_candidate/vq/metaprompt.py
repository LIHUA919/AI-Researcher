TASK = """
Train and evaluate a vector-quantized image autoencoder on CIFAR-10. The
implementation must address codebook representation collapse while preserving
reconstruction quality. For the one_layer_vq task, implement the SimVQ-style
learnable linear transformation over a fixed latent code basis and compare it
with a vanilla VQ configuration under the same encoder, decoder, codebook size,
training budget, data split, and seed.
"""

DATASET = r"""
Use the actual CIFAR-10 images loaded with
`torchvision.datasets.CIFAR10(root="/workplace/project/data", download=True)`.
Use the official training split for training and the official test split for
evaluation; do not use toy, random, or generated substitutes.

The bundled `/workplace/dataset_candidate/cifar10-32x32.npz` contains only
precomputed Inception mean and covariance values for optional FID calculation.
It is not image data and must not be treated as a CIFAR-10 training archive.
"""

BASELINE = r"""
The primary baseline is a vanilla VQ model compared with the proposed
SimVQ-style model under the same architecture, codebook size, optimizer,
training steps, data order, seed, and evaluation sample set. Published
ImageNet-128 SimVQ results may be used as qualitative context only; they are
not numerical baselines for this two-epoch CIFAR-10 smoke protocol.
"""

COMPARISON = r"""
Report paired results for the vanilla VQ and SimVQ-style configurations.
Codebook utilization is the primary metric. Also report active-code count and
codebook perplexity, with reconstruction MSE and PSNR as quality guardrails.
Do not claim a scientific improvement from a single two-epoch smoke run.
Calibrate any pass threshold on independent runs using this exact CIFAR-10
architecture, seed policy, and compute budget.
"""

EVALUATION = r"""
The primary metric is codebook utilization: the number of distinct code
indices selected on held-out test examples divided by the configured codebook
size. The evaluator also computes codebook perplexity, reconstruction MSE, and
reconstruction PSNR independently from raw code indices, original images, and
reconstructed images. FID is optional and is not the primary metric for this
VQ reconstruction task.

For the checked smoke contract, evaluate at least 1024 held-out CIFAR-10 test
images after exactly two training epochs and emit the raw evidence described by
the Evaluation Contract.
"""

REF = r"""
Use the official SimVQ repository and paper implementation as the method
reference. Use torchvision's CIFAR-10 loader for the dataset. Keep the exact
code revision, configuration, seed, execution log, and raw evaluator artifacts
for every Experiment Attempt.
"""
