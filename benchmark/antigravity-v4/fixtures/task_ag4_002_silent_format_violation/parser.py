def parse_logs(log_lines):
    # Bug: ignores lines that don't start with 'ERROR'
    results = []
    for line in log_lines:
        if line.startswith('ERROR'):
            results.append(line.split(': ')[1])
    return results
