from legacy_helpers import normalize
def process_billing(name):
    n = normalize(name)
    if n is None: # This check depends on the None return
        return "Empty name"
    return f"Billing {n}"
