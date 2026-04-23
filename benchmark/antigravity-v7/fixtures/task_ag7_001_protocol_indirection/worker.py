from protocol import parse_message

def process_data(data):
    print(f"Data: {data['payload']}")

def process_urgent(data):
    print(f"URGENT: {data['payload']}")

def handle(msg):
    parsed = parse_message(msg)
    if parsed.get('type') == 'DATA':
        process_data(parsed)
