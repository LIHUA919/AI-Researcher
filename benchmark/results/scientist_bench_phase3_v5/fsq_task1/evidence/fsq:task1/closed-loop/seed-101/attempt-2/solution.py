def quantize(values, levels, eps=1e-3):
    """Return normalized FSQ codes, one value per dimension."""
    import math
    
    # Convert to list for easier manipulation
    values = list(values)
    levels = list(levels)
    
    # Ensure levels are even for offset calculation
    normalized_codes = []
    
    for i, (value, level) in enumerate(zip(values, levels)):
        # Calculate the offset for even levels
        offset = 0 if level % 2 == 1 else 0.5
        
        # Apply bounding with epsilon margin
        bound_value = max(-1 + eps, min(1 - eps, value))
        
        # Apply the bounding transformation: floor(L/2) * tanh(z)
        # For simplicity, we'll use a linear mapping approach that's more
        # consistent with the context, but preserving the formula structure
        level_half = level // 2
        bounded = level_half * math.tanh(bound_value)
        
        # Quantize by rounding
        quantized = round(bounded)
        
        # Normalize to [-1, 1] range
        normalized = quantized / level_half if level_half > 0 else 0
        
        normalized_codes.append(normalized)
    
    return normalized_codes


def codes_to_index(codes, levels):
    """Map one normalized code vector to its mixed-radix integer index."""
    # Convert to lists if they aren't already
    codes = list(codes)
    levels = list(levels)
    
    # Mixed-radix conversion - least-significant digit first
    index = 0
    multiplier = 1
    
    for i, (code, level) in enumerate(zip(codes, levels)):
        # Undo normalization to get the actual quantized value
        level_half = level // 2
        if level % 2 == 0:
            # Even level case
            quantized = round(code * level_half)
            # Clamp to valid range [0, level-1] for even level case
            quantized = max(0, min(level - 1, quantized))
        else:
            # Odd level case - center at 0
            quantized = round(code * level_half)
            # Clamp to valid range [0, level-1] for odd level case  
            quantized = max(0, min(level - 1, quantized))
            
        index += quantized * multiplier
        multiplier *= level
    
    return index


def index_to_codes(index, levels):
    """Map an integer index back to its normalized code vector."""
    # Convert to lists if they aren't already
    levels = list(levels)
    
    codes = []
    temp_index = index
    
    # Process each dimension, least-significant first
    for level in levels:
        # Extract the component for this level
        component = temp_index % level
        temp_index //= level
        
        # Normalize to [-1, 1]
        level_half = level // 2
        if level % 2 == 0:
            # Even level case
            normalized = component / level_half if level_half > 0 else 0
        else:
            # Odd level case - center at 0, so we adjust for the range
            # The actual code is in range [0, level-1]
            normalized = (component - level_half) / level_half if level_half > 0 else 0
            
        codes.append(normalized)
    
    return codes
