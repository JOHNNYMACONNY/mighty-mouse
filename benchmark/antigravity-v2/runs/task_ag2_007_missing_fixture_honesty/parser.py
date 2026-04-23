def parse_mode(value):
    if value is None:
        return 'default'
    return str(value).strip().lower()
