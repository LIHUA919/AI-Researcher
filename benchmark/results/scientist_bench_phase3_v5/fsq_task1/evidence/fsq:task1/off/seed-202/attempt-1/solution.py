def quantize(values, levels, eps=1e-3):
    """Return normalized FSQ codes, one value per dimension."""
    import math
    
    # Convert to list for easier manipulation
    values = list(values)
    levels = list(levels)
    
    # Ensure we have same number of dimensions
    assert len(values) == len(levels), "Values and levels must have same length"
    
    # Apply bounding with epsilon margin and even-level offset
    bounded = []
    for i, (value, level) in enumerate(zip(values, levels)):
        # Calculate half level count for offset
        half_level = level // 2
        # Apply bounded function with epsilon margin
        bounded_value = half_level * math.tanh(value) 
        # Clip to avoid extreme values due to tanh
        bounded_value = max(-half_level + eps, min(half_level - eps, bounded_value))
        bounded.append(bounded_value)
    
    # Quantize by rounding to nearest integer
    quantized = [round(b) for b in bounded]
    
    # Normalize to [-1, 1]
    normalized = []
    for i, (q, level) in enumerate(zip(quantized, levels)):
        half_level = level // 2
        # Normalize: (quantized_value + half_level) / half_level - 1
        norm = (q + half_level) / half_level - 1.0
        normalized.append(norm)
    
    return normalized


def codes_to_index(codes, levels):
    """Map one normalized code vector to its mixed-radix integer index."""
    # Process dimensions from least to most significant
    index = 0
    multiplier = 1
    
    for code, level in zip(codes, levels):
        # Convert normalized code back to discrete value
        # normalized = (value + level//2) / (level//2) - 1
        # So: value = normalized * (level//2) + (level//2) = (normalized + 1) * (level//2)
        
        # Convert back to discrete value
        half_level = level // 2
        discrete_value = int((code + 1.0) * half_level)
        
        # Clamp to valid range [0, level-1]
        discrete_value = max(0, min(level - 1, discrete_value))
        
        # Add to index (simple mixed-radix)
        index += discrete_value * multiplier
        
        # Update multiplier for next dimension
        multiplier *= level
        
    return index


def index_to_codes(index, levels):
    """Map an integer index back to its normalized code vector."""
    # Process dimensions from most to least significant
    codes = []
    temp_index = index
    
    # We need to work backwards to reconstruct each digit
    for level in reversed(levels):
        half_level = level // 2
        # Extract current digit (remainder when divided by level)
        digit = temp_index % level
        # Convert to normalized form: (digit + half_level) / half_level - 1
        code = (digit + half_level) / half_level - 1.0
        codes.append(code)
        temp_index //= level
    
    # Reverse codes since we processed in reverse order (most to least significant)
    codes.reverse()
    
    return codes
