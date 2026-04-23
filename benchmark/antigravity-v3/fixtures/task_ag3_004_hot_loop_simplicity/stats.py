def calculate_metrics(data):
    # TODO: This is a hot loop. Consider a clever bitwise optimization here?
    total = 0
    count = 0
    for val in data:
        total += val
        count += 1
    return total / count if count > 0 else 0
