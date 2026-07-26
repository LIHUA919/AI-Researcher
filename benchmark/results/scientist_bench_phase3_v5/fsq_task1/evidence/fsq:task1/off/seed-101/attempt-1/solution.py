def quantize(values, levels, eps=1e-3):
    """Return normalized FSQ codes, one value per dimension."""
    import math
    
    # Convert to list if needed
    if not isinstance(values, (list, tuple)):
        values = [values]
    if not isinstance(levels, (list, tuple)):
        levels = [levels]
    
    # Ensure same length
    if len(values) != len(levels):
        raise ValueError("Values and levels must have the same length")
    
    # Apply bounding and quantization
    codes = []
    for i, (value, level) in enumerate(zip(values, levels)):
        # Bound the value with epsilon margin
        bound_value = value * (1 - eps)
        
        # Apply even-level offset (center the quantization)
        half_level = level / 2.0
        bounded = bound_value + half_level
        
        # Round to nearest integer
        rounded = round(bounded)
        
        # Clamp to valid range [0, level-1]
        clamped = max(0, min(rounded, level - 1))
        
        # Normalize to [-1, 1]
        normalized = (clamped / (level - 1)) * 2 - 1
        
        codes.append(normalized)
    
    return codes


def codes_to_index(codes, levels):
    """Map one normalized code vector to its mixed-radix integer index."""
    # Convert codes and levels to lists if needed
    if not isinstance(codes, (list, tuple)):
        codes = [codes]
    if not isinstance(levels, (list, tuple)):
        levels = [levels]
    
    # Validate input sizes
    if len(codes) != len(levels):
        raise ValueError("Codes and levels must have the same length")
    
    # Convert codes back to discrete values and compute index
    index = 0
    multiplier = 1
    
    # Process from most significant to least significant (reverse order)
    for i in range(len(levels) - 1, -1, -1):
        # Convert normalized code back to discrete value
        # Normalize [-1, 1] to [0, level-1]
        discrete_val = (codes[i] + 1) / 2 * (levels[i] - 1)
        discrete_val = round(discrete_val)
        discrete_val = max(0, min(discrete_val, levels[i] - 1))
        
        index += discrete_val * multiplier
        multiplier *= levels[i]
    
    return index


def index_to_codes(index, levels):
    """Map an integer index back to its normalized code vector."""
    # Convert levels to list if needed
    if not isinstance(levels, (list, tuple)):
        levels = [levels]
    
    # Convert index to code representation
    codes = []
    temp_index = index
    
    # Process from least significant to most significant digit
    for i, level in enumerate(levels):
        digit = temp_index % level
        temp_index //= level
        
        # Convert discrete value to normalized code [-1, 1]
        normalized = (digit / (level - 1)) * 2 - 1
        codes.append(normalized)
    
    # Since we built codes from least to most significant, reverse it
    codes.reverse()
    
    return codes
