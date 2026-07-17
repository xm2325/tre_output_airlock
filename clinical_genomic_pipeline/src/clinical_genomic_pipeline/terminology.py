"""Versioned terminology-map loading and mapping-quality reporting."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def load_terminology_map(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Load a small, explicit source-code to OMOP concept mapping table."""
    required = {
        "source_system",
        "source_code",
        "target_concept_id",
        "target_vocabulary",
        "target_domain",
        "mapping_status",
    }
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Terminology map missing columns: {', '.join(sorted(missing))}")
        output: dict[tuple[str, str], dict[str, Any]] = {}
        for row in reader:
            key = (row["source_system"], row["source_code"])
            if key in output:
                raise ValueError(f"Duplicate terminology mapping: {key[0]}|{key[1]}")
            output[key] = {
                "target_concept_id": int(row["target_concept_id"]),
                "target_vocabulary": row["target_vocabulary"],
                "target_domain": row["target_domain"],
                "mapping_status": row["mapping_status"],
            }
    return output


def map_source_code(
    mapping: dict[tuple[str, str], dict[str, Any]],
    source_system: str | None,
    source_code: str | None,
) -> dict[str, Any]:
    """Return an explicit mapping result; unknown codes remain review-required."""
    system = source_system or ""
    code = source_code or ""
    mapped = mapping.get((system, code))
    if mapped is None:
        return {
            "target_concept_id": 0,
            "target_vocabulary": "UNMAPPED",
            "target_domain": "Unknown",
            "mapping_status": "REVIEW_REQUIRED",
        }
    return mapped


def build_terminology_report(
    conditions: list[dict[str, Any]],
    measurements: list[dict[str, Any]],
    mapping: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    """Summarise mapping coverage without copying clinical values into monitoring output."""
    observed = [
        (str(record.get("source_system") or ""), str(record.get("source_code") or ""))
        for record in [*conditions, *measurements]
    ]
    distinct = sorted(set(observed))
    mapped_count = 0
    review_required: list[dict[str, str]] = []
    by_vocabulary: dict[str, int] = {}

    for system, code in distinct:
        result = map_source_code(mapping, system, code)
        vocabulary = str(result["target_vocabulary"])
        by_vocabulary[vocabulary] = by_vocabulary.get(vocabulary, 0) + 1
        if result["mapping_status"] == "MAPPED" and int(result["target_concept_id"]) > 0:
            mapped_count += 1
        else:
            review_required.append({"source_system": system, "source_code": code})

    total = len(distinct)
    coverage = mapped_count / total if total else 1.0
    return {
        "status": "PASS" if coverage == 1.0 else "WARN",
        "distinct_code_count": total,
        "mapped_code_count": mapped_count,
        "review_required_count": len(review_required),
        "mapping_coverage": round(coverage, 6),
        "by_vocabulary": dict(sorted(by_vocabulary.items())),
        "review_required": review_required,
    }
