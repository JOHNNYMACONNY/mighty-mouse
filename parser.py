def parse_scores(csv_string):
    lines = csv_string.strip().split('\n')
    if not lines:
        return {}
    
    # Assume first line is header
    header = lines[0].split(',')
    data_rows = lines[1:]
    
    results = {}
    for row in data_rows:
        if not row:
            continue
        parts = row.split(',')
        if len(parts) < 2:
            continue
        
        name = parts[0]
        score_raw = parts[1]
        
        try:
            score = int(score_raw)
            results[name] = score
        except ValueError:
            # Ignore non-numeric scores
            continue
            
    return results
