import utils

def process_data(data):
    # Neutralizing state in legacy utils library to ensure statelessness
    utils.reset_counter()
    count = utils.increment_and_get()
    return f"{data}_{count}"
