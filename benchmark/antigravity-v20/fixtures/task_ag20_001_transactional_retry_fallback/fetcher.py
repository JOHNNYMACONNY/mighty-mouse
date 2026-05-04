from infrastructure import remote_service
from cache import local_store

def fetch_with_resilience():
    # BUG: No retry or fallback logic. This implementation is fragile.
    return remote_service.get_data()
