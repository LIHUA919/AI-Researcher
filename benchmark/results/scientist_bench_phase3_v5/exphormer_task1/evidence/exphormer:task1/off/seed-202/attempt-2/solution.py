import random
import json

def build_interaction_graph(
    num_nodes,
    local_edges,
    expander_degree,
    num_global_nodes,
    seed,
):
    """Return directed, typed attention edges."""
    random.seed(seed)
    
    # Initialize result list
    edges = []
    
    # Add local edges (both directions)
    for src, dst in local_edges:
        edges.append([src, dst, "local"])
        edges.append([dst, src, "local"])
    
    # Generate expander graph edges
    # Create a d-regular expander graph
    if num_nodes > 0:
        # Create permutation-based expander graph
        # For each node, we'll connect it to expander_degree neighbors
        # We use a simple cyclic permutation approach
        
        # Create adjacency list for expander edges
        expander_adjacency = [[] for _ in range(num_nodes)]
        
        # Generate permutations for expander edges
        for i in range(num_nodes):
            # Create a set of neighbors for node i
            neighbors = set()
            while len(neighbors) < expander_degree:
                # Generate a random neighbor based on seed and node id
                # Using a hash-like approach for reproducibility
                neighbor = (i * 1103515245 + 12345 + seed * 1000 + len(neighbors)) % num_nodes
                if neighbor != i and neighbor not in neighbors:
                    neighbors.add(neighbor)
            
            expander_adjacency[i] = list(neighbors)
        
        # Add expander edges in both directions
        for i in range(num_nodes):
            for neighbor in expander_adjacency[i]:
                if i < neighbor:  # Avoid duplicates
                    edges.append([i, neighbor, "expander"])
                    edges.append([neighbor, i, "expander"])
    
    # Add global node connections
    global_start = num_nodes
    for i in range(num_nodes):
        for g in range(num_global_nodes):
            global_node = global_start + g
            edges.append([i, global_node, "global"])
            edges.append([global_node, i, "global"])
    
    # Remove duplicates and sort for consistent output
    edge_set = set()
    unique_edges = []
    
    for edge in edges:
        # Create a canonical representation for the edge to detect duplicates
        src, dst, etype = edge
        edge_key = (min(src, dst), max(src, dst), etype)
        if edge_key not in edge_set:
            edge_set.add(edge_key)
            unique_edges.append(edge)
    
    # Sort edges for deterministic output
    unique_edges.sort(key=lambda x: (x[0], x[1], x[2]))
    
    return unique_edges
