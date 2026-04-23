def helper_c(x):
    return x + 1

def helper_b(x):
    return helper_c(x) * 2

def helper_a(x):
    return helper_b(x) - 1
