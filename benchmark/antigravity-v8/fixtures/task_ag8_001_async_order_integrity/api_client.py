import asyncio

async def fetch_item(id):
    await asyncio.sleep(0.01)
    return f"Item {id}"

async def fetch_all(ids):
    results = []
    for i in ids:
        results.append(await fetch_item(i))
    return results
