from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from . import (
    Fixture,
    ScorerSpec,
    ScorerVerdict,
    Submission,
    Task,
    TaskConfig,
    TierManifest,
    Totals,
    Trajectory,
    Turn,
)

MODELS: tuple[type[BaseModel], ...] = (
    Task,
    TaskConfig,
    Fixture,
    ScorerSpec,
    ScorerVerdict,
    TierManifest,
    Turn,
    Totals,
    Trajectory,
    Submission,
)


def export(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for model in MODELS:
        schema = model.model_json_schema()
        target = out_dir / f"{model.__name__}.schema.json"
        target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
        written.append(target)
        print(str(target))
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Pydantic models to JSON Schema files.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/schemas"),
        help="Directory to write *.schema.json files into.",
    )
    args = parser.parse_args()
    export(args.out)


if __name__ == "__main__":
    main()
