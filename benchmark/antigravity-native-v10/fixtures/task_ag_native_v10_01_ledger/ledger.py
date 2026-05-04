from decimal import Decimal
from audit import AuditEntry

class Ledger:
    def __init__(self):
        self._balance = Decimal("0")
        self._history = []

    @property
    def balance(self):
        return self._balance

    @property
    def history(self):
        return list(self._history)

    def credit(self, amount):
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError("Must be positive")
        self._balance += amount
        self._history.append(AuditEntry("credit", amount, self._balance))

    def debit(self, amount):
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError("Must be positive")
        if amount > self._balance:
            raise ValueError("Insufficient funds")
        self._balance -= amount
        self._history.append(AuditEntry("debit", amount, self._balance))
