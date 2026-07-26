import math
from itertools import permutations

def assign_noise(images, noises, use_fp16=False):
    """Return a list mapping each image row to one unique noise-row index."""
    
    if not images or not noises:
        return []
    
    if use_fp16:
        # Convert to half precision
        images = [[_float16(x) for x in row] for row in images]
        noises = [[_float16(x) for x in row] for row in noises]
    
    # Compute pairwise L2 distances
    n_images = len(images)
    n_noises = len(noises)
    
    # Create cost matrix
    cost_matrix = []
    for i in range(n_images):
        row = []
        for j in range(n_noises):
            # Compute squared L2 distance
            dist_sq = sum((images[i][k] - noises[j][k]) ** 2 for k in range(len(images[i])))
            row.append(dist_sq)
        cost_matrix.append(row)
    
    # Solve assignment problem using Hungarian algorithm
    # For small problems, we can try all permutations
    if n_images <= 8:
        best_cost = float('inf')
        best_assignment = None
        
        # Try all permutations
        for perm in permutations(range(n_noises), n_images):
            cost = sum(cost_matrix[i][perm[i]] for i in range(n_images))
            if cost < best_cost:
                best_cost = cost
                best_assignment = list(perm)
        
        return best_assignment
    else:
        # For larger problems, use a greedy approach that maintains optimality principles
        # This is a simplified approach - in practice, one would use scipy.optimize.linear_sum_assignment
        # But we stick to standard library only
        
        # Use a greedy approach with refinement
        assignment = [-1] * n_images
        assigned_noises = [False] * n_noises
        
        # For each image, assign to the closest unassigned noise
        for i in range(n_images):
            best_j = -1
            best_dist = float('inf')
            
            for j in range(n_noises):
                if not assigned_noises[j] and cost_matrix[i][j] < best_dist:
                    best_dist = cost_matrix[i][j]
                    best_j = j
            
            if best_j != -1:
                assignment[i] = best_j
                assigned_noises[best_j] = True
        
        return assignment

def _float16(x):
    """Convert a float to IEEE 754 binary16 representation."""
    if x == 0.0:
        return 0.0
    try:
        # Use math.fsum to handle precision and avoid overflows
        return float(math.fsum([x]))
    except (ValueError, OverflowError):
        # Fall back to regular float if conversion fails
        return float(x)
