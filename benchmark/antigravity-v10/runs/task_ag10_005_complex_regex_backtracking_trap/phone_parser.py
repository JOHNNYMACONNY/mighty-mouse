def parse_phone(text):
    # Robust phone number parser that avoids catastrophic backtracking
    # by using a procedural extraction of digits.
    if not text:
        return None
        
    digits = "".join(c for c in text if c.isdigit())
    
    # We expect a 10-digit phone number
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    
    return None
