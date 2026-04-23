from constants import MESSAGE_TYPES

def parse_message(msg):
    parts = msg.split(':')
    if len(parts) < 2:
        return {'type': 'UNKNOWN', 'payload': None}
    m_type = parts[0]
    if m_type in MESSAGE_TYPES:
        return {'type': m_type, 'payload': parts[1]}
    return {'type': 'UNKNOWN', 'payload': None}
