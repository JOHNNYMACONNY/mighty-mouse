import random

def flaky_operation():
    if random.random() < 0.1:
        raise RuntimeError("Operation failed randomly")
    return "Success"

def run():
    result = flaky_operation()
    print(result)

if __name__ == "__main__":
    run()
