from decimal import Decimal
from audit import AuditEntry

class Ledger:
    """
    Tracks a balance with full audit trail.
    - credit(amount): adds to balance. amount must be > 0.
    - debit(amount): subtracts. Raises ValueError if insufficient funds or amount <= 0.
    - balance: current balance as Decimal.
    - history: list of AuditEntry (immutable, append-only).
    """

    def __init__(self):
        self._balance = Decimal("0")
        self._history = []

    @property
    def balance(self):
        return self._balance

    @property
    def history(self):
        return list(self._history)  # defensive copy — callers cannot mutate

    def credit(self, amount):
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError("Credit amount must be positive")
        self._balance += amount
        self._history.append(AuditEntry("credit", amount, self._balance))

    def debit(self, amount):
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError("Debit amount must be positive")
        if amount > self._balance:
            raise ValueError("Insufficient funds")
        self._balance -= amount
        self._history.append(AuditEntry("debit", amount, self._balance))
