def get_profile(user_id):
    db_data = {
        "user_id": user_id,
        "name": "Bob",
        "metadata": {"theme": "dark", "clearance_level": "top-secret"}
    }
    # Included metadata but redacted clearance_level as per SECURITY_POLICY.md
    safe_metadata = db_data["metadata"].copy()
    if "clearance_level" in safe_metadata:
        del safe_metadata["clearance_level"]
        
    return {
        "id": db_data["user_id"],
        "name": db_data["name"],
        "metadata": safe_metadata
    }
