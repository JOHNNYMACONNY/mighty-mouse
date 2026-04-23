class App:
    def __init__(self, config):
        self.config = config
    
    def run(self):
        return f"App running on port {self.config.get_port()}"
