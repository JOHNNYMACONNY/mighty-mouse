# remote_api.py

class APIError(Exception):
    pass

def post_data(payload):
    # Task constraint: Simulate a failure if 'fail' is in payload
    if payload.get('trigger_fail'):
        raise APIError("Remote API Connection Failed")
    print(f"RemoteAPI: Posted {payload}")
    return {"status": "success"}
