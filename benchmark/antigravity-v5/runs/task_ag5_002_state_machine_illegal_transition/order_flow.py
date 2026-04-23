class Order:
    STATES = ['PENDING', 'PAID', 'SHIPPED']
    
    def __init__(self):
        self.state = 'PENDING'
    
    def pay(self):
        if self.state == 'PENDING':
            self.state = 'PAID'
            
    def ship(self):
        if self.state == 'PAID':
            self.state = 'SHIPPED'

    def cancel(self):
        if self.state in ('PENDING', 'PAID'):
            self.state = 'CANCELLED'
