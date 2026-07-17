"""Versioned data-contract inspection and schema-drift classification."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .hashing import sha256_text

CONTRACT_VERSION = "clinical-genomic/1.1"

_REQUIRED_BUNDLE_FIELDS = {"resourceType", "entry"}
_ALLOWED_BUNDLE_FIELDS = {
    "resourceType",
    "id",
    "meta",
    "identifier",
    "type",
    "timestamp",
    "entry",
}
_ALLOWED_ENTRY_FIELDS = {"fullUrl", "resource", "search", "request", "response"}
_REQUIRED_MANIFEST_COLUMNS = {
    "sample_id",
    "patient_reference",
    "specimen_reference",
    "vcf_path",
    "expected_sha256",
    "assembly",
}
_RESOURCE_REQUIRED_FIELDS: dict[str, set[str]] = {
    "Patient": {"resourceType", "id"},
    "Condition": {"resourceType", "id", "subject", "code"},
    "Observation": {"resourceType", "id", "subject", "code"},
    "Specimen": {"resourceType", "id", "subject"},
}
_RESOURCE_ALLOWED_FIELDS: dict[str, set[str]] = {
    "Patient": {
        "resourceType",
        "id",
        "meta",
        "identifier",
        "name",
        "telecom",
        "gender",
        "birthDate",
        "deceasedBoolean",
        "address",
        "managingOrganization",
    },
    "Condition": {
        "resourceType",
        "id",
        "meta",
        "identifier",
        "clinicalStatus",
        "verificationStatus",
        "category",
        "severity",
        "code",
        "bodySite",
        "subject",
        "encounter",
        "onsetDateTime",
        "onsetPeriod",
        "recordedDate",
    },
    "Observation": {
        "resourceType",
        "id",
        "meta",
        "identifier",
        "status",
        "category",
        "code",
        "subject",
        "encounter",
        "effectiveDateTime",
        "effectivePeriod",
        "issued",
        "performer",
        "valueQuantity",
        "valueCodeableConcept",
        "interpretation",
        "referenceRange",
        "specimen",
    },
    "Specimen": {
        "resourceType",
        "id",
        "meta",
        "identifier",
        "status",
        "type",
        "subject",
        "receivedTime",
        "collection",
        "container",
    },
}


def _drift(
    *,
    kind: str,
    scope: str,
    field: str,
    message: str,
) -> dict[str, str]:
    return {"kind": kind, "scope": scope, "field": field, "message": message}


def _manifest_columns(path: Path) -> set[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return set(reader.fieldnames or [])


def evaluate_contract(bundle: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    """Return a value-free contract report with breaking and additive drift."""
    drift: list[dict[str, str]] = []
    bundle_fields = set(bundle)

    for field in sorted(_REQUIRED_BUNDLE_FIELDS - bundle_fields):
        drift.append(
            _drift(
                kind="BREAKING",
                scope="FHIR.Bundle",
                field=field,
                message=f"Required Bundle field is missing: {field}",
            )
        )
    for field in sorted(bundle_fields - _ALLOWED_BUNDLE_FIELDS):
        drift.append(
            _drift(
                kind="ADDITIVE",
                scope="FHIR.Bundle",
                field=field,
                message=f"Unrecognised additive Bundle field: {field}",
            )
        )

    observed_resource_fields: dict[str, set[str]] = {}
    entries = bundle.get("entry")
    if isinstance(entries, list):
        for index, entry in enumerate(entries):
            entry_fields = set(entry) if isinstance(entry, dict) else set()
            for field in sorted(entry_fields - _ALLOWED_ENTRY_FIELDS):
                drift.append(
                    _drift(
                        kind="ADDITIVE",
                        scope=f"FHIR.Bundle.entry[{index}]",
                        field=field,
                        message=f"Unrecognised additive entry field: {field}",
                    )
                )
            resource = entry.get("resource") if isinstance(entry, dict) else None
            if not isinstance(resource, dict):
                continue
            resource_type_value = resource.get("resourceType")
            if not isinstance(resource_type_value, str):
                continue
            resource_type = resource_type_value
            fields = set(resource)
            observed_resource_fields.setdefault(resource_type, set()).update(fields)
            required = _RESOURCE_REQUIRED_FIELDS.get(resource_type)
            allowed = _RESOURCE_ALLOWED_FIELDS.get(resource_type)
            if required is None or allowed is None:
                continue
            for field in sorted(required - fields):
                drift.append(
                    _drift(
                        kind="BREAKING",
                        scope=f"FHIR.{resource_type}",
                        field=field,
                        message=f"Required {resource_type} field is missing: {field}",
                    )
                )
            for field in sorted(fields - allowed):
                drift.append(
                    _drift(
                        kind="ADDITIVE",
                        scope=f"FHIR.{resource_type}",
                        field=field,
                        message=f"Unrecognised additive {resource_type} field: {field}",
                    )
                )

    manifest_columns = _manifest_columns(manifest_path)
    for field in sorted(_REQUIRED_MANIFEST_COLUMNS - manifest_columns):
        drift.append(
            _drift(
                kind="BREAKING",
                scope="GenomicManifest",
                field=field,
                message=f"Required genomic manifest column is missing: {field}",
            )
        )
    for field in sorted(manifest_columns - _REQUIRED_MANIFEST_COLUMNS):
        drift.append(
            _drift(
                kind="ADDITIVE",
                scope="GenomicManifest",
                field=field,
                message=f"Unrecognised additive genomic manifest column: {field}",
            )
        )

    fingerprint_material = {
        "bundle_fields": sorted(bundle_fields),
        "resource_fields": {
            resource_type: sorted(fields)
            for resource_type, fields in sorted(observed_resource_fields.items())
        },
        "manifest_columns": sorted(manifest_columns),
    }
    fingerprint = sha256_text(json.dumps(fingerprint_material, sort_keys=True))
    breaking_count = sum(item["kind"] == "BREAKING" for item in drift)
    warning_count = sum(item["kind"] == "ADDITIVE" for item in drift)
    status = "FAIL" if breaking_count else "WARN" if warning_count else "PASS"

    return {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "schema_fingerprint": fingerprint,
        "breaking_count": breaking_count,
        "warning_count": warning_count,
        "drift": drift,
        "observed_schema": fingerprint_material,
    }
