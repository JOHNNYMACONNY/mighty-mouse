ACCOUNTS = {"A": 100, "B": 50}

def withdraw(acc_id, amount):
    if ACCOUNTS.get(acc_id, 0) >= amount:
        ACCOUNTS[acc_id] -= amount
        return True
    return False

def deposit(acc_id, amount):
    if acc_id in ACCOUNTS:
        ACCOUNTS[acc_id] += amount
        return True
    return False

def transfer(from_id, to_id, amount):
    # Atomic transfer implementation with rollback on failure
    if not withdraw(from_id, amount):
        return False
    
    if not deposit(to_id, amount):
        # Rollback: return the funds to the source account
        deposit(from_id, amount)
        return False
        
    return True
