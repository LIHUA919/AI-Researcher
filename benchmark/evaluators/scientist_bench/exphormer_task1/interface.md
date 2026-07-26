# Exphormer task1 candidate interface

Submit one standard-library-only `solution.py` defining:

```python
def build_interaction_graph(
    num_nodes,
    local_edges,
    expander_degree,
    num_global_nodes,
    seed,
):
    """Return directed, typed attention edges."""
```

Return a JSON-serializable list of `[source, target, edge_type]` triples.
`edge_type` is one of `"local"`, `"expander"`, or `"global"`.

- Original nodes are `0 .. num_nodes - 1`.
- Global nodes are appended as
  `num_nodes .. num_nodes + num_global_nodes - 1`.
- Treat each input `local_edges` pair as undirected attention by emitting both
  directions with type `"local"`.
- On original nodes, construct a simple undirected `expander_degree`-regular
  graph and emit both directions with type `"expander"`.
- Connect every global node to every original node in both directions with
  type `"global"`; do not add global-to-global edges.
- The same seed and inputs must produce the same edge set. Different seeds
  should change the expander component.
- Do not emit self-loops or duplicate typed directed edges. Keep total edges
  linear in the input edges, expander degree, and number of global nodes.

The CPU contract verifies interaction-graph construction only. It does not
train a graph transformer or support accuracy, throughput, or scalability
claims.
