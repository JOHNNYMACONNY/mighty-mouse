def is_authorized(user_roles, required_role):
    # BUG: Substring check allows escalation
    for role in user_roles:
        if required_role in role:
            return True
    return False
