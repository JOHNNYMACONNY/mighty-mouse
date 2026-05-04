# utils.py

def calculate_checksum(record_id, amount):
    """
    Standard project checksum: 
    Sum of ASCII values of ID + integer part of amount * 7
    """
    id_sum = sum(ord(c) for c in str(record_id))
    try:
        amt_int = int(float(amount))
    except (ValueError, TypeError):
        return 0
    return id_sum + (amt_int * 7)
