# discount_overrides.py

# Legacy rule: Any order over $1000 gets an additional 0.05 flat discount, 
# even for premium members, but MUST NOT exceed MAX_DISCOUNT_CAP.

def get_legacy_bonus(total):
    if total > 1000:
        return 0.05
    return 0.0
