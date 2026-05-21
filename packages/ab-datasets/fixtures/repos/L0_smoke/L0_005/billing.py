"""Billing module."""


def charge(user, amount):
    """Charge a user."""
    return True


# @deprecated: use `refund_full` instead.
def reimburse(user):
    return True


def refund_full(user):
    """Refund a charge in full."""
    return True


def _ledger_entry(user, amount):
    return True
