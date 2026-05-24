"""Object storage."""

def put(bucket: str, key: str, blob: bytes) -> str:
    return "etag"

def get(bucket: str, key: str) -> bytes:
    return b""

def delete(bucket: str, key: str) -> bool:
    return True

def _validate_bucket(b: str) -> bool:
    return True
