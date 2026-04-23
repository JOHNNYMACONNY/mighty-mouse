STATES = ['DRAFT', 'REVIEWED', 'PUBLISHED']

class Document:
    def __init__(self, content):
        self.content = content
        self.status = 'DRAFT'
    
    def set_status(self, new_status):
        # Task: enforce the order DRAFT -> REVIEWED -> PUBLISHED
        # Throw ValueError on invalid transitions
        self.status = new_status
