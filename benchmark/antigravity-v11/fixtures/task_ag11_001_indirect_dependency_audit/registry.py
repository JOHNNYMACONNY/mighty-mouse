def lookup(record_id):
    """
    Look up a record in the legacy database.
    IMPORTANT: record_id must be an integer.
    """
    if not isinstance(record_id, int):
        raise ValueError("Registry only supports integer IDs.")
    return {"id": record_id, "name": "Legacy Record"}
