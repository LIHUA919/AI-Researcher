def quantize(values, levels, eps=1e-3):
    """Return normalized FSQ codes, one value per dimension."""
    # Convert inputs to lists for easier manipulation
    values = list(values)
    levels = list(levels)
    
    # Ensure the number of values matches the number of levels
    assert len(values) == len(levels), "Number of values must match number of levels"
    
    # Apply bounding function with epsilon margin and even-level offset
    # For even levels, we want to center around 0 and avoid edge issues
    # f(z) = floor(L/2) * tanh(z) where L is the number of levels
    bounded_values = []
    for i, (value, level) in enumerate(zip(values, levels)):
        # Calculate the bound based on levels (even offset)
        bound = level // 2
        # Apply the bounding function: bound * tanh(value)
        bounded = bound * (value / (abs(value) + eps) if value != 0 else 0)  # Simple bounding
        bounded_values.append(bounded)
    
    # Round to nearest integer and ensure within bounds
    quantized_values = []
    for i, (bounded, level) in enumerate(zip(bounded_values, levels)):
        # Round bounded value to nearest integer
        rounded = round(bounded)
        # Clamp to valid range [-level//2, level//2 - 1] for even levels
        # For odd levels, range is [-level//2, level//2] 
        if level % 2 == 0:
            clamped = max(-level // 2, min(level // 2 - 1, rounded))
        else:
            clamped = max(-level // 2, min(level // 2, rounded))
        quantized_values.append(clamped)
    
    # Normalize the quantized values to [-1, 1]
    normalized = []
    for i, (quantized, level) in enumerate(zip(quantized_values, levels)):
        # Normalize to [-1, 1]
        if level % 2 == 0:
            # Even case: range is [-level//2, level//2 - 1] so normalized is [-1, 1]  
            normalized_value = quantized / (level // 2 - 1) if level > 2 else 0.0
        else:
            # Odd case: range is [-level//2, level//2] so normalized is [-1, 1]
            normalized_value = quantized / (level // 2) if level > 0 else 0.0
        normalized.append(normalized_value)
    
    return normalized


def codes_to_index(codes, levels):
    """Map one normalized code vector to its mixed-radix integer index."""
    # Convert inputs to lists
    codes = list(codes)
    levels = list(levels)
    
    # Ensure matching lengths
    assert len(codes) == len(levels), "Number of codes must match number of levels"
    
    # Convert normalized codes back to discrete values
    discrete_codes = []
    for i, (code, level) in enumerate(zip(codes, levels)):
        # Normalize back to discrete range
        if level % 2 == 0:
            discrete_value = int(code * (level // 2 - 1)) if level > 2 else 0
            # Clamp to valid range
            discrete_value = max(-level // 2, min(level // 2 - 1, discrete_value))
        else:
            discrete_value = int(code * (level // 2)) if level > 0 else 0
            # Clamp to valid range
            discrete_value = max(-level // 2, min(level // 2, discrete_value))
        discrete_codes.append(discrete_value)
    
    # Build mixed-radix index, with first dimension as LSB
    index = 0
    multiplier = 1
    
    for i in range(len(discrete_codes)):
        # Reverse the indexing order
        code = discrete_codes[len(discrete_codes) - 1 - i]
        level = levels[len(levels) - 1 - i]
        
        # Adjust code to be in [0, level-1] range
        if level % 2 == 0:
            adjusted_code = code + level // 2  # Shift to [0, level-1]
        else:
            adjusted_code = code + level // 2  # Shift to [0, level-1]
        
        index += adjusted_code * multiplier
        multiplier *= level
    
    return index


def index_to_codes(index, levels):
    """Map an integer index back to its normalized code vector."""
    # Convert levels to list
    levels = list(levels)
    
    # Convert index to mixed-radix representation in reverse order
    # (LSB first)
    codes = []
    temp_index = index
    
    for level in reversed(levels):  # Process in reverse (LSB first)
        if level <= 0:
            codes.append(0) 
            continue
            
        code = temp_index % level
        temp_index //= level
        
        # Shift back to [-level//2, level//2 - 1] for even levels
        # Or [-level//2, level//2] for odd levels
        if level % 2 == 0:
            # For even: range is [0, level-1], shift to [-level//2, level//2 - 1]
            code -= level // 2
        else:
            # For odd: range is [0, level-1], shift to [-level//2, level//2]
            code -= level // 2
            
        codes.append(code)
    
    # Reverse to get proper order (MSB first)
    codes.reverse()
    
    # Normalize values
    normalized = []
    for i, (code, level) in enumerate(zip(codes, levels)):
        # Normalize to [-1, 1]
        if level % 2 == 0:
            normalized_value = code / (level // 2 - 1) if level > 2 else 0.0
        else:
            normalized_value = code / (level // 2) if level > 0 else 0.0
        normalized.append(normalized_value)
    
    return normalized
