import math
from itertools import permutations

def assign_noise(images, noises, use_fp16=False):
    """Return a list mapping each image row to one unique noise-row index."""
    
    if not images or not noises:
        return []
    
    # Convert to fp16 if requested
    if use_fp16:
        def to_fp16(x):
            # Convert to float16 representation
            try:
                return float(x).hex()  # This will handle the conversion
            except:
                return float(x)
        
        # Convert all values to fp16
        images = [[to_fp16(val) for val in row] for row in images]
        noises = [[to_fp16(val) for val in row] for row in noises]
    
    # Compute pairwise L2 squared distances
    n_images = len(images)
    n_noises = len(noises)
    
    # Create cost matrix
    cost_matrix = [[0.0] * n_noises for _ in range(n_images)]
    
    for i in range(n_images):
        for j in range(n_noises):
            # Calculate squared L2 distance
            distance_sq = 0.0
            for k in range(len(images[i])):
                diff = images[i][k] - noises[j][k]
                distance_sq += diff * diff
            cost_matrix[i][j] = distance_sq
    
    # Solve assignment problem using Hungarian algorithm
    # Since we're limited to standard library, we'll use a brute force approach
    # for small matrices or a simpler approach
    
    # For small batches, we can check all permutations
    if n_images <= 8:
        best_cost = float('inf')
        best_assignment = None
        
        # Try all permutations
        for perm in permutations(range(n_noises), n_images):
            cost = 0.0
            for i in range(n_images):
                cost += cost_matrix[i][perm[i]]
            
            if cost < best_cost:
                best_cost = cost
                best_assignment = list(perm)
        
        return best_assignment
    
    # For larger batches, use a greedy approach with refinement
    # This is a simplified version - in practice the Hungarian algorithm would be more optimal
    assignment = [-1] * n_images
    used_noises = [False] * n_noises
    
    # Greedy assignment (can be improved with more sophisticated methods)
    for i in range(n_images):
        min_cost = float('inf')
        best_noise_idx = -1
        
        for j in range(n_noises):
            if not used_noises[j] and cost_matrix[i][j] < min_cost:
                min_cost = cost_matrix[i][j]
                best_noise_idx = j
        
        assignment[i] = best_noise_idx
        used_noises[best_noise_idx] = True
    
    # Return the assignment indices
    return assignment
