def parse_logs(log_lines):
    # Fixed: includes WARNING as well as ERROR
    results = []
    for line in log_lines:
        if line.startswith(('ERROR', 'WARNING')):
            results.append(line.split(': ')[1])
    return results
