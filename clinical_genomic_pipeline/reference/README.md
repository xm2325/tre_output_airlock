# Terminology reference data

`terminology_map.csv` is a deliberately small, versioned mapping fixture for the synthetic pipeline.

The sample mappings are:

- SNOMED CT `44054006` → OMOP standard concept `201826` (`Type 2 diabetes mellitus`);
- LOINC `4548-4` → OMOP standard concept `3004410` (`Hemoglobin A1c measurement`).

The mapping file is not a replacement for an approved terminology service or a licensed vocabulary release. Production work would pin the OHDSI vocabulary version, record mapping provenance and approvals, validate domain compatibility, monitor deprecated concepts and route unresolved codes to clinical terminology review.
