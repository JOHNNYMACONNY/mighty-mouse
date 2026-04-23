def get_profile(user_id):
    db_data = {
        "user_id": user_id,
        "name": "Bob",
        "metadata": {"theme": "dark", "clearance_level": "top-secret"}
    }
    # Task: include metadata but redact clearance_level
    return {
        "id": db_data["user_id"],
        "name": db_data["name"]
    }
