def normalize_rows(text):
    rows = []
    for line in text.splitlines():
        rows.append([field.strip() for field in line.split(',')])
    return rows
