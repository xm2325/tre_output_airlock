"""Genomic file-manifest validation."""

from __future__ import annotations

import csv
from pathlib import Path

from .hashing import sha256_file
from .models import GenomicManifestRow, ValidationIssue

_REQUIRED_COLUMNS = {
    "sample_id",
    "patient_reference",
    "specimen_reference",
    "vcf_path",
    "expected_sha256",
    "assembly",
}
_ALLOWED_ASSEMBLIES = {"GRCh37", "GRCh38"}


def load_manifest(path: Path) -> list[GenomicManifestRow]:
    """Load a genomic delivery manifest."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = _REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"Manifest missing columns: {', '.join(sorted(missing))}")
        return [
            GenomicManifestRow(**{name: row[name] for name in _REQUIRED_COLUMNS})
            for row in reader
        ]


def validate_manifest(
    rows: list[GenomicManifestRow],
    base_directory: Path,
    patient_ids: set[str],
    specimen_ids: set[str],
) -> list[ValidationIssue]:
    """Validate identifiers, paths, assemblies and file digests."""
    issues: list[ValidationIssue] = []
    seen_samples: set[str] = set()
    base_resolved = base_directory.resolve()

    for row in rows:
        if row.sample_id in seen_samples:
            issues.append(
                ValidationIssue(
                    "GENOMIC_SAMPLE_DUPLICATE",
                    f"Duplicate sample_id: {row.sample_id}",
                    record_id=row.sample_id,
                )
            )
        seen_samples.add(row.sample_id)

        if row.patient_reference not in patient_ids:
            issues.append(
                ValidationIssue(
                    "GENOMIC_PATIENT_UNKNOWN",
                    f"Unknown patient_reference: {row.patient_reference}",
                    record_id=row.sample_id,
                )
            )
        if row.specimen_reference not in specimen_ids:
            issues.append(
                ValidationIssue(
                    "GENOMIC_SPECIMEN_UNKNOWN",
                    f"Unknown specimen_reference: {row.specimen_reference}",
                    record_id=row.sample_id,
                )
            )
        if row.assembly not in _ALLOWED_ASSEMBLIES:
            issues.append(
                ValidationIssue(
                    "GENOMIC_ASSEMBLY_UNSUPPORTED",
                    f"Unsupported assembly: {row.assembly}",
                    record_id=row.sample_id,
                )
            )

        candidate = (base_directory / row.vcf_path).resolve()
        if candidate != base_resolved and base_resolved not in candidate.parents:
            issues.append(
                ValidationIssue(
                    "GENOMIC_PATH_OUTSIDE_DELIVERY",
                    "vcf_path escapes the delivery directory",
                    record_id=row.sample_id,
                )
            )
            continue
        if candidate.suffix.lower() not in {".vcf", ".gz"}:
            issues.append(
                ValidationIssue(
                    "GENOMIC_FILE_TYPE_UNSUPPORTED",
                    f"Expected VCF or VCF.GZ file: {row.vcf_path}",
                    record_id=row.sample_id,
                )
            )
        if not candidate.is_file():
            issues.append(
                ValidationIssue(
                    "GENOMIC_FILE_MISSING",
                    f"Missing file: {row.vcf_path}",
                    record_id=row.sample_id,
                )
            )
            continue
        observed_sha256 = sha256_file(candidate)
        if observed_sha256.lower() != row.expected_sha256.lower():
            issues.append(
                ValidationIssue(
                    "GENOMIC_CHECKSUM_MISMATCH",
                    f"Checksum mismatch for {row.vcf_path}",
                    record_id=row.sample_id,
                )
            )
    return issues
