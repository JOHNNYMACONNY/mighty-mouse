from nodes import node_a, node_b, node_c

def update_all(value):
    # BUG: No rollback logic. This will leave nodes in an inconsistent state if it fails mid-way.
    node_a.update_node(value)
    node_b.update_node(value)
    node_c.update_node(value)
