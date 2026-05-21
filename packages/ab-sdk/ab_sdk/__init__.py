"""Result-format library for agent-benchmarks run dirs."""

from .results import RunDir, read_run_dir, read_trajectory, validate, write_run_dir

__version__ = "0.0.1"

__all__ = [
    "RunDir",
    "__version__",
    "read_run_dir",
    "read_trajectory",
    "validate",
    "write_run_dir",
]
