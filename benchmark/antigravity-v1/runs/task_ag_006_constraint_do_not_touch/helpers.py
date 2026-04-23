def currency_symbol():
    return '$'


def format_price(value):
    if value is None:
        return f"{currency_symbol()}0"
    return f"{currency_symbol()}{float(value):.1f}"
