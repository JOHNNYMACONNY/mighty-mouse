_data = "initial"
_fail_next = False

def get_node_data():
    return _data

def update_node(val):
    global _data
    if _fail_next:
        raise Exception("NODE_C_FAILURE")
    _data = val

def set_fail(status):
    global _fail_next
    _fail_next = status
