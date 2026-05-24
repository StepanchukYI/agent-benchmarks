"""Billing module."""

def charge(account: str, amount: float) -> str:
    """Charge an account; returns transaction id."""
    return "txn-1"

def refund_full(transaction_id: str) -> bool:
    """Refund the full amount of a transaction."""
    return True

# @deprecated: use refund_full or refund_partial
def reimburse(account: str, amount: float) -> str:
    return "txn-r"

def _audit_log(event: dict) -> None:
    pass
