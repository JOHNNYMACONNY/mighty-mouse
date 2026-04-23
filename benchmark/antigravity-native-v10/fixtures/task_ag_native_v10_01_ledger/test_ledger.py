from decimal import Decimal
from ledger import Ledger

def test_credit_and_balance():
    L = Ledger()
    L.credit("100.50")
    assert L.balance == Decimal("100.50")

def test_debit_reduces_balance():
    L = Ledger()
    L.credit("200")
    L.debit("75.25")
    assert L.balance == Decimal("124.75")

def test_insufficient_funds():
    L = Ledger()
    L.credit("10")
    raised = False
    try:
        L.debit("50")
    except ValueError:
        raised = True
    assert raised

def test_audit_trail_integrity():
    L = Ledger()
    L.credit("500")
    L.debit("200")
    L.credit("100")
    h = L.history
    assert len(h) == 3
    assert h[0].txn_type == "credit" and h[0].balance_after == Decimal("500")
    assert h[1].txn_type == "debit"  and h[1].balance_after == Decimal("300")
    assert h[2].txn_type == "credit" and h[2].balance_after == Decimal("400")

def test_history_is_immutable():
    L = Ledger()
    L.credit("50")
    copy = L.history
    copy.clear()
    # Original history must still have 1 entry
    assert len(L.history) == 1

def test_zero_credit_rejected():
    L = Ledger()
    raised = False
    try:
        L.credit(0)
    except ValueError:
        raised = True
    assert raised

def test_floating_point_precision():
    # Classic float trap: 0.1 + 0.2 != 0.3 in float, but Decimal handles it
    L = Ledger()
    L.credit("0.1")
    L.credit("0.2")
    assert L.balance == Decimal("0.3")

if __name__ == "__main__":
    test_credit_and_balance()
    test_debit_reduces_balance()
    test_insufficient_funds()
    test_audit_trail_integrity()
    test_history_is_immutable()
    test_zero_credit_rejected()
    test_floating_point_precision()
    print("PASS")
