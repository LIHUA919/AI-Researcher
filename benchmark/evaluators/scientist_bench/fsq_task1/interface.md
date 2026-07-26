# FSQ task1 candidate interface

Submit one standard-library-only `solution.py` defining:

```python
def quantize(values, levels, eps=1e-3):
    """Return normalized FSQ codes, one value per dimension."""

def codes_to_index(codes, levels):
    """Map one normalized code vector to its mixed-radix integer index."""

def index_to_codes(index, levels):
    """Map an integer index back to its normalized code vector."""
```

Follow the official FSQ reference semantics:

- Bound each input with the epsilon margin and the even-level offset.
- Round the bounded value and normalize each dimension to `[-1, 1]`.
- Use the first dimension as the least-significant mixed-radix digit.
- Odd and even level counts must both work.

The CPU contract checks bounding/rounding, saturation, even-level offsets, and
code/index round trips. It does not execute an autograd engine, train a VAE, or
measure codebook utilization or generative quality.
