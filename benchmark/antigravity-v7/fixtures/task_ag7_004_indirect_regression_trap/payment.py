def do_work(item):
    print(f"Working on {item}")

def process(items):
    # items is an iterator (e.g. from a generator)
    for item in items:
        do_work(item)
