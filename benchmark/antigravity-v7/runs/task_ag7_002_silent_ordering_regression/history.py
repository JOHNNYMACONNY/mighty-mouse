def get_recent_actions(actions):
    # Fixed: list(set(actions)) destroys order.
    # dict.fromkeys preserves insertion order. Since input is most recent first,
    # keeping the first occurrence of each action maintains that order.
    return list(dict.fromkeys(actions))
