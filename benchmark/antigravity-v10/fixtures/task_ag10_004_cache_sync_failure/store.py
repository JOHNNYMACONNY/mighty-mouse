from search_index import update_index

PRICES = {}

def update_price(p_id, price):
    # Update local DB
    PRICES[p_id] = price
    # Task: Sync with search index
