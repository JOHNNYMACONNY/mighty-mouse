from handler import handle_request

def process_route():
    record = handle_request({"id": 1})
    # This line fails because Record has no 'status' attribute
    return f"Status: {record.status}"
