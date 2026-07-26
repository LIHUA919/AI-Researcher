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
    
    # Store all edges to avoid duplicates
    edge_set = set()
    edges = []
    
    # Helper function to add edge if not duplicate
    def add_edge(source, target, edge_type):
        # Create a tuple representing the edge
        edge = (source, target, edge_type)
        # Add both directions for undirected edges
        if edge_type == "local" or edge_type == "expander":
            reverse_edge = (target, source, edge_type)
            if edge not in edge_set and reverse_edge not in edge_set:
                edge_set.add(edge)
                edges.append([source, target, edge_type])
        else:  # global edges
            if edge not in edge_set:
                edge_set.add(edge)
                edges.append([source, target, edge_type])
    
    # Process local edges (undirected)
    for src, dst in local_edges:
        add_edge(src, dst, "local")
        add_edge(dst, src, "local")
    
    # Generate expander graph edges
    if num_nodes > 0 and expander_degree > 0:
        # Create expander graph using permutation method
        # Each node connects to expander_degree neighbors
        node_list = list(range(num_nodes))
        
        # Generate random permutations for each edge type
        for i in range(expander_degree):
            # Create random mapping
            perm = node_list.copy()
            random.shuffle(perm)
            
            # For each node, connect it to its permutation image
            for j in range(num_nodes):
                source = node_list[j]
                target = perm[j]
                if source != target:  # No self-loops
                    add_edge(source, target, "expander")
                    add_edge(target, source, "expander")
    
    # Add global nodes and edges
    if num_global_nodes > 0:
        global_start = num_nodes
        global_end = num_nodes + num_global_nodes
        
        # Connect each global node to every original node
        for global_node in range(global_start, global_end):
            for original_node in range(num_nodes):
                add_edge(global_node, original_node, "global")
                add_edge(original_node, global_node, "global")
    
    return edges
