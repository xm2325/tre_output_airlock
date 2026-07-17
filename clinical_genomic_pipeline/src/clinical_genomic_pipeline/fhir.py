"""Small FHIR R4 validation and research-table transformation layer."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .hashing import deterministic_date_shift_days, pseudonymise
from .models import NormalisedClinicalData, ValidationIssue

_ALLOWED_RESOURCE_TYPES = {"Patient", "Condition", "Observation", "Specimen"}


def _reference_id(reference: str, expected_type: str) -> str | None:
    prefix = f"{expected_type}/"
    if not reference.startswith(prefix):
        return None
    identifier = reference.removeprefix(prefix)
    return identifier or None


def _shift_date(raw_value: str | None, shift_days: int) -> str | None:
    if not raw_value:
        return None
    try:
        parsed = date.fromisoformat(raw_value)
    except ValueError:
        return None
    return (parsed + timedelta(days=shift_days)).isoformat()


def validate_bundle(bundle: dict[str, Any]) -> list[ValidationIssue]:
    """Validate the small FHIR contract used by this demonstration."""
    issues: list[ValidationIssue] = []
    if bundle.get("resourceType") != "Bundle":
        return [ValidationIssue("FHIR_NOT_BUNDLE", "FHIR input must be a Bundle")]

    entries = bundle.get("entry")
    if not isinstance(entries, list):
        return [ValidationIssue("FHIR_ENTRIES_MISSING", "Bundle.entry must be a list")]

    resource_ids: dict[str, set[str]] = {
        resource_type: set() for resource_type in _ALLOWED_RESOURCE_TYPES
    }
    resources: list[dict[str, Any]] = []

    for index, entry in enumerate(entries):
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict):
            issues.append(
                ValidationIssue(
                    "FHIR_RESOURCE_MISSING",
                    "Entry has no resource object",
                    record_id=str(index),
                )
            )
            continue
        resource_type = resource.get("resourceType")
        resource_id = resource.get("id")
        if resource_type not in _ALLOWED_RESOURCE_TYPES:
            issues.append(
                ValidationIssue(
                    "FHIR_RESOURCE_TYPE_UNSUPPORTED",
                    f"Unsupported resource type: {resource_type}",
                    record_id=str(resource_id or index),
                )
            )
            continue
        if not isinstance(resource_id, str) or not resource_id:
            issues.append(
                ValidationIssue(
                    "FHIR_ID_MISSING",
                    f"{resource_type} resource requires id",
                    record_id=str(index),
                )
            )
            continue
        if resource_id in resource_ids[resource_type]:
            issues.append(
                ValidationIssue(
                    "FHIR_ID_DUPLICATE",
                    f"Duplicate {resource_type} id: {resource_id}",
                    record_id=resource_id,
                )
            )
        resource_ids[resource_type].add(resource_id)
        resources.append(resource)

    for resource in resources:
        resource_type = str(resource["resourceType"])
        resource_id = str(resource["id"])
        if resource_type in {"Condition", "Observation", "Specimen"}:
            subject = resource.get("subject")
            reference = subject.get("reference") if isinstance(subject, dict) else None
            patient_id = _reference_id(reference, "Patient") if isinstance(reference, str) else None
            if patient_id is None or patient_id not in resource_ids["Patient"]:
                issues.append(
                    ValidationIssue(
                        "FHIR_SUBJECT_REFERENCE_INVALID",
                        f"{resource_type}/{resource_id} does not reference a known Patient",
                        record_id=resource_id,
                    )
                )
    return issues


def transform_bundle(bundle: dict[str, Any], secret: str) -> NormalisedClinicalData:
    """Create de-identified research tables from the validated FHIR bundle."""
    issues = validate_bundle(bundle)
    if issues:
        messages = "; ".join(issue.message for issue in issues)
        raise ValueError(f"FHIR validation failed: {messages}")

    output = NormalisedClinicalData()
    patient_pseudonyms: dict[str, str] = {}
    patient_shifts: dict[str, int] = {}

    resources = [entry["resource"] for entry in bundle["entry"]]
    for resource in resources:
        if resource["resourceType"] != "Patient":
            continue
        raw_id = str(resource["id"])
        person_id = pseudonymise(raw_id, secret, prefix="PERSON")
        patient_pseudonyms[raw_id] = person_id
        patient_shifts[raw_id] = deterministic_date_shift_days(raw_id, secret)
        birth_date = resource.get("birthDate")
        birth_year = None
        if isinstance(birth_date, str) and len(birth_date) >= 4 and birth_date[:4].isdigit():
            birth_year = int(birth_date[:4])
        output.people.append(
            {
                "person_id": person_id,
                "birth_year": birth_year,
                "administrative_sex": resource.get("gender"),
            }
        )
        output.patient_linkage.append({"raw_patient_id": raw_id, "person_id": person_id})

    for resource in resources:
        resource_type = resource["resourceType"]
        if resource_type == "Patient":
            continue
        subject = resource.get("subject", {}).get("reference", "")
        raw_patient_id = _reference_id(subject, "Patient")
        if raw_patient_id is None:
            raise ValueError(f"Invalid subject reference in {resource_type}/{resource['id']}")
        person_id = patient_pseudonyms[raw_patient_id]
        shift_days = patient_shifts[raw_patient_id]

        if resource_type == "Condition":
            coding = resource.get("code", {}).get("coding", [{}])[0]
            output.conditions.append(
                {
                    "condition_id": pseudonymise(str(resource["id"]), secret, prefix="COND"),
                    "person_id": person_id,
                    "source_system": coding.get("system"),
                    "source_code": coding.get("code"),
                    "display": coding.get("display"),
                    "condition_start_date": _shift_date(
                        resource.get("onsetDateTime"), shift_days
                    ),
                }
            )
        elif resource_type == "Observation":
            coding = resource.get("code", {}).get("coding", [{}])[0]
            quantity = resource.get("valueQuantity", {})
            output.measurements.append(
                {
                    "measurement_id": pseudonymise(str(resource["id"]), secret, prefix="MEAS"),
                    "person_id": person_id,
                    "source_system": coding.get("system"),
                    "source_code": coding.get("code"),
                    "display": coding.get("display"),
                    "value": quantity.get("value"),
                    "unit": quantity.get("unit"),
                    "measurement_date": _shift_date(
                        resource.get("effectiveDateTime"), shift_days
                    ),
                }
            )
        elif resource_type == "Specimen":
            raw_specimen_id = str(resource["id"])
            specimen_id = pseudonymise(raw_specimen_id, secret, prefix="SPEC")
            output.specimens.append(
                {
                    "specimen_id": specimen_id,
                    "person_id": person_id,
                    "collected_date": _shift_date(
                        resource.get("collection", {}).get("collectedDateTime"), shift_days
                    ),
                }
            )
            output.specimen_linkage.append(
                {
                    "raw_specimen_id": raw_specimen_id,
                    "specimen_id": specimen_id,
                }
            )

    return output
