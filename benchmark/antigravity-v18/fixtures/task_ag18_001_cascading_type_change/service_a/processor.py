from common.utils import get_next_id

def process_item(item_name):
    # This logic assumes ID is an integer for arithmetic
    new_id = get_next_id()
    return {"name": item_name, "sort_index": new_id * 10}
