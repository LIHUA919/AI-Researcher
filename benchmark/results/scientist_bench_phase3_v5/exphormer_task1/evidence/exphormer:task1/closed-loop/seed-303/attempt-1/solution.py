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
    for src, dst in local_edges:
        edges.append([src, dst, "local"])
        edges.append([dst, src, "local"])
    
    # Generate expander graph edges
    if num_nodes > 0:
        # Create a list of nodes
        nodes = list(range(num_nodes))
        
        # For each node, create expander_degree connections to other nodes
        # Using a simple approach: for each node, randomly select expander_degree
        # other nodes to connect to (without replacement)
        
        # Create a list of all possible connections for the expander
        expander_edges = []
        
        # For each node, randomly select expander_degree other nodes
        for node in nodes:
            # Get all other nodes
            other_nodes = [n for n in nodes if n != node]
            
            # Sample expander_degree nodes without replacement
            if len(other_nodes) >= expander_degree:
                selected_nodes = random.sample(other_nodes, expander_degree)
            else:
                # If not enough nodes, sample with replacement
                selected_nodes = [random.choice(other_nodes) for _ in range(expander_degree)]
            
            # Add both directions for each connection
            for neighbor in selected_nodes:
                expander_edges.append([node, neighbor, "expander"])
                expander_edges.append([neighbor, node, "expander"])
        
        # Remove duplicates and add edges
        unique_edges = []
        seen = set()
        for edge in expander_edges:
            # Create a tuple to check uniqueness
            edge_tuple = tuple(edge)
            if edge_tuple not in seen:
                seen.add(edge_tuple)
                unique_edges.append(edge)
        
        edges.extend(unique_edges)
    
    # Add global edges (connect each global node to each original node)
    if num_global_nodes > 0 and num_nodes > 0:
        global_nodes_start = num_nodes
        global_nodes_end = num_nodes + num_global_nodes
        
        # For each global node, connect to all original nodes
        for global_node in range(global_nodes_start, global_nodes_end):
            for original_node in range(num_nodes):
                edges.append([global_node, original_node, "global"])
                edges.append([original_node, global_node, "global"])
    
    # Remove duplicates and ensure no self-loops
    # Convert to tuples for deduplication
    seen = set()
    unique_edges = []
    
    for edge in edges:
        src, dst, edge_type = edge
        # Don't add self-loops
        if src == dst:
            continue
        # Create a tuple for the edge
        edge_key = (src, dst, edge_type)
        if edge_key not in seen:
            seen.add(edge_key)
            unique_edges.append(edge)
    
    # Sort for consistent output
    unique_edges.sort()
    
    return unique_edges
