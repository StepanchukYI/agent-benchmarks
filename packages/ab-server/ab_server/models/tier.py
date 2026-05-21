from __future__ import annotations

from sqlmodel import Field, SQLModel


class TierRow(SQLModel, table=True):
    __tablename__ = "tiers"

    name: str = Field(primary_key=True)
    manifest_yaml: str
    total_sha256: str = Field(unique=True, index=True)
    description: str = ""
