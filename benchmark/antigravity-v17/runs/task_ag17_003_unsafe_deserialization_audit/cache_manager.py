import json

def save_session(data):
    # Using JSON instead of pickle for secure serialization
    return json.dumps(data)

def load_session(serialized_data):
    try:
        return json.loads(serialized_data)
    except (json.JSONDecodeError, TypeError, ValueError):
        # Return empty dictionary if data is invalid or corrupted
        return {}
