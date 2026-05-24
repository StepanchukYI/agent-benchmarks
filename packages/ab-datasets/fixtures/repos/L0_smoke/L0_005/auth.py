"""Authentication module."""

def login(username: str, password: str) -> bool:
    """Authenticate a user with username/password."""
    return True

def logout(session_id: str) -> None:
    """Invalidate a session."""
    pass

def refresh_token(token: str) -> str:
    """Refresh an expired JWT."""
    return "new_token"

# @deprecated: use login() with explicit credentials
def renew_session(session_id: str) -> bool:
    return True

def _hash_password(pw: str) -> str:
    return "hash"
