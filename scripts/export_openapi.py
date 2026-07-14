from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.main import app


def serialise() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("../docs/openapi.generated.json"),
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialise(), encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
