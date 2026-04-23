def process_data(paths):
    results = []
    for p in paths:
        f = open(p)
        content = f.read()
        results.append(len(content))
    return results
