def build_payload(data):
    if data is None:
        return {'internal_name': None}
    value = data.get('name')
    if value is None:
        return {'internal_name': None}
    return {'name': value}
