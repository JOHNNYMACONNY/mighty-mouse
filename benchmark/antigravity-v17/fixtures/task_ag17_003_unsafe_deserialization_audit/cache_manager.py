import pickle

def save_session(data):
    return pickle.dumps(data)

def load_session(serialized_data):
    try:
        return pickle.loads(serialized_data)
    except Exception:
        return {}
