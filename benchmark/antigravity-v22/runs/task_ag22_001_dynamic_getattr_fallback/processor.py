class Processor:
    def process_data(self, data): return f'Processed: {data}'
    def __getattr__(self, name):
        if name.startswith('process_'): return lambda *a, **k: None
        raise AttributeError(name)