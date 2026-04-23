import asyncio

async def fetch_item(id):
    await asyncio.sleep(0.01)
    return f"Item {id}"

async def fetch_all(ids):
    # Parallelized using asyncio.gather to preserve order as per requirements
    return await asyncio.gather(*[fetch_item(i) for i in ids])
