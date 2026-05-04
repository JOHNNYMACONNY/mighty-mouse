import os

def atomic_append(filename, content):
    with open(filename, "a") as f:
        f.write(content + "\n")
