_id_counter = 0

def get_next_id():
    global _id_counter
    _id_counter += 1
    return _id_counter
