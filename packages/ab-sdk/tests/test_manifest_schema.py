"""metadata.yaml schema: missing required fields raise; full fields round-trip."""

from __future__ import annotations

import pytest
from ab_sdk.manifest import MetadataFile, read_metadata, write_metadata
from pydantic import ValidationError


def _full_metadata() -> dict:
    return {
        "run_id": "run-mf",
        "task_id": "L0_001",
        "model": "claude",
        "tier": "T0",
        "tier_hash": "sha256:abc",
        "dataset_version": "0.0.1",
        "harness": "claude-code-cli@0.4.1",
        "started_at": "2026-05-21T12:00:00+00:00",
        "finished_at": "2026-05-21T12:00:14+00:00",
        "status": "completed",
        "prompt_template_hash": "sha256:def",
    }


def test_full_metadata_roundtrips(tmp_path):
    path = tmp_path / "metadata.yaml"
    write_metadata(path, _full_metadata())

    loaded = read_metadata(path)
    assert loaded["run_id"] == "run-mf"
    assert loaded["harness"] == "claude-code-cli@0.4.1"
    assert loaded["dataset_version"] == "0.0.1"


def test_missing_required_field_raises(tmp_path):
    bad = _full_metadata()
    del bad["harness"]
    path = tmp_path / "metadata.yaml"
    with pytest.raises(ValidationError):
        write_metadata(path, bad)


def test_metadata_file_pydantic_schema_directly():
    full = _full_metadata()
    parsed = MetadataFile.model_validate(full)
    assert parsed.run_id == "run-mf"

    incomplete = {k: v for k, v in full.items() if k != "started_at"}
    with pytest.raises(ValidationError):
        MetadataFile.model_validate(incomplete)
