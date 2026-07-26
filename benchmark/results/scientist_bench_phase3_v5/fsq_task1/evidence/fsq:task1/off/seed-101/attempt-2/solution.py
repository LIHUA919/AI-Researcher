def quantize(values, levels, eps=1e-3):
    """Return normalized FSQ codes, one value per dimension."""
    # Convert inputs to lists for easier processing
    values = list(values)
    levels = list(levels)
    
    # For each dimension, perform quantization
    codes = []
    for i, (value, level) in enumerate(zip(values, levels)):
        # Apply bounding: bound to [-L/2, L/2] with epsilon margin
        # Using the formula f(z) = floor(L/2) * tanh(z)
        bound = level // 2
        bounded = bound * (value / (abs(value) + eps) if abs(value) > eps else 0.0)
        # Clamp to ensure we stay within bounds
        bounded = max(-bound, min(bound, bounded))
        
        # Round to nearest integer
        rounded = round(bounded)
        
        # Normalize to [-1, 1]
        normalized = rounded / bound if bound != 0 else 0.0
        
        codes.append(normalized)
    
    return codes

def codes_to_index(codes, levels):
    """Map one normalized code vector to its mixed-radix integer index."""
    # Convert inputs to lists
    codes = list(codes)
    levels = list(levels)
    
    # Mixed-radix conversion with first dimension being least significant
    index = 0
    multiplier = 1
    
    # Process dimensions from least significant to most significant
    for i in range(len(codes)):
        # Convert normalized code back to discrete value
        bound = levels[i] // 2
        if bound == 0:
            discrete_val = 0
        else:
            # Normalize back from [-1, 1] to [-bound, bound]
            discrete_val = round(codes[i] * bound)
            # Clamp to valid range for this level
            discrete_val = max(-bound, min(bound, discrete_val))
        
        index += discrete_val * multiplier
        multiplier *= levels[i]
    
    return index

def index_to_codes(index, levels):
    """Map an integer index back to its normalized code vector."""
    # Convert levels to list
    levels = list(levels)
    
    # Convert index to mixed-radix representation
    codes = []
    remaining = index
    
    for i, level in enumerate(levels):
        bound = level // 2
        if bound == 0:
            codes.append(0.0)
            continue
            
        # Get the value for this dimension
        value = remaining % level
        remaining //= level
        
        # Adjust for symmetric range [-bound, bound]
        if value > bound:
            value -= level
        
        # Normalize to [-1, 1]
        normalized = value / bound if bound != 0 else 0.0
        codes.append(normalized)
    
    return codes
