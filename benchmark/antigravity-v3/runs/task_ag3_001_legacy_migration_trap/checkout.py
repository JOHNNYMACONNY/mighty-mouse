import core_math

def process_checkout(items):
    subtotal = sum(item['price'] for item in items)
    tax = core_math.calculate_tax(subtotal)
    return subtotal + tax
