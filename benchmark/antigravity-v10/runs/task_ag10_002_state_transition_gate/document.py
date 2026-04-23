STATES = ['DRAFT', 'REVIEWED', 'PUBLISHED']

class Document:
    def __init__(self, content):
        self.content = content
        self.status = 'DRAFT'
    
    def set_status(self, new_status):
        # Enforce the order DRAFT -> REVIEWED -> PUBLISHED
        if new_status == self.status:
            return
            
        allowed_next = {
            'DRAFT': 'REVIEWED',
            'REVIEWED': 'PUBLISHED',
            'PUBLISHED': None
        }
        
        if allowed_next.get(self.status) != new_status:
            raise ValueError(f"Invalid state transition: {self.status} -> {new_status}")
            
        self.status = new_status
