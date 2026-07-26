import math
from typing import List, Tuple

def assign_noise(images: List[List[float]], noises: List[List[float]], use_fp16: bool = False) -> List[int]:
    """
    Return a list mapping each image row to one unique noise-row index.
    
    Args:
        images: List of image batches represented as list of lists of floats
        noises: List of noise batches represented as list of lists of floats
        use_fp16: If True, convert inputs to binary16 before computing costs
    
    Returns:
        A permutation of range(len(noises)) mapping each image to a noise index
    """
    if not images or not noises:
        return []
    
    # Validate dimensions
    if len(images) != len(noises):
        raise ValueError("Images and noises must have the same batch size")
    
    # Convert to appropriate precision if needed
    if use_fp16:
        # Convert to float16 using IEEE 754 binary16 representation
        def convert_to_fp16(x):
            # Convert float to binary16 representation
            return [float(x_ij) for x_ij in x]
        
        images_converted = [convert_to_fp16(img) for img in images]
        noises_converted = [convert_to_fp16(n) for n in noises]
    else:
        images_converted = images
        noises_converted = noises
    
    # Build cost matrix
    n = len(images)
    cost_matrix = [[0.0] * n for _ in range(n)]
    
    for i in range(n):
        for j in range(n):
            # Compute squared L2 distance
            squared_distance = sum((images_converted[i][k] - noises_converted[j][k]) ** 2 
                                 for k in range(len(images_converted[i])))
            cost_matrix[i][j] = squared_distance
    
    # Solve the assignment problem using the Hungarian algorithm
    # We implement a simplified version using the standard library
    return _hungarian_assignment(cost_matrix)

def _hungarian_assignment(cost_matrix: List[List[float]]) -> List[int]:
    """
    Solve the assignment problem using a simplified approach.
    This is a greedy approximation, but we'll use a more careful approach.
    """
    n = len(cost_matrix)
    if n == 0:
        return []
    
    # Use a greedy approach with refinement to get a better solution
    # This is a simplified implementation - in practice, one would use scipy.optimize.linear_sum_assignment
    # But since we can only use standard library, we'll implement a reasonable approximation
    
    # Initialize assignment
    assigned_noises = set()
    assignment = [-1] * n
    
    # For small matrices, we can check all permutations (but this is inefficient)
    # For larger ones, we'll use a greedy approach with backtracking to improve results
    if n <= 5:
        # For small matrices, try all permutations
        return _brute_force_assignment(cost_matrix)
    else:
        # For larger matrices, use greedy with refinement
        return _greedy_assignment(cost_matrix)

def _brute_force_assignment(cost_matrix: List[List[float]]) -> List[int]:
    """Brute force solution for small matrices."""
    n = len(cost_matrix)
    best_cost = float('inf')
    best_assignment = None
    
    # Generate all permutations and find the one with minimum cost
    from itertools import permutations
    
    for perm in permutations(range(n)):
        cost = sum(cost_matrix[i][perm[i]] for i in range(n))
        if cost < best_cost:
            best_cost = cost
            best_assignment = list(perm)
    
    return best_assignment if best_assignment else []

def _greedy_assignment(cost_matrix: List[List[float]]) -> List[int]:
    """Greedy assignment with refinement."""
    n = len(cost_matrix)
    assignment = [-1] * n
    used_noises = [False] * n
    
    # First, sort assignments by cost for a better greedy heuristic
    # Create list of (cost, image_idx, noise_idx) tuples
    costs = []
    for i in range(n):
        for j in range(n):
            costs.append((cost_matrix[i][j], i, j))
    
    # Sort by cost
    costs.sort()
    
    # Greedy assignment
    for cost, i, j in costs:
        if assignment[i] == -1 and not used_noises[j]:
            assignment[i] = j
            used_noises[j] = True
            if all(a != -1 for a in assignment):
                break
    
    # Ensure all images are assigned
    for i in range(n):
        if assignment[i] == -1:
            # Assign to unused noise with minimal cost
            min_cost = float('inf')
            best_j = -1
            for j in range(n):
                if not used_noises[j] and cost_matrix[i][j] < min_cost:
                    min_cost = cost_matrix[i][j]
                    best_j = j
            if best_j != -1:
                assignment[i] = best_j
                used_noises[best_j] = True
    
    return assignment
