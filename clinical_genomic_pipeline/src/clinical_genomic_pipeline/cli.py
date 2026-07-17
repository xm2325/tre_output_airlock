"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the synthetic clinical-genomic pipeline")
    parser.add_argument("--fhir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--secret", default=os.getenv("PIPELINE_PSEUDONYMISATION_SECRET"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_pipeline(
        fhir_path=args.fhir,
        genomic_manifest_path=args.manifest,
        output_root=args.output,
        secret=args.secret,
    )
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "run_directory": str(result.run_directory),
                "reused_existing_run": result.reused_existing_run,
                "people_count": result.people_count,
                "sample_count": result.sample_count,
                "issue_count": result.issue_count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
