import math
import functools

def quantize(values, levels, eps=1e-3):
    """Return normalized FSQ codes, one value per dimension."""
    # Convert inputs to lists for easier handling
    if not isinstance(values, (list, tuple)):
        values = [values]
    if not isinstance(levels, (list, tuple)):
        levels = [levels] * len(values) if len(values) > 0 else []
    
    # Ensure same length
    if len(values) != len(levels):
        raise ValueError("values and levels must have the same length")
    
    # Apply bounding and quantization
    result = []
    for i, (value, level) in enumerate(zip(values, levels)):
        # Bound the value with epsilon margin
        bound_min = -1 + eps
        bound_max = 1 - eps
        bounded_value = max(bound_min, min(bound_max, float(value)))
        
        # Apply tanh to compress range and adjust to [0, L-1]
        # f(z) = floor(L/2) * tanh(z)
        offset = level // 2
        scaled_value = offset * math.tanh(bounded_value)
        
        # Project to [0, L-1] range
        projected_value = (scaled_value + offset) / offset
        
        # Round to nearest integer
        rounded_value = round(projected_value)
        
        # Clamp to valid range [0, L-1]
        clamped_value = max(0, min(level - 1, rounded_value))
        
        # Normalize to [-1, 1]
        normalized_value = (2.0 * clamped_value / (level - 1)) - 1.0
        
        result.append(normalized_value)
    
    return result if len(result) > 1 else result[0] if result else None

def codes_to_index(codes, levels):
    """Map one normalized code vector to its mixed-radix integer index."""
    if not isinstance(codes, (list, tuple)):
        codes = [codes]
    if not isinstance(levels, (list, tuple)):
        levels = [levels] * len(codes) if len(codes) > 0 else []
    
    if len(codes) != len(levels):
        raise ValueError("codes and levels must have the same length")
    
    # Convert each normalized code back to integer code
    int_codes = []
    for i, (code, level) in enumerate(zip(codes, levels)):
        # Convert back from [-1, 1] to [0, level-1]
        int_code = round((code + 1.0) * (level - 1) / 2.0)
        # Clamp to [0, level-1]
        int_code = max(0, min(level - 1, int_code))
        int_codes.append(int_code)
    
    # Convert to mixed-radix index (LSB first)
    index = 0
    base = 1
    for int_code, level in zip(int_codes, levels):
        index += int_code * base
        base *= level
    
    return index

def index_to_codes(index, levels):
    """Map an integer index back to its normalized code vector."""
    if not isinstance(levels, (list, tuple)):
        levels = [levels] * (len(levels) if hasattr(levels, '__len__') else 1) if len(levels) > 0 else []
    
    # Convert index to mixed-radix representation
    codes = []
    temp_index = index
    for level in levels:
        codes.append(temp_index % level)
        temp_index //= level
    
    # Convert integer codes to normalized [-1, 1] codes
    normalized_codes = []
    for i, (code, level) in enumerate(zip(codes, levels)):
        # Convert [0, level-1] to [-1, 1]
        normalized = (2.0 * code / (level - 1)) - 1.0
        normalized_codes.append(normalized)
    
    # Return in reverse order (MSB first to LSB first)
    return normalized_codes[::-1] if normalized_codes else []
