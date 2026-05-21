"""Model-runner adapters that normalize into the shared trajectory protocol."""

from ab_harness.runners.anthropic_compat import AnthropicCompatRunner
from ab_harness.runners.base import BaseRunner
from ab_harness.runners.claude_code import ClaudeCodeRunner
from ab_harness.runners.factory import StubRunner, make_runner, supported_runners
from ab_harness.runners.mock import MockRunner
from ab_harness.runners.openai_compat import OpenAICompatRunner

__all__ = [
    "AnthropicCompatRunner",
    "BaseRunner",
    "ClaudeCodeRunner",
    "MockRunner",
    "OpenAICompatRunner",
    "StubRunner",
    "make_runner",
    "supported_runners",
]
