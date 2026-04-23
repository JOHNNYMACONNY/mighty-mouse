def clamp_percentage(value):
    if value is None:
        return 0
    return min(max(int(value), 0), 99)
