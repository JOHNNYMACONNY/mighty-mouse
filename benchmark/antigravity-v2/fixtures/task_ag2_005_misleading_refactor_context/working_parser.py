def parse_code(value):
    parts = str(value).split('-')
    return parts[1] if len(parts) > 1 else ''
