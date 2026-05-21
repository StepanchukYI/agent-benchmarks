"""Model-runner adapters that normalize into the shared trajectory protocol."""

from ab_harness.runners.base import BaseRunner
from ab_harness.runners.claude_code import ClaudeCodeRunner
from ab_harness.runners.mock import MockRunner

__all__ = ["BaseRunner", "ClaudeCodeRunner", "MockRunner"]
