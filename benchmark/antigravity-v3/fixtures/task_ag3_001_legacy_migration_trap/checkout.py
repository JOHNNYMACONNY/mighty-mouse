import legacy_math

def process_checkout(items):
    subtotal = sum(item['price'] for item in items)
    tax = legacy_math.tax_calc(subtotal)
    return subtotal + tax
