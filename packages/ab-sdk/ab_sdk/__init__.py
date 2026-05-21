"""Result-format library for agent-benchmarks run dirs."""

from .publish_gate import check_publish_ready
from .replay import replay
from .results import (
    RunDir,
    ScoresFile,
    read_run_dir,
    read_scores,
    read_trajectory,
    validate,
    write_run_dir,
)

__version__ = "0.0.1"

__all__ = [
    "RunDir",
    "ScoresFile",
    "__version__",
    "check_publish_ready",
    "read_run_dir",
    "read_scores",
    "read_trajectory",
    "replay",
    "validate",
    "write_run_dir",
]
