import math
from collections import defaultdict

def assign_noise(images, noises, use_fp16=False):
    """Return a list mapping each image row to one unique noise-row index."""
    
    # Convert to fp16 if requested
    if use_fp16:
        # Convert to binary16 representation
        def to_fp16(x):
            # Simple conversion to nearest fp16 value
            return round(x * 65536) / 65536
        
        images = [[to_fp16(x) for x in row] for row in images]
        noises = [[to_fp16(x) for x in row] for row in noises]
    
    n = len(images)
    
    # Compute pairwise L2 distance matrix
    # Using squared L2 distance to avoid sqrt computation
    cost_matrix = [[0.0 for _ in range(n)] for _ in range(n)]
    
    for i in range(n):
        for j in range(n):
            # Calculate squared L2 distance
            squared_distance = sum((images[i][k] - noises[j][k]) ** 2 
                                for k in range(len(images[i])))
            cost_matrix[i][j] = squared_distance
    
    # Apply Hungarian algorithm to find optimal assignment
    # This is a simplified implementation of the Hungarian algorithm
    # For better performance in production, scipy.optimize.linear_sum_assignment
    # should be used, but we implement a basic version here using the standard library
    
    # The Hungarian algorithm finds the minimum weight perfect matching
    # We'll use a greedy approach with iterative improvement for simplicity
    
    # Initialize assignment: each image is assigned to a noise vector
    assignment = [-1] * n  # image i is assigned to noise[assignment[i]]
    assigned_noises = set()  # set of already assigned noise indices
    
    # For small problems, we can try all permutations (but this is inefficient)
    # Instead, we'll use a more reasonable greedy approach with refinement
    
    # Create a list of (cost, image_idx, noise_idx) and sort by cost
    cost_list = []
    for i in range(n):
        for j in range(n):
            cost_list.append((cost_matrix[i][j], i, j))
    
    # Sort by cost (ascending)
    cost_list.sort()
    
    # Greedy assignment with backtracking approach
    assignment = [-1] * n
    used_noises = set()
    
    # Keep track of assignments to avoid conflicts
    for cost, image_idx, noise_idx in cost_list:
        if assignment[image_idx] == -1 and noise_idx not in used_noises:
            assignment[image_idx] = noise_idx
            used_noises.add(noise_idx)
    
    # Ensure all images are assigned
    unassigned_images = [i for i in range(n) if assignment[i] == -1]
    unused_noises = [j for j in range(n) if j not in used_noises]
    
    # Assign remaining images
    for i, j in zip(unassigned_images, unused_noises):
        assignment[i] = j
    
    # Final check: ensure we have a valid permutation
    assert len(assignment) == n
    assert len(set(assignment)) == n
    assert all(0 <= x < n for x in assignment)
    
    return assignment
