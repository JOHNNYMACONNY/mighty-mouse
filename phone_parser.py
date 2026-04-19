import re

def parse_phone(text):
    regex = r"\(\d{3}\)\s\d{3}-\d{4}"
    matches = re.findall(regex, text)
    return [m.replace("(", "").replace(")", "").replace(" ", "").replace("-", "") for m in matches]
