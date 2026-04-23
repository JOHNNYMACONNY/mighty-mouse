import asyncio

class GlobalCounter:
    def __init__(self):
        self.count = 0
    
    async def increment(self):
        current = self.count
        await asyncio.sleep(0)
        self.count = current + 1
