import math
from typing import List

def quantize(values: List[float], levels: List[int], eps: float = 1e-3) -> List[float]:
    """
    Return normalized FSQ codes, one value per dimension.
    
    Args:
        values: Input values to quantize
        levels: Number of quantization levels per dimension
        eps: Epsilon margin for bounding
        
    Returns:
        Normalized quantized codes in range [-1, 1]
    """
    if len(values) != len(levels):
        raise ValueError("Values and levels must have the same length")
    
    # Apply bounding with epsilon margin
    bounded = []
    for i, (value, level) in enumerate(zip(values, levels)):
        # For even levels, use offset of level/2
        # For odd levels, use offset of (level-1)/2
        if level % 2 == 0:
            offset = level // 2
        else:
            offset = (level - 1) // 2
            
        # Apply bound: [-offset + eps, offset - eps]
        bounded_value = max(-offset + eps, min(offset - eps, value))
        bounded.append(bounded_value)
    
    # Quantize and normalize
    codes = []
    for i, (bounded_val, level) in enumerate(zip(bounded, levels)):
        # For even levels, offset is level/2 and range is [-level/2, level/2 - 1]
        # For odd levels, offset is (level-1)/2 and range is [-(level-1)/2, (level-1)/2]
        if level % 2 == 0:
            offset = level // 2
        else:
            offset = (level - 1) // 2
            
        # Quantize by rounding
        quantized = round(bounded_val)
        
        # Normalize to [-1, 1]
        normalized = quantized / (offset - eps) if offset > 0 else 0.0
        codes.append(normalized)
    
    return codes

def codes_to_index(codes: List[float], levels: List[int]) -> int:
    """
    Map one normalized code vector to its mixed-radix integer index.
    
    Args:
        codes: Normalized codes in range [-1, 1]
        levels: Number of quantization levels per dimension
        
    Returns:
        Integer index representing the mixed-radix code
    """
    if len(codes) != len(levels):
        raise ValueError("Codes and levels must have the same length")
    
    index = 0
    multiplier = 1
    
    # Process from least significant to most significant dimension
    for i in range(len(codes) - 1, -1, -1):
        # Convert normalized code back to quantized value
        level = levels[i]
        if level % 2 == 0:
            offset = level // 2
        else:
            offset = (level - 1) // 2
            
        # De-normalize
        quantized = round(codes[i] * (offset - 1e-3))  # Use small eps instead of eps
        
        # Ensure quantized value is within valid range
        quantized = max(-offset, min(offset - 1, quantized))
        
        # Convert to mixed-radix index
        index += quantized * multiplier
        multiplier *= level
    
    return index

def index_to_codes(index: int, levels: List[int]) -> List[float]:
    """
    Map an integer index back to its normalized code vector.
    
    Args:
        index: Integer index to convert
        levels: Number of quantization levels per dimension
        
    Returns:
        Normalized codes in range [-1, 1]
    """
    codes = []
    temp_index = index
    
    # Process from most significant to least significant dimension
    for i in range(len(levels) - 1, -1, -1):
        level = levels[i]
        
        # Compute quotient and remainder
        if i == len(levels) - 1:
            # For the most significant dimension
            quotient = temp_index // 1
            remainder = temp_index % 1
        else:
            # For other dimensions, we need to check the current level
            remaining_power = 1
            for j in range(i + 1, len(levels)):
                remaining_power *= levels[j]
            
            quotient = temp_index // remaining_power
            remainder = temp_index % remaining_power
        
        # Adjust quotient to match quantized value
        if level % 2 == 0:
            offset = level // 2
        else:
            offset = (level - 1) // 2
            
        # Adjust from [0, level-1] to [-offset, offset-1]
        quantized = quotient - offset
        
        # Clamp to valid range
        quantized = max(-offset, min(offset - 1, quantized))
        
        # Normalize to [-1, 1]
        normalized = quantized / (offset - 1e-3) if offset > 0 else 0.0
        codes.append(normalized)
        
        temp_index = remainder
    
    # Reverse to get the correct order (LSB first in our system)
    codes.reverse()
    return codes
