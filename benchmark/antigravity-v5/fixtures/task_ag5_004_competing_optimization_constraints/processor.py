import time

def apply_filter(data):
    # Simulate work
    new_data = data[:]
    for i in range(len(new_data)):
        new_data[i] = new_data[i] * 2
        time.sleep(0.01)
    return new_data
