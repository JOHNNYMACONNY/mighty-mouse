def get_recent_actions(actions):
    # Task: deduplicate actions but keep most recent first
    # actions is a list where index 0 is most recent
    return list(set(actions))
