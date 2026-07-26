import random
from collections import defaultdict

def build_interaction_graph(
    num_nodes,
    local_edges,
    expander_degree,
    num_global_nodes,
    seed,
):
    """Return directed, typed attention edges."""
    
    # Set seed for reproducibility
    random.seed(seed)
    
    edges = []
    
    # Process local edges - make them bidirectional with "local" type
    for src, dst in local_edges:
        if src != dst:  # Avoid self-loops
            edges.append([src, dst, "local"])
            edges.append([dst, src, "local"])
    
    # Generate expander graph edges
    # Create a d-regular expander graph
    if num_nodes > 0:
        # For each node, create expander_degree connections
        # Use a simple method: for each node, connect to nodes based on a permutation
        node_order = list(range(num_nodes))
        random.shuffle(node_order)
        
        # Create a mapping from node to its neighbors
        neighbors = defaultdict(list)
        
        # Create expander edges
        for i in range(num_nodes):
            for j in range(expander_degree):
                # Connect node i to node (i + j * step) % num_nodes
                # Use a fixed step to avoid creating too many duplicate edges
                step = (i * expander_degree + j) % num_nodes if num_nodes > 0 else 1
                neighbor = (i + step) % num_nodes
                if neighbor != i and len(neighbors[i]) < expander_degree:
                    neighbors[i].append(neighbor)
        
        # Add expander edges (bidirectional)
        for src in range(num_nodes):
            for dst in neighbors[src]:
                if src < dst:  # Avoid duplicates
                    edges.append([src, dst, "expander"])
                    edges.append([dst, src, "expander"])
    
    # Add global nodes and connections
    if num_global_nodes > 0:
        # Add global nodes at indices [num_nodes, ..., num_nodes + num_global_nodes - 1]
        global_start = num_nodes
        
        # Connect each global node to every original node (bidirectional)
        for global_node in range(global_start, global_start + num_global_nodes):
            for original_node in range(num_nodes):
                edges.append([global_node, original_node, "global"])
                edges.append([original_node, global_node, "global"])
    
    # Remove duplicates while maintaining order
    edge_set = set()
    unique_edges = []
    for edge in edges:
        edge_key = tuple(edge)
        if edge_key not in edge_set:
            edge_set.add(edge_key)
            unique_edges.append(edge)
    
    return unique_edges
