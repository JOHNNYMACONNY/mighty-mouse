from events import EventManager

def test_event_manager():
    mgr = EventManager()
    results = []

    def handler1(data):
        results.append(f"h1:{data}")

    def handler_fail(data):
        raise ValueError("Handler failed")

    def handler2(data):
        results.append(f"h2:{data}")

    mgr.register("test", handler1)
    mgr.register("test", handler_fail)
    mgr.register("test", handler2)

    # Trigger
    try:
        mgr.publish("test", "hello")
    except Exception as e:
        pass # The orchestrator should handle isolation

    assert "h1:hello" in results
    assert "h2:hello" in results, "h2 should run even if handler_fail crashed"
    
    print("PASS")

if __name__ == "__main__":
    test_event_manager()
