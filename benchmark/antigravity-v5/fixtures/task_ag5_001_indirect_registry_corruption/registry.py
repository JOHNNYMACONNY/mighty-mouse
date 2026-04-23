class Registry:
    def __init__(self):
        self.services = []
    
    def register(self, service):
        self.services.append(service)
    
    def get_active(self):
        return [s for s in self.services if s.is_active()]

class Service:
    def __init__(self, name):
        self.name = name
        self.active = True
    
    def is_active(self):
        return self.active
