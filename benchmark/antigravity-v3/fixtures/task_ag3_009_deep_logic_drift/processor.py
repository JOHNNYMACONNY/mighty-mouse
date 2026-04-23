import transformer

def process_batch(batch):
    return [transformer.transform(x) for x in batch]
