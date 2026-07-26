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
    
    edges = []
    
    # Process local edges (undirected, so emit both directions)
    for source, target in local_edges:
        edges.append([source, target, "local"])
        edges.append([target, source, "local"])
    
    # Generate expander graph edges
    # Create a d-regular expander graph using random permutations
    if num_nodes > 0:
        # Create a list of nodes for each expander
        node_list = list(range(num_nodes))
        
        # For each node, we'll connect it to expander_degree other nodes
        # We'll create a random permutation for each node, but ensure no self-loops
        for i in range(num_nodes):
            # Generate random neighbors for this node
            neighbors = random.sample(node_list, min(expander_degree, num_nodes))
            
            # Remove self-loop if present
            neighbors = [n for n in neighbors if n != i]
            
            # If we don't have enough neighbors, try to add more from remaining nodes
            while len(neighbors) < expander_degree:
                # Find a node that's not already a neighbor and not self
                candidates = [n for n in node_list if n != i and n not in neighbors]
                if candidates:
                    neighbors.append(random.choice(candidates))
                else:
                    break
            
            # Add the edges (both directions)
            for neighbor in neighbors:
                # Only add edge if it doesn't already exist
                if not any(e[0] == i and e[1] == neighbor for e in edges):
                    edges.append([i, neighbor, "expander"])
                    edges.append([neighbor, i, "expander"])
    
    # Add global nodes and connect them to all original nodes
    global_start = num_nodes
    global_nodes = list(range(global_start, global_start + num_global_nodes))
    
    # Connect each global node to every original node (both directions)
    for global_node in global_nodes:
        for original_node in range(num_nodes):
            edges.append([global_node, original_node, "global"])
            edges.append([original_node, global_node, "global"])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_edges = []
    for edge in edges:
        edge_key = tuple(edge)
        if edge_key not in seen:
            seen.add(edge_key)
            unique_edges.append(edge)
    
    # Sort edges for deterministic output
    unique_edges.sort(key=lambda x: (x[0], x[1], x[2]))
    
    return unique_edges
