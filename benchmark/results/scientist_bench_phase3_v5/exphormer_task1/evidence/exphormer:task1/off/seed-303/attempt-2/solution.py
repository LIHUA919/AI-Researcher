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
    
    # Set seed for reproducibility
    random.seed(seed)
    
    # Initialize result list
    edges = []
    
    # Add local edges (both directions)
    for source, target in local_edges:
        edges.append([source, target, "local"])
        edges.append([target, source, "local"])
    
    # Generate expander graph edges
    if num_nodes > 0:
        # Create a list of nodes
        nodes = list(range(num_nodes))
        
        # For each node, create expander_degree connections
        # We'll use a simple approach: for each node, connect to the next 
        # expander_degree nodes in a circular fashion
        for i in range(num_nodes):
            for j in range(expander_degree):
                target = (i + j + 1) % num_nodes
                edges.append([i, target, "expander"])
                edges.append([target, i, "expander"])
    
    # Add global nodes connections
    if num_global_nodes > 0:
        # Global nodes are numbered from num_nodes to num_nodes + num_global_nodes - 1
        global_nodes = list(range(num_nodes, num_nodes + num_global_nodes))
        
        # Connect each global node to every original node in both directions
        for global_node in global_nodes:
            for original_node in range(num_nodes):
                edges.append([global_node, original_node, "global"])
                edges.append([original_node, global_node, "global"])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_edges = []
    for edge in edges:
        edge_tuple = tuple(edge)
        if edge_tuple not in seen:
            seen.add(edge_tuple)
            unique_edges.append(edge)
    
    # Return the result
    return unique_edges

# Example usage:
# edges = build_interaction_graph(
#     num_nodes=5,
#     local_edges=[[0, 1], [1, 2], [2, 3], [3, 4]],
#     expander_degree=3,
#     num_global_nodes=2,
#     seed=303
# )
# print(json.dumps(edges))
