def is_authorized(user_roles, required_role):
    # FIXED: Exact match check to prevent permission escalation
    return required_role in user_roles
