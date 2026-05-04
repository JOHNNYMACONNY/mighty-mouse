import data_store
import event_bus

def update_with_event(record_id, value):
    # BUG: No rollback logic
    data_store.set_val(record_id, value)
    event_bus.emit("UPDATE", {"id": record_id, "val": value})
