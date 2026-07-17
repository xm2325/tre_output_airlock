"""Typed records used by the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GenomicManifestRow:
    sample_id: str
    patient_reference: str
    specimen_reference: str
    vcf_path: str
    expected_sha256: str
    assembly: str


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = "ERROR"
    record_id: str | None = None


@dataclass
class NormalisedClinicalData:
    people: list[dict[str, Any]] = field(default_factory=list)
    conditions: list[dict[str, Any]] = field(default_factory=list)
    measurements: list[dict[str, Any]] = field(default_factory=list)
    specimens: list[dict[str, Any]] = field(default_factory=list)
    patient_linkage: list[dict[str, str]] = field(default_factory=list)
    specimen_linkage: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class PipelineResult:
    run_id: str
    run_directory: Path
    reused_existing_run: bool
    people_count: int
    sample_count: int
    issue_count: int
    warning_count: int = 0
