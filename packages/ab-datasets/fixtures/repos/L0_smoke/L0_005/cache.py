"""In-memory cache."""

def get(key: str):
    return None

def set(key: str, value) -> None:
    pass

def delete(key: str) -> bool:
    return True

def invalidate(prefix: str) -> int:
    return 0

# @deprecated: use invalidate(prefix="")
def flush() -> None:
    pass
