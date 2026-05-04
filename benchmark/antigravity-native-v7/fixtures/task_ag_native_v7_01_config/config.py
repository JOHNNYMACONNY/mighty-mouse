class Config:
    def __init__(self, port=8080):
        self.port = port
    def get_port(self):
        return self.port

SETTINGS = {
    "debug": False,
    "port": 8080
}
