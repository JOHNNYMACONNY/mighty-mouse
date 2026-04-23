from legacy_helpers import normalize
def get_user_api(name):
    n = normalize(name)
    return n.lower() # Crashing here if n is None
