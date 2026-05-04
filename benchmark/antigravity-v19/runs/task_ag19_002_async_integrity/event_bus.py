_fail = False

def set_fail(status):
    global _fail
    _fail = status

def emit(event_type, payload):
    if _fail:
        raise Exception("EVENT_BUS_FAILURE")
    print(f"EVENT: {event_type} - {payload}")
