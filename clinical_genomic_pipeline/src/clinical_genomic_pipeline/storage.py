"""AWS curated-publication planning with an explicit restricted-data deny boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .hashing import sha256_file

_ALLOWED_ROOT_FILES = {
    "_SUCCESS",
    "contract_report.json",
    "data_quality_report.json",
    "lineage.json",
    "metrics.json",
    "transfer_report.json",
}


def build_curated_publish_plan(
    *,
    run_directory: Path,
    bucket: str,
    prefix: str,
) -> list[dict[str, Any]]:
    """Plan encrypted S3 objects for curated evidence and gold data only."""
    if not (run_directory / "_SUCCESS").is_file():
        raise ValueError("Only successful runs can be planned for curated publication")
    if not bucket.strip():
        raise ValueError("bucket must not be empty")

    candidates = [path for path in run_directory.rglob("*") if path.is_file()]
    plan: list[dict[str, Any]] = []
    for path in sorted(candidates):
        relative = path.relative_to(run_directory)
        if relative.parts[0] == "gold":
            classification = "CURATED_RESEARCH"
        elif len(relative.parts) == 1 and relative.name in _ALLOWED_ROOT_FILES:
            classification = "OPERATIONAL_EVIDENCE"
        else:
            continue
        key = "/".join(part for part in (prefix.strip("/"), run_directory.name, relative.as_posix()) if part)
        plan.append(
            {
                "source_path": str(path),
                "bucket": bucket,
                "key": key,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "classification": classification,
            }
        )

    if any("restricted" in Path(item["source_path"]).parts for item in plan):
        raise AssertionError("Restricted linkage material must never enter the curated publish plan")
    return plan


def upload_curated_publish_plan(
    *,
    plan: list[dict[str, Any]],
    client: Any,
    kms_key_id: str,
) -> dict[str, Any]:
    """Upload a pre-validated plan through a boto3-compatible client using SSE-KMS."""
    if not kms_key_id.strip():
        raise ValueError("kms_key_id must not be empty")
    uploaded_bytes = 0
    for item in plan:
        source_path = Path(str(item["source_path"]))
        with source_path.open("rb") as body:
            client.put_object(
                Bucket=str(item["bucket"]),
                Key=str(item["key"]),
                Body=body.read(),
                ServerSideEncryption="aws:kms",
                SSEKMSKeyId=kms_key_id,
                Metadata={
                    "sha256": str(item["sha256"]),
                    "classification": str(item["classification"]),
                },
            )
        uploaded_bytes += int(item["size_bytes"])
    return {
        "status": "COMPLETED",
        "object_count": len(plan),
        "uploaded_bytes": uploaded_bytes,
        "encryption": "aws:kms",
    }
