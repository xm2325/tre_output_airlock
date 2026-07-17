"""Transfer-receipt creation and validation for delivered clinical-genomic files."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .hashing import sha256_file
from .models import ValidationIssue

_ALLOWED_TOOLS = {"ASPERA", "GLOBUS", "LOCAL"}


def _resolve_delivery_path(delivery_root: Path, relative_path: str) -> Path | None:
    root = delivery_root.resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    return candidate


def build_transfer_receipt(
    *,
    delivery_root: Path,
    relative_paths: list[str],
    output_path: Path,
    tool: str,
    transfer_id: str,
    source_endpoint: str,
    destination_endpoint: str,
) -> dict[str, Any]:
    """Create receiver-side transfer evidence from files present in a delivery directory."""
    tool_value = tool.upper()
    if tool_value not in _ALLOWED_TOOLS:
        raise ValueError(f"tool must be one of: {', '.join(sorted(_ALLOWED_TOOLS))}")
    if not transfer_id.strip():
        raise ValueError("transfer_id must not be empty")

    files: list[dict[str, Any]] = []
    for relative_path in relative_paths:
        candidate = _resolve_delivery_path(delivery_root, relative_path)
        if candidate is None:
            raise ValueError(f"Path escapes delivery root: {relative_path}")
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        size_bytes = candidate.stat().st_size
        files.append(
            {
                "path": relative_path,
                "size_bytes": size_bytes,
                "bytes_transferred": size_bytes,
                "sha256": sha256_file(candidate),
                "attempts": 1,
                "resumed": False,
            }
        )

    receipt: dict[str, Any] = {
        "schema_version": "transfer-receipt/1.0",
        "transfer_id": transfer_id,
        "tool": tool_value,
        "status": "COMPLETED",
        "source_endpoint": source_endpoint,
        "destination_endpoint": destination_endpoint,
        "completed_at": datetime.now(UTC).isoformat(),
        "files": files,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def validate_transfer_receipt(
    *,
    receipt_path: Path,
    delivery_root: Path,
    expected_files: list[Path],
) -> tuple[dict[str, Any], list[ValidationIssue]]:
    """Check transfer status, file coverage, byte counts, paths and receiver-side digests."""
    issues: list[ValidationIssue] = []
    if not receipt_path.is_file():
        report = {"status": "FAIL", "schema_version": "transfer-receipt/1.0"}
        return report, [ValidationIssue("TRANSFER_RECEIPT_MISSING", "Transfer receipt is missing")]

    value: Any = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        report = {"status": "FAIL", "schema_version": "transfer-receipt/1.0"}
        return report, [ValidationIssue("TRANSFER_RECEIPT_INVALID", "Transfer receipt must be an object")]
    receipt: dict[str, Any] = value

    tool = str(receipt.get("tool", "")).upper()
    if tool not in _ALLOWED_TOOLS:
        issues.append(
            ValidationIssue("TRANSFER_TOOL_UNSUPPORTED", f"Unsupported transfer tool: {tool or 'missing'}")
        )
    if receipt.get("status") != "COMPLETED":
        issues.append(
            ValidationIssue("TRANSFER_NOT_COMPLETED", "Transfer receipt status must be COMPLETED")
        )

    file_values = receipt.get("files")
    file_entries = file_values if isinstance(file_values, list) else []
    by_path = {
        str(entry.get("path")): entry
        for entry in file_entries
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }

    root = delivery_root.resolve()
    expected_relative_paths: list[str] = []
    total_bytes = 0
    retry_count = 0
    resumed_file_count = 0

    for expected_file in expected_files:
        resolved = expected_file.resolve()
        try:
            relative_path = resolved.relative_to(root).as_posix()
        except ValueError:
            issues.append(
                ValidationIssue(
                    "TRANSFER_EXPECTED_PATH_OUTSIDE_DELIVERY",
                    f"Expected path is outside delivery root: {expected_file}",
                )
            )
            continue
        expected_relative_paths.append(relative_path)
        entry = by_path.get(relative_path)
        if entry is None:
            issues.append(
                ValidationIssue(
                    "TRANSFER_FILE_NOT_RECEIPTED",
                    f"Expected file is absent from receipt: {relative_path}",
                    record_id=relative_path,
                )
            )
            continue
        if not resolved.is_file():
            issues.append(
                ValidationIssue(
                    "TRANSFER_FILE_MISSING",
                    f"Receipted file is missing: {relative_path}",
                    record_id=relative_path,
                )
            )
            continue

        observed_size = resolved.stat().st_size
        observed_sha256 = sha256_file(resolved)
        receipted_size = int(entry.get("size_bytes", -1))
        bytes_transferred = int(entry.get("bytes_transferred", -1))
        receipted_sha256 = str(entry.get("sha256", "")).lower()
        attempts = int(entry.get("attempts", 1))
        total_bytes += observed_size
        retry_count += max(0, attempts - 1)
        resumed_file_count += int(bool(entry.get("resumed", False)))

        if receipted_size != observed_size or bytes_transferred != observed_size:
            issues.append(
                ValidationIssue(
                    "TRANSFER_BYTE_COUNT_MISMATCH",
                    f"Byte count mismatch for {relative_path}",
                    record_id=relative_path,
                )
            )
        if receipted_sha256 != observed_sha256:
            issues.append(
                ValidationIssue(
                    "TRANSFER_CHECKSUM_MISMATCH",
                    f"Transfer checksum mismatch for {relative_path}",
                    record_id=relative_path,
                )
            )

    unexpected_paths = sorted(set(by_path) - set(expected_relative_paths))
    report: dict[str, Any] = {
        "schema_version": str(receipt.get("schema_version", "unknown")),
        "status": "PASS" if not issues else "FAIL",
        "transfer_id": str(receipt.get("transfer_id", "")),
        "tool": tool,
        "source_endpoint": str(receipt.get("source_endpoint", "")),
        "destination_endpoint": str(receipt.get("destination_endpoint", "")),
        "completed_at": str(receipt.get("completed_at", "")),
        "expected_file_count": len(expected_relative_paths),
        "receipted_file_count": len(by_path),
        "unexpected_paths": unexpected_paths,
        "total_bytes": total_bytes,
        "retry_count": retry_count,
        "resumed_file_count": resumed_file_count,
        "issue_codes": sorted({issue.code for issue in issues}),
    }
    return report, issues


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build receiver-side transfer evidence")
    parser.add_argument("--delivery-root", type=Path, required=True)
    parser.add_argument("--file", action="append", dest="files", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tool", choices=sorted(_ALLOWED_TOOLS), required=True)
    parser.add_argument("--transfer-id", required=True)
    parser.add_argument("--source-endpoint", default="synthetic-source")
    parser.add_argument("--destination-endpoint", default="synthetic-landing-zone")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    receipt = build_transfer_receipt(
        delivery_root=args.delivery_root,
        relative_paths=args.files,
        output_path=args.output,
        tool=args.tool,
        transfer_id=args.transfer_id,
        source_endpoint=args.source_endpoint,
        destination_endpoint=args.destination_endpoint,
    )
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
