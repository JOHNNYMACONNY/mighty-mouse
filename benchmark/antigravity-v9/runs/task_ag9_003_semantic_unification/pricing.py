def get_price(base, region):
    # Unified pricing logic based on region
    multipliers = {
        'US': 1.0,
        'EU': 1.2
    }
    return base * multipliers.get(region, 1.0)
