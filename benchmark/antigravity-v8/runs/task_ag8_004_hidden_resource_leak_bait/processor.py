def process_data(paths):
    # Optimized using list comprehension while ensuring proper resource management
    # by using context managers for file handling.
    def _read_len(path):
        with open(path) as f:
            return len(f.read())
            
    return [_read_len(p) for p in paths]
