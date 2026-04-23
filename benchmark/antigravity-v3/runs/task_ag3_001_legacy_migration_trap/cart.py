import legacy_math

def update_cart(cart_id, items):
    # This file should NOT be touched
    subtotal = sum(item['price'] for item in items)
    return legacy_math.tax_calc(subtotal)
