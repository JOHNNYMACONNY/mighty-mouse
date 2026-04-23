import low_level

def transform(val):
    return low_level.clip_value(val * 1.5)
