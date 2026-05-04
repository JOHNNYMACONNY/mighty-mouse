# local_db.py
_data = {}

def insert(key, val):
    _data[key] = val
    print(f"LocalDB: Inserted {key}")

def delete(key):
    if key in _data:
        del _data[key]
        print(f"LocalDB: Deleted {key}")

def get(key):
    return _data.get(key)
