class BatchProcessor:
    """
    Collects items. Flushes to storage when:
    - count >= max_batch_size, OR
    - tick() is called and items have been waiting > max_ticks ticks

    flush() sends all pending items to storage and resets state.
    """
    def __init__(self, storage, max_batch_size=3, max_ticks=2):
        self.storage = storage
        self.max_batch_size = max_batch_size
        self.max_ticks = max_ticks
        self._buffer = []
        self._ticks_since_first_item = 0

    def add(self, item):
        self._buffer.append(item)
        if len(self._buffer) == 1:
            # Reset tick counter when first item arrives
            self._ticks_since_first_item = 0
        if len(self._buffer) >= self.max_batch_size:
            self._flush()

    def tick(self):
        if not self._buffer:
            return
        self._ticks_since_first_item += 1
        if self._ticks_since_first_item >= self.max_ticks:
            self._flush()

    def _flush(self):
        self.storage.write(list(self._buffer))
        self._buffer = []
        self._ticks_since_first_item = 0
