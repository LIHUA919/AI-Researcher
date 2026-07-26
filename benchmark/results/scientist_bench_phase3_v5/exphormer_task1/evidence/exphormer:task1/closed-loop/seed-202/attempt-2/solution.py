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
    random.seed(seed)
    
    # Store all edges to avoid duplicates
    edges = set()
    
    # Helper to add edge
    def add_edge(src, tgt, edge_type):
        # Avoid self-loops
        if src == tgt:
            return
        # Add both directions for undirected edges
        edges.add((src, tgt, edge_type))
        if edge_type == "local" or edge_type == "expander":
            edges.add((tgt, src, edge_type))
    
    # Step 1: Add local edges (both directions)
    for src, tgt in local_edges:
        add_edge(src, tgt, "local")
    
    # Step 2: Generate expander graph
    # Create a d-regular graph using permutations
    if num_nodes > 0:
        # Create a list of nodes
        nodes = list(range(num_nodes))
        
        # Create expander edges
        for i in range(num_nodes):
            # For each node, connect to expander_degree other nodes
            # Using deterministic approach based on seed
            # Generate random indices to avoid duplicates
            targets = set()
            while len(targets) < expander_degree:
                # Use a deterministic approach with seed
                random.seed(seed + i + len(targets))
                idx = random.randint(0, num_nodes - 1)
                if idx != i and idx not in targets:
                    targets.add(idx)
            
            for target in targets:
                add_edge(nodes[i], target, "expander")
    
    # Step 3: Add global nodes and connect them to all original nodes
    global_start = num_nodes
    for i in range(num_global_nodes):
        global_node = global_start + i
        for j in range(num_nodes):
            # Connect global node to original node
            add_edge(global_node, j, "global")
            # Connect original node to global node
            add_edge(j, global_node, "global")
    
    # Convert to list and sort for reproducibility
    result = list(edges)
    result.sort()
    
    return result
