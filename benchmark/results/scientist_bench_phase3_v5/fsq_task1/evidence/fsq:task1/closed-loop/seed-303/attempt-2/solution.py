def quantize(values, levels, eps=1e-3):
    """Return normalized FSQ codes, one value per dimension."""
    import math
    
    # Clamp values to prevent numerical issues
    values = [max(-1 + eps, min(1 - eps, v)) for v in values]
    
    # Create normalized codes
    codes = []
    for i, (val, level) in enumerate(zip(values, levels)):
        # Apply tanh for bounding (but already clamped)
        bounded = math.tanh(val) if abs(val) < 10 else (1 if val > 0 else -1)
        
        # Adjust for even/odd levels
        offset = 0.5 if level % 2 == 0 else 0.0
        
        # Scale to [0, L-1] range and quantize
        scaled = (bounded + 1) / 2 * (level - 1) + offset
        quantized = round(scaled)
        
        # Clamp to valid range
        quantized = max(0, min(level - 1, quantized))
        
        # Convert back to [-1, 1] range
        normalized = 2 * quantized / (level - 1) - 1
        
        codes.append(normalized)
    
    return codes


def codes_to_index(codes, levels):
    """Map one normalized code vector to its mixed-radix integer index."""
    index = 0
    multiplier = 1
    
    # Process from least significant to most significant dimension
    for code, level in zip(codes, levels):
        # Convert normalized code back to integer code
        # normalized = 2 * code_int / (level - 1) - 1
        # code_int = ((normalized + 1) * (level - 1)) / 2
        
        # Convert normalized code to integer (reverse of normalization)
        code_int = round(((code + 1) / 2) * (level - 1))
        # Ensure it's within bounds
        code_int = max(0, min(level - 1, code_int))
        
        index += code_int * multiplier
        multiplier *= level
    
    return index


def index_to_codes(index, levels):
    """Map an integer index back to its normalized code vector."""
    codes = []
    remaining = index
    
    # Convert from mixed-radix to codes
    for level in levels:
        code_int = remaining % level
        remaining //= level
        
        # Convert integer code to normalized code in [-1, 1]
        normalized = 2 * code_int / (level - 1) - 1
        codes.append(normalized)
    
    return codes
