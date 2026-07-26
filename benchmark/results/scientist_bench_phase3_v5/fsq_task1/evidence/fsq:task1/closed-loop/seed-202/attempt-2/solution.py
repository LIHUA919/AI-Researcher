def quantize(values, levels, eps=1e-3):
    """Return normalized FSQ codes, one value per dimension."""
    import math
    import torch
    
    # Convert to tensor if needed
    if not isinstance(values, torch.Tensor):
        values = torch.tensor(values, dtype=torch.float32)
    if not isinstance(levels, torch.Tensor):
        levels = torch.tensor(levels, dtype=torch.int32)
    
    # For each dimension, apply the bounding function
    bound_values = []
    for i, (value, level) in enumerate(zip(values, levels)):
        # Calculate floor(L/2) for this dimension
        half_level = level // 2
        
        # Apply bounding: floor(L/2) * tanh(z)
        bounded = half_level * torch.tanh(value)
        
        # Clip to ensure we're within bounds
        bounded = torch.clamp(bounded, -half_level + eps, half_level - eps)
        
        # Round to nearest integer
        rounded = torch.round(bounded)
        
        # Normalize to [-1, 1]: (rounded + floor(L/2)) / floor(L/2) - 1
        normalized = (rounded + half_level) / half_level - 1.0
        
        bound_values.append(normalized)
    
    return torch.stack(bound_values)


def codes_to_index(codes, levels):
    """Map one normalized code vector to its mixed-radix integer index."""
    import torch
    
    # Convert to tensors if needed
    if not isinstance(codes, torch.Tensor):
        codes = torch.tensor(codes, dtype=torch.float32)
    if not isinstance(levels, torch.Tensor):
        levels = torch.tensor(levels, dtype=torch.int32)
    
    # Handle case where codes might be a scalar tensor
    if codes.dim() == 0:
        codes = codes.unsqueeze(0)
    if levels.dim() == 0:
        levels = levels.unsqueeze(0)
    
    if codes.shape[0] != levels.shape[0]:
        raise ValueError("Codes and levels must have the same number of dimensions")
    
    # Convert codes back to discrete levels
    # Reversing the normalization: discrete = (code + 1) * half_level - half_level
    index = 0
    multiplier = 1
    
    # Process dimensions from least to most significant (as specified)
    for i in range(len(levels) - 1, -1, -1):
        half_level = levels[i] // 2
        
        # Convert normalized code back to discrete value
        discrete_value = torch.round((codes[i] + 1.0) * half_level - half_level)
        discrete_value = torch.clamp(discrete_value, 0, levels[i] - 1)
        
        index += discrete_value.item() * multiplier
        multiplier *= levels[i]
    
    return index


def index_to_codes(index, levels):
    """Map an integer index back to its normalized code vector."""
    import torch
    
    # Convert levels to tensor if needed
    if not isinstance(levels, torch.Tensor):
        levels = torch.tensor(levels, dtype=torch.int32)
    
    # Convert index to integer if needed
    if isinstance(index, torch.Tensor):
        index = index.item()
    
    # Decompose index into mixed-radix representation
    codes = []
    temp_index = index
    
    # Process dimensions from least to most significant  
    for i in range(len(levels) - 1, -1, -1):
        level = levels[i]
        half_level = level // 2
        
        # Extract the coefficient for this dimension
        coeff = temp_index % level
        temp_index //= level
        
        # Convert back to normalized format
        # Original: normalized = (rounded + half_level) / half_level - 1
        # Reverse to get discrete: discrete = (normalized + 1) * half_level - half_level
        # But we want to reconstruct the original normalized value
        # So: normalized = (coeff - half_level) / half_level  # Since coeff is 0 to L-1
        normalized = (coeff - half_level) / half_level
        
        codes.append(normalized)
    
    # Since we built codes from MSB to LSB, we need to reverse for right ordering
    codes.reverse()
    
    return torch.tensor(codes, dtype=torch.float32)
