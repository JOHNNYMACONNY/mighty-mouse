from batch_processor import BatchProcessor

class MockStorage:
    def __init__(self):
        self.writes = []
    def write(self, batch):
        self.writes.append(batch)

def test_flush_on_count():
    storage = MockStorage()
    bp = BatchProcessor(storage, max_batch_size=3, max_ticks=10)
    bp.add("a")
    bp.add("b")
    assert len(storage.writes) == 0  # not flushed yet
    bp.add("c")
    assert len(storage.writes) == 1
    assert storage.writes[0] == ["a", "b", "c"]

def test_flush_on_timeout():
    storage = MockStorage()
    bp = BatchProcessor(storage, max_batch_size=10, max_ticks=2)
    bp.add("x")
    bp.tick()  # 1 tick
    assert len(storage.writes) == 0
    bp.tick()  # 2nd tick — should flush
    assert len(storage.writes) == 1
    assert storage.writes[0] == ["x"]

def test_no_flush_when_empty():
    storage = MockStorage()
    bp = BatchProcessor(storage, max_batch_size=3, max_ticks=1)
    bp.tick()
    bp.tick()
    assert len(storage.writes) == 0  # no items, never flush

def test_buffer_resets_after_flush():
    storage = MockStorage()
    bp = BatchProcessor(storage, max_batch_size=2, max_ticks=5)
    bp.add("p")
    bp.add("q")  # triggers count flush
    bp.add("r")
    assert len(storage.writes) == 1
    assert storage.writes[0] == ["p", "q"]
    # r should still be in buffer, not yet flushed
    bp.add("s")  # triggers second flush
    assert len(storage.writes) == 2
    assert storage.writes[1] == ["r", "s"]

if __name__ == "__main__":
    test_flush_on_count()
    test_flush_on_timeout()
    test_no_flush_when_empty()
    test_buffer_resets_after_flush()
    print("PASS")
