import random
from typing import List, Tuple

def build_interaction_graph(
    num_nodes: int,
    local_edges: List[Tuple[int, int]],
    expander_degree: int,
    num_global_nodes: int,
    seed: int
) -> List[List]:
    """Return directed, typed attention edges."""
    
    # Set seed for reproducibility
    random.seed(seed)
    
    edges = []
    
    # Step 1: Add local edges (both directions)
    for u, v in local_edges:
        edges.append([u, v, "local"])
        edges.append([v, u, "local"])
    
    # Step 2: Generate expander graph edges
    # Create a d-regular expander graph for original nodes
    if num_nodes > 0 and expander_degree > 0:
        # Create degree list for each node
        node_degrees = [0] * num_nodes
        
        # For a d-regular graph, we need to construct a symmetric graph
        # We'll generate a random regular graph using a simple approach:
        # For each node, connect to exactly 'expander_degree' other nodes
        # that are not already connected
        
        # We'll use a simple construction method to make sure it's regular
        # Each node connects to the next 'expander_degree' nodes in a cyclic manner
        # and then fill in with random connections to maintain d-regularity
        
        # Initialize connections per node
        connections = [[] for _ in range(num_nodes)]
        
        # Create base connections in a systematic way
        for i in range(num_nodes):
            for j in range(1, expander_degree + 1):
                neighbor = (i + j) % num_nodes
                if neighbor != i and neighbor not in connections[i] and len(connections[i]) < expander_degree:
                    connections[i].append(neighbor)
                    connections[neighbor].append(i)
                    
        # If we haven't reached full degree, add random connections
        for i in range(num_nodes):
            while len(connections[i]) < expander_degree:
                # Try to add a random neighbor
                candidate = random.randint(0, num_nodes - 1)
                if candidate != i and candidate not in connections[i]:
                    connections[i].append(candidate)
                    connections[candidate].append(i)
                    
        # Add expander edges (both directions)
        for i in range(num_nodes):
            for neighbor in connections[i]:
                if i < neighbor:  # Avoid duplicates
                    edges.append([i, neighbor, "expander"])
                    edges.append([neighbor, i, "expander"])
    
    # Step 3: Add global node connections
    # Global nodes are numbered from num_nodes to num_nodes + num_global_nodes - 1
    global_start = num_nodes
    global_end = num_nodes + num_global_nodes
    
    # Connect each global node to every original node
    for i in range(global_start, global_end):
        for j in range(num_nodes):
            edges.append([i, j, "global"])
            edges.append([j, i, "global"])
    
    # Step 4: Remove duplicates and self-loops
    # Use a set to track seen edges
    seen = set()
    unique_edges = []
    
    for source, target, edge_type in edges:
        # Skip self-loops
        if source == target:
            continue
            
        # Create tuple for deduplication
        edge_tuple = (source, target, edge_type)
        if edge_tuple not in seen:
            seen.add(edge_tuple)
            unique_edges.append([source, target, edge_type])
    
    # Sort for consistent output
    unique_edges.sort(key=lambda x: (x[0], x[1], x[2]))
    
    return unique_edges
