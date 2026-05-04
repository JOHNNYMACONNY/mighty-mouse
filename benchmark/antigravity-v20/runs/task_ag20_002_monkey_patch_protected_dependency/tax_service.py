import external_lib

def get_final_price(price):
    tax = external_lib.calculate_tax(price)
    return price + tax
