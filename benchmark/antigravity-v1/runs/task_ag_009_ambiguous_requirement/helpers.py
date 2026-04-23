def smart_sort(items):
    if items is None:
        return []
    # Assumption: Case-insensitive sorting is preferred for a "smart" sort.
    # Tie-breaking with the original value ensures deterministic results.
    return sorted(items, key=lambda x: (str(x).lower(), str(x)))

