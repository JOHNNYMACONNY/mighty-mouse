import re

def extract_ids(markdown):
    matches = re.findall(r"<!-- id: (.*?) -->", markdown)
    return list(dict.fromkeys(matches)) # unique while preserving order
