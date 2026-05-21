from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_export_writes_schemas(tmp_path: Path) -> None:
    out = tmp_path / "schemas"
    result = subprocess.run(
        [sys.executable, "-m", "ab_datasets.schemas.export", "--out", str(out)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    files = sorted(out.glob("*.schema.json"))
    assert len(files) >= 5
    for path in files:
        data = json.loads(path.read_text())
        assert isinstance(data, dict)
        assert "properties" in data or "$defs" in data or "type" in data


def test_export_function_directly(tmp_path: Path) -> None:
    from ab_datasets.schemas.export import export

    written = export(tmp_path / "schemas")
    assert len(written) >= 5
    for path in written:
        assert path.exists()
        json.loads(path.read_text())
