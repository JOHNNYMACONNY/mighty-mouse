import asyncio

class GlobalCounter:
    def __init__(self):
        self.count = 0
        self.lock = asyncio.Lock()
    
    async def increment(self):
        async with self.lock:
            current = self.count
            await asyncio.sleep(0)
            self.count = current + 1
