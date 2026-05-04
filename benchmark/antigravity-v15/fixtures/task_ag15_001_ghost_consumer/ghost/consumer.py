# consumer.py
from api.schemas import ItemSchema

def process_item():
    # This instantiation will break if priority becomes mandatory without a default
    it = ItemSchema("Test Item")
    return it.name
