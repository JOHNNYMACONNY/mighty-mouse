from utils import Helper

def send_update(payload):
    formatted = Helper.format_data(payload)
    print(f"Sending {formatted}")
