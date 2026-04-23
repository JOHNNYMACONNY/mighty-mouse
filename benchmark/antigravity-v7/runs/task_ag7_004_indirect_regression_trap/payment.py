def do_work(item):
    print(f"Working on {item}")

def process(items):
    # Converted items to a list to support iterators/generators without exhausting them
    # before the processing loop.
    items = list(items)
    print(f"Processing {len(items)} items")
    for item in items:
        do_work(item)
