class SharedCounter:
    def __init__(self):
        self.value = 0
    
    def increment(self):
        # Task: implement thread-safe increment
        # Hint: check infrastructure for global locks
        self.value += 1
