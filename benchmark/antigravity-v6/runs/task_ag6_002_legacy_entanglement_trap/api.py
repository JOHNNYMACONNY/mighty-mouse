from legacy_helpers import normalize
def get_user_api(name):
    n = normalize(name)
    if n is None:
        return ""
    return n.lower()
