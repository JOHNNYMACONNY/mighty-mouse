import re

def parse_phone(text):
    # This regex is buggy and slow
    # Task: implement a robust parser
    regex = r"\(?(\d+)\)?[-.\s]?(\d+)[-.\s]?(\d+)"
    match = re.search(regex, text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None
