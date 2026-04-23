class Connection:
    def __init__(self):
        self.is_open = True
    def close(self):
        self.is_open = False

class Session:
    def __init__(self, conn):
        self.conn = conn
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()
