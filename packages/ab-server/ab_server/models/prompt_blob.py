from __future__ import annotations

from sqlmodel import Field, SQLModel

# Maximum stored/served prompt text length (64 KB). Prompts longer than this
# are truncated at ingest; a sentinel suffix marks the truncation.
_PROMPT_BLOB_MAX_BYTES = 64 * 1024
_TRUNCATION_MARKER = "\n... [truncated at 64KB]"


def _truncate(text: str) -> str:
    """Truncate prompt text to 64 KB (UTF-8 bytes), appending a marker."""
    encoded = text.encode("utf-8")
    if len(encoded) <= _PROMPT_BLOB_MAX_BYTES:
        return text
    # Truncate bytes then decode safely, appending the marker.
    truncated = encoded[: _PROMPT_BLOB_MAX_BYTES].decode("utf-8", errors="ignore")
    return truncated + _TRUNCATION_MARKER


class PromptBlob(SQLModel, table=True):
    """Content-addressed store for custom prompt texts.

    Keyed by prompt_hash (= tier_hash when a custom CLAUDE.md was used).
    Upsert is idempotent — duplicate inserts are silently skipped by the
    ingest layer.
    """

    __tablename__ = "prompt_blobs"

    # prompt_hash is the SHA-256 of the tier config that includes the custom
    # CLAUDE.md (= trajectory.tier_hash when a custom prompt was active).
    prompt_hash: str = Field(primary_key=True)
    # Verbatim prompt text, truncated to 64 KB.
    text: str
    # Human-readable label from --prompt-label; None when not supplied.
    label: str | None = Field(default=None, nullable=True)
