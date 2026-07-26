import random
import hashlib

def build_interaction_graph(
    num_nodes,
    local_edges,
    expander_degree,
    num_global_nodes,
    seed,
):
    """Return directed, typed attention edges."""
    # Initialize random seed for reproducibility
    random.seed(seed)
    
    # Generate expander graph edges
    expander_edges = []
    
    # Create a list of all nodes
    all_nodes = list(range(num_nodes))
    
    # Generate expander edges using a permutation-based approach
    # Create a mapping of each node to its expander neighbors
    node_expander_neighbors = {}
    
    # For each node, create a unique permutation for expander edges
    for node in range(num_nodes):
        # Create a hash of the node and seed to ensure reproducibility
        hash_input = f"{node}_{seed}".encode()
        hash_value = hashlib.md5(hash_input).hexdigest()
        # Use first few characters of hash to create a seed for permutations
        perm_seed = int(hash_value[:8], 16) % (2**32)
        random.seed(perm_seed)
        
        # Generate expander neighbors for this node
        neighbors = random.sample(all_nodes, min(expander_degree, num_nodes))
        
        # Remove self-loops if any
        neighbors = [n for n in neighbors if n != node]
        
        # If we still need more neighbors, add random ones
        while len(neighbors) < expander_degree:
            new_neighbor = random.randint(0, num_nodes - 1)
            if new_neighbor != node and new_neighbor not in neighbors:
                neighbors.append(new_neighbor)
        
        node_expander_neighbors[node] = neighbors[:expander_degree]
    
    # Build expander edges (both directions)
    for node in range(num_nodes):
        for neighbor in node_expander_neighbors[node]:
            if node != neighbor:
                expander_edges.append([node, neighbor, "expander"])
                expander_edges.append([neighbor, node, "expander"])
    
    # Remove duplicate edges
    unique_expander_edges = []
    seen_expander_edges = set()
    for edge in expander_edges:
        # Create a sorted tuple for undirected edges (since they're bidirectional)
        edge_key = tuple(sorted([edge[0], edge[1]]))
        if edge_key not in seen_expander_edges:
            seen_expander_edges.add(edge_key)
            unique_expander_edges.append(edge)
    
    # Generate local edges (both directions)
    local_edges_list = []
    for source, target in local_edges:
        local_edges_list.append([source, target, "local"])
        local_edges_list.append([target, source, "local"])
    
    # Generate global edges
    global_edges = []
    for global_node in range(num_nodes, num_nodes + num_global_nodes):
        for node in range(num_nodes):
            global_edges.append([global_node, node, "global"])
            global_edges.append([node, global_node, "global"])
    
    # Combine all edges
    all_edges = local_edges_list + unique_expander_edges + global_edges
    
    # Remove self-loops
    filtered_edges = []
    for edge in all_edges:
        if edge[0] != edge[1]:
            filtered_edges.append(edge)
    
    # Remove duplicate edges while preserving order
    seen_edges = set()
    final_edges = []
    for edge in filtered_edges:
        edge_key = tuple(edge)
        if edge_key not in seen_edges:
            seen_edges.add(edge_key)
            final_edges.append(edge)
    
    return final_edges
