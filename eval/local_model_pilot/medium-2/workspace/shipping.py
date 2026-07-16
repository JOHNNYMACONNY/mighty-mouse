def calculate_shipping(method: str, base_cost: float) -> float:
    """Calculate shipping cost based on the method and base cost."""
    if method == "standard":
        return base_cost * 1.0
    elif method == "express":
        return base_cost * 1.5 + 5.0
    elif method == "overnight":
        return base_cost * 2.5 + 15.0
    else:
        raise ValueError(f"Unknown shipping method: {method}")
