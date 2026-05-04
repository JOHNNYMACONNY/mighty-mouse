import json
import client

def start_request():
    with open('settings.json', 'r') as f:
        config = json.load(f)
    # Passing the timeout to the client
    return client.send_data("data", config.get('timeout'))
