"""Build a small OMOP-aligned research model from normalised clinical records."""

from __future__ import annotations

import hashlib
from typing import Any

from .models import NormalisedClinicalData
from .terminology import map_source_code

_GENDER_CONCEPTS = {"female": 8532, "male": 8507}


def _numeric_id(value: str) -> int:
    """Create a stable positive 63-bit identifier for synthetic OMOP-shaped tables."""
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def build_omop_tables(
    clinical: NormalisedClinicalData,
    terminology_map: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Create person, condition, measurement and specimen tables."""
    person_ids = {
        str(record["person_id"]): _numeric_id(str(record["person_id"]))
        for record in clinical.people
    }

    people = [
        {
            "person_id": person_ids[str(record["person_id"])],
            "gender_concept_id": _GENDER_CONCEPTS.get(
                str(record.get("administrative_sex") or "").lower(), 0
            ),
            "year_of_birth": record.get("birth_year"),
            "person_source_value": record["person_id"],
            "gender_source_value": record.get("administrative_sex"),
        }
        for record in clinical.people
    ]

    conditions: list[dict[str, Any]] = []
    for record in clinical.conditions:
        source_system = str(record.get("source_system") or "")
        source_code = str(record.get("source_code") or "")
        mapping = map_source_code(terminology_map, source_system, source_code)
        conditions.append(
            {
                "condition_occurrence_id": _numeric_id(str(record["condition_id"])),
                "person_id": person_ids[str(record["person_id"])],
                "condition_concept_id": int(mapping["target_concept_id"]),
                "condition_start_date": record.get("condition_start_date"),
                "condition_source_value": source_code,
                "condition_source_vocabulary": mapping["target_vocabulary"],
                "mapping_status": mapping["mapping_status"],
            }
        )

    measurements: list[dict[str, Any]] = []
    for record in clinical.measurements:
        source_system = str(record.get("source_system") or "")
        source_code = str(record.get("source_code") or "")
        mapping = map_source_code(terminology_map, source_system, source_code)
        measurements.append(
            {
                "measurement_id": _numeric_id(str(record["measurement_id"])),
                "person_id": person_ids[str(record["person_id"])],
                "measurement_concept_id": int(mapping["target_concept_id"]),
                "measurement_date": record.get("measurement_date"),
                "value_as_number": record.get("value"),
                "unit_source_value": record.get("unit"),
                "measurement_source_value": source_code,
                "measurement_source_vocabulary": mapping["target_vocabulary"],
                "mapping_status": mapping["mapping_status"],
            }
        )

    specimens = [
        {
            "specimen_id": _numeric_id(str(record["specimen_id"])),
            "person_id": person_ids[str(record["person_id"])],
            "specimen_date": record.get("collected_date"),
            "specimen_source_value": record["specimen_id"],
        }
        for record in clinical.specimens
    ]

    return {
        "person": people,
        "condition_occurrence": conditions,
        "measurement": measurements,
        "specimen": specimens,
    }


def build_omop_quality_report(
    tables: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Check primary keys, foreign keys and required fields."""
    people = tables["person"]
    person_ids = {int(record["person_id"]) for record in people}
    duplicate_person_ids = len(people) - len(person_ids)
    orphan_count = 0
    required_null_count = 0

    required_by_table = {
        "person": ("person_id", "year_of_birth"),
        "condition_occurrence": (
            "condition_occurrence_id",
            "person_id",
            "condition_start_date",
        ),
        "measurement": ("measurement_id", "person_id", "measurement_date"),
        "specimen": ("specimen_id", "person_id", "specimen_date"),
    }
    for table_name, rows in tables.items():
        required = required_by_table[table_name]
        required_null_count += sum(
            value is None or value == ""
            for row in rows
            for value in (row.get(field) for field in required)
        )
        if table_name != "person":
            orphan_count += sum(
                int(row["person_id"]) not in person_ids for row in rows
            )

    failures = duplicate_person_ids + orphan_count + required_null_count
    return {
        "status": "PASS" if failures == 0 else "FAIL",
        "row_counts": {name: len(rows) for name, rows in tables.items()},
        "duplicate_person_id_count": duplicate_person_ids,
        "orphan_person_reference_count": orphan_count,
        "required_null_count": required_null_count,
    }
