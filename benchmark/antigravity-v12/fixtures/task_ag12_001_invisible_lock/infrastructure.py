import threading

class Infrastructure:
    """
    Global infrastructure services.
    All shared resources MUST use the GlobalLock for atomicity.
    """
    GlobalLock = threading.Lock()
