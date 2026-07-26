# Immiscible Diffusion task1 candidate interface

Submit one standard-library-only `solution.py` defining:

```python
def assign_noise(images, noises, use_fp16=False):
    """Return a list mapping each image row to one unique noise-row index."""
```

`images` and `noises` are equally sized batches represented as
`list[list[float]]`. Minimize the total squared L2 distance across the whole
batch; a greedy nearest-neighbor assignment is not sufficient. The return value
must be a permutation of `range(len(noises))`.

When `use_fp16=True`, convert every input scalar to IEEE 754 binary16 before
computing the assignment cost. The returned indices still refer to the original
noise rows.

The CPU contract checks output structure, global assignment optimality,
multi-dimensional inputs, ties, and fp16 behavior. It does not run diffusion
training and cannot establish training-speed or image-quality claims.
