class EventManager:
    def __init__(self):
        self.topics = {} # topic -> list of handlers

    def register(self, topic, handler):
        if topic not in self.topics:
            self.topics[topic] = []
        self.topics[topic].append(handler)

    def publish(self, topic, data):
        if topic not in self.topics:
            return
        
        for handler in self.topics[topic]:
            try:
                handler(data)
            except Exception as e:
                # Log error or just continue to ensure isolation
                pass
