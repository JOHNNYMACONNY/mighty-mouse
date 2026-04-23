import random

def flaky_operation():
    if random.random() < 0.1:
        raise RuntimeError("Operation failed randomly")
    return "Success"

def run():
    for attempt in range(3):
        try:
            result = flaky_operation()
            print(result)
            return
        except RuntimeError as e:
            if attempt == 2:
                raise e
            print(f"Attempt {attempt + 1} failed, retrying...")

if __name__ == "__main__":
    run()
