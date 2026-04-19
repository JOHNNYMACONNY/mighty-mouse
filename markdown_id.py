import re

def extract_ids(markdown):
    return re.findall(r"id:\s*(\w+)", markdown)
