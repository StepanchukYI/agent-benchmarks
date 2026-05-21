"""Auth module."""


def login(user, password):
    """Login a user."""
    return True


def logout(user):
    """Log out a user."""
    return True


# @deprecated: replaced by `refresh_token`. Do NOT include in README.
def renew_session(user):
    return True


def refresh_token(user):
    """Refresh the auth token."""
    return True


def _hash_password(password):
    return password
