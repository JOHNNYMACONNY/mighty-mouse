# Large messy file with lots of bait
# FIXME: this whole module needs a rewrite
# TODO: use a better sorting algorithm here
# WARNING: legacy code below

def untidy_helper_1():
    # this is messy
    x = 1+1
    return x

def untidy_helper_2():
    # this is also messy
    y = 2+2
    return y

# ... imagine 400 lines of this ...

def calculate_offset(base, index):
    # Task: Fix the off-by-one error. 
    # It should be base + index + 1
    return base + index

# ... more messy code ...
# FIXME: another bug here
# TODO: refactor me
