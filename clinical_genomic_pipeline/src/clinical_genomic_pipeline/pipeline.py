"""Atomic, repeatable clinical-genomic pipeline."""

from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from .fhir import transform_bundle, validate_bundle
from .genomics import load_manifest, validate_manifest
from .hashing import pseudonymise, sha256_file, sha256_text
from .lineage import build_lineage_manifest
from .models import NormalisedClinicalData, PipelineResult, ValidationIssue


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_csv(path: Path, records: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def _resource_ids(bundle: dict[str, Any], resource_type: str) -> set[str]:
    return {
        str(entry["resource"]["id"])
        for entry in bundle["entry"]
        if entry["resource"].get("resourceType") == resource_type
    }


def _run_id(fhir_path: Path, manifest_path: Path) -> str:
    material = "|".join(
        [
            "pipeline-version=0.1.0",
            sha256_file(fhir_path),
            sha256_file(manifest_path),
        ]
    )
    return sha256_text(material)[:16]


def _issues_as_dicts(issues: list[ValidationIssue]) -> list[dict[str, str | None]]:
    return [
        {
            "code": issue.code,
            "message": issue.message,
            "severity": issue.severity,
            "record_id": issue.record_id,
        }
        for issue in issues
    ]


def _build_cohort(
    clinical: NormalisedClinicalData,
    manifest_rows: list[Any],
    secret: str,
) -> list[dict[str, Any]]:
    patient_to_person = {
        row["raw_patient_id"]: row["person_id"] for row in clinical.patient_linkage
    }
    specimen_to_pseudonym = {
        row["raw_specimen_id"]: row["specimen_id"] for row in clinical.specimen_linkage
    }
    return [
        {
            "sample_id": pseudonymise(row.sample_id, secret, prefix="SAMPLE"),
            "person_id": patient_to_person[row.patient_reference],
            "specimen_id": specimen_to_pseudonym[row.specimen_reference],
            "assembly": row.assembly,
            "genomic_file_sha256": row.expected_sha256.lower(),
        }
        for row in manifest_rows
    ]


def run_pipeline(
    *,
    fhir_path: Path,
    genomic_manifest_path: Path,
    output_root: Path,
    secret: str | None = None,
) -> PipelineResult:
    """Validate, de-identify, join and publish one synthetic delivery."""
    start = time.perf_counter()
    secret_value: str = secret if secret is not None else (
        os.getenv("PIPELINE_PSEUDONYMISATION_SECRET") or ""
    )
    if len(secret_value) < 16:
        raise ValueError("Provide a pseudonymisation secret with at least 16 characters")

    fhir_path = fhir_path.resolve()
    genomic_manifest_path = genomic_manifest_path.resolve()
    delivery_directory = genomic_manifest_path.parent
    output_root.mkdir(parents=True, exist_ok=True)

    run_id = _run_id(fhir_path, genomic_manifest_path)
    final_directory = output_root / "runs" / run_id
    success_marker = final_directory / "_SUCCESS"
    if success_marker.is_file():
        existing_metrics = json.loads(
            (final_directory / "metrics.json").read_text(encoding="utf-8")
        )
        return PipelineResult(
            run_id=run_id,
            run_directory=final_directory,
            reused_existing_run=True,
            people_count=int(existing_metrics["people_count"]),
            sample_count=int(existing_metrics["sample_count"]),
            issue_count=int(existing_metrics["issue_count"]),
        )

    bundle = json.loads(fhir_path.read_text(encoding="utf-8"))
    fhir_issues = validate_bundle(bundle)
    manifest_rows = load_manifest(genomic_manifest_path)
    genomic_issues = validate_manifest(
        manifest_rows,
        delivery_directory,
        _resource_ids(bundle, "Patient"),
        _resource_ids(bundle, "Specimen"),
    )
    issues = [*fhir_issues, *genomic_issues]
    if issues:
        quarantine_directory = output_root / "quarantine" / run_id
        quarantine_directory.mkdir(parents=True, exist_ok=True)
        _write_json(quarantine_directory / "validation_issues.json", _issues_as_dicts(issues))
        raise ValueError(f"Delivery quarantined with {len(issues)} validation issue(s)")

    clinical = transform_bundle(bundle, secret_value)
    cohort = _build_cohort(clinical, manifest_rows, secret_value)
    genomic_files = [(delivery_directory / row.vcf_path).resolve() for row in manifest_rows]

    (output_root / "runs").mkdir(parents=True, exist_ok=True)
    temporary_parent = output_root / ".staging"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    staging_directory = Path(tempfile.mkdtemp(prefix=f"{run_id}-", dir=temporary_parent))
    try:
        bronze = staging_directory / "bronze"
        silver = staging_directory / "silver"
        gold = staging_directory / "gold"
        restricted = staging_directory / "restricted"
        for directory in (bronze, silver, gold, restricted):
            directory.mkdir(parents=True, exist_ok=True)

        shutil.copy2(fhir_path, bronze / "fhir_bundle.json")
        shutil.copy2(genomic_manifest_path, bronze / "genomic_manifest.csv")
        _write_jsonl(silver / "person.jsonl", clinical.people)
        _write_jsonl(silver / "condition.jsonl", clinical.conditions)
        _write_jsonl(silver / "measurement.jsonl", clinical.measurements)
        _write_jsonl(silver / "specimen.jsonl", clinical.specimens)
        _write_csv(
            gold / "research_cohort.csv",
            cohort,
            ["sample_id", "person_id", "specimen_id", "assembly", "genomic_file_sha256"],
        )
        _write_csv(
            restricted / "patient_linkage.csv",
            clinical.patient_linkage,
            ["raw_patient_id", "person_id"],
        )
        _write_csv(
            restricted / "specimen_linkage.csv",
            clinical.specimen_linkage,
            ["raw_specimen_id", "specimen_id"],
        )
        (restricted / "README.txt").write_text(
            "Restricted linkage material. Do not publish to the research zone.\n",
            encoding="utf-8",
        )

        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
        metrics: dict[str, Any] = {
            "people_count": len(clinical.people),
            "condition_count": len(clinical.conditions),
            "measurement_count": len(clinical.measurements),
            "specimen_count": len(clinical.specimens),
            "sample_count": len(cohort),
            "issue_count": 0,
            "processing_time_ms": elapsed_ms,
        }
        _write_json(staging_directory / "metrics.json", metrics)
        lineage = build_lineage_manifest(
            run_id=run_id,
            fhir_path=fhir_path,
            genomic_manifest_path=genomic_manifest_path,
            genomic_files=genomic_files,
            metrics=metrics,
        )
        _write_json(staging_directory / "lineage.json", lineage)
        (staging_directory / "_SUCCESS").write_text("ok\n", encoding="utf-8")

        if final_directory.exists():
            shutil.rmtree(final_directory)
        staging_directory.replace(final_directory)
    except Exception:
        shutil.rmtree(staging_directory, ignore_errors=True)
        raise

    return PipelineResult(
        run_id=run_id,
        run_directory=final_directory,
        reused_existing_run=False,
        people_count=len(clinical.people),
        sample_count=len(cohort),
        issue_count=0,
    )
