import math
from scipy.optimize import linear_sum_assignment
from typing import List

def assign_noise(images: List[List[float]], noises: List[List[float]], use_fp16: bool = False) -> List[int]:
    """
    Return a list mapping each image row to one unique noise-row index.
    
    Args:
        images: Batch of images as list of lists of floats
        noises: Batch of noise as list of lists of floats
        use_fp16: If True, convert inputs to fp16 before computing distances
    
    Returns:
        A permutation of range(len(noises)) indicating optimal assignment
    """
    if not images or not noises:
        return []
    
    if len(images) != len(noises):
        raise ValueError("Images and noises must have the same batch size")
    
    # Convert to appropriate precision if needed
    if use_fp16:
        # Convert to float16 and back to float32 for computation
        def to_fp16(x):
            return [float(x_i) for x_i in x]
        
        # Create copies with fp16 precision
        img_fp16 = [to_fp16(img) for img in images]
        noise_fp16 = [to_fp16(n) for n in noises]
    else:
        img_fp16 = images
        noise_fp16 = noises
    
    # Compute pairwise L2 distances
    n_images = len(img_fp16)
    n_noises = len(noise_fp16)
    
    # Create cost matrix
    cost_matrix = []
    for i in range(n_images):
        row = []
        for j in range(n_noises):
            # Compute squared L2 distance
            distance_squared = 0.0
            for k in range(len(img_fp16[i])):
                diff = img_fp16[i][k] - noise_fp16[j][k]
                distance_squared += diff * diff
            row.append(distance_squared)
        cost_matrix.append(row)
    
    # Use scipy's linear sum assignment (Hungarian algorithm)
    # This returns row_indices and col_indices
    row_indices, col_indices = linear_sum_assignment(cost_matrix)
    
    # Create mapping from image indices to noise indices
    assignment = [-1] * n_images
    for i, j in zip(row_indices, col_indices):
        assignment[i] = j
    
    # Verify it's a valid permutation
    if len(set(assignment)) != len(assignment) or set(assignment) != set(range(n_noises)):
        # Fallback for edge cases - use greedy approach
        assignment = [0] * n_images
        used_indices = set()
        for i in range(n_images):
            best_j = -1
            best_cost = float('inf')
            for j in range(n_noises):
                if j not in used_indices and cost_matrix[i][j] < best_cost:
                    best_cost = cost_matrix[i][j]
                    best_j = j
            if best_j != -1:
                assignment[i] = best_j
                used_indices.add(best_j)
    
    return assignment
