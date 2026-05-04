import utils

def process_data(data):
    # BUG: This uses the global counter without resetting it, leading to state leakage
    count = utils.increment_and_get()
    return f"{data}_{count}"
