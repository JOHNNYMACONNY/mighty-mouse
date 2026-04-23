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
    # Task: implement atomic transfer
    # Must revert withdraw if deposit fails
    pass
