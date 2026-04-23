from decimal import Decimal

class AuditEntry:
    """Immutable record of a ledger transaction."""
    def __init__(self, txn_type, amount, balance_after):
        self.txn_type = txn_type
        self.amount = Decimal(str(amount))
        self.balance_after = Decimal(str(balance_after))

    def __repr__(self):
        return f"AuditEntry({self.txn_type}, {self.amount}, balance={self.balance_after})"
