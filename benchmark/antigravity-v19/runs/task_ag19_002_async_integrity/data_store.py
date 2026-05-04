_records = {"1": "old_val"}

def get_val(id):
    return _records.get(id)

def set_val(id, val):
    _records[id] = val
