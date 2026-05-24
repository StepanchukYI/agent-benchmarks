"""Background worker queue."""

def enqueue(task: dict) -> str:
    return "job-1"

def status(job_id: str) -> str:
    return "pending"

# @deprecated: use enqueue() in a loop
def batch_enqueue(tasks: list) -> list:
    return []

def _retry(job_id: str) -> bool:
    return True
