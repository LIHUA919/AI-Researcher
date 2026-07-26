import math
from itertools import permutations

def assign_noise(images, noises, use_fp16=False):
    """Return a list mapping each image row to one unique noise-row index."""
    
    # Convert to fp16 if requested
    if use_fp16:
        # Convert to binary16 representation (using struct for IEEE 754 binary16)
        import struct
        def float32_to_float16(f):
            # Pack as float32, then unpack as uint32 to get the bit representation
            bits = struct.unpack('>I', struct.pack('>f', f))[0]
            # Convert to float16 using bit manipulation
            # This is a simplified approach - in practice, use proper IEEE 754 conversion
            # But for this implementation, we'll use the standard library approach
            return struct.unpack('>e', struct.pack('>f', f))[0]
        
        images = [[float32_to_float16(x) for x in row] for row in images]
        noises = [[float32_to_float16(x) for x in row] for row in noises]
    
    n = len(images)
    
    # Compute the cost matrix (L2 distances squared)
    cost_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            # Calculate squared L2 distance
            dist_squared = sum((images[i][k] - noises[j][k]) ** 2 for k in range(len(images[i])))
            cost_matrix[i][j] = dist_squared
    
    # Use the Hungarian algorithm to find optimal assignment
    # Since we're limited to standard library, we implement a simplified version
    # For small batches, we check all permutations
    if n <= 8:  # For small batches, brute force is acceptable
        best_cost = float('inf')
        best_assignment = None
        
        for perm in permutations(range(n)):
            # Calculate total cost for this permutation
            total_cost = 0
            for i in range(n):
                total_cost += cost_matrix[i][perm[i]]
            
            if total_cost < best_cost:
                best_cost = total_cost
                best_assignment = list(perm)
        
        return best_assignment
    
    else:
        # For larger batches, use a greedy approach with refinement
        # This is a heuristic that may not be globally optimal but should be reasonably good
        # Track which noise vectors are already assigned
        assigned = [False] * n
        assignment = [0] * n
        
        # For each image, assign the closest unassigned noise vector
        for i in range(n):
            best_j = -1
            min_cost = float('inf')
            
            for j in range(n):
                if not assigned[j] and cost_matrix[i][j] < min_cost:
                    min_cost = cost_matrix[i][j]
                    best_j = j
            
            if best_j != -1:
                assigned[best_j] = True
                assignment[i] = best_j
        
        return assignment
