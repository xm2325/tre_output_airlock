"""Lineage manifest construction."""

from __future__ import annotations

import json
import os
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .hashing import sha256_file, sha256_text


def build_lineage_manifest(
    *,
    run_id: str,
    fhir_path: Path,
    genomic_manifest_path: Path,
    genomic_files: list[Path],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """Build a machine-readable source and execution record."""
    sources = [fhir_path, genomic_manifest_path, *genomic_files]
    return {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "pipeline_version": "0.1.0",
        "code_revision": os.getenv("GITHUB_SHA", "local"),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "configuration_sha256": sha256_text(
            json.dumps({"date_shift_limit_days": 30, "output_format": "jsonl+csv"}, sort_keys=True)
        ),
        "sources": [
            {
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sources
        ],
        "metrics": metrics,
    }
