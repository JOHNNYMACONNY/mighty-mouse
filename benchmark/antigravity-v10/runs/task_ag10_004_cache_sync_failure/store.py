from search_index import update_index

PRICES = {}

def update_price(p_id, price):
    # Update local DB
    PRICES[p_id] = price
    # Synchronize with search index
    update_index(p_id, price)
