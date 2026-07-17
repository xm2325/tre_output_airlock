# Clinical–Genomic Ingestion Pipeline

This package adds an upstream data-engineering path to the TRE Output Airlock. It demonstrates how a synthetic FHIR delivery and a synthetic VCF delivery can be checked, de-identified, linked, recorded and published as research-ready tables before output disclosure review begins.

> **Safety boundary:** all records are synthetic. The package is not a clinical system, does not implement a complete FHIR or OMOP specification, and must not be used for real patient data.

## Problem

Clinical and genomic deliveries often arrive from different systems. Before researchers use them, a platform must check source integrity, validate identifiers, detect source-schema changes, remove direct identifiers, create stable pseudonyms, record data lineage, isolate failed deliveries and publish only complete runs.

## Demonstrated flow

```mermaid
flowchart LR
  A[Synthetic FHIR bundle] --> C[Versioned contract and reference checks]
  B[Synthetic VCF and manifest] --> D[Path, assembly and SHA-256 checks]
  C -->|breaking drift| Q[Quarantine evidence]
  C -->|additive drift| W[Recorded warning]
  C --> E[Deterministic pseudonymisation and date shifting]
  D --> F[Clinical-genomic linkage]
  D -->|invalid| Q
  E --> F
  W --> F
  F --> G[Bronze, silver and gold layers]
  G --> H[Contract report, metrics and lineage]
  H --> I[Atomic publish with _SUCCESS]
  I --> O[Operations JSON and HTML]
  I --> J[TRE research use]
  J --> K[Output Airlock]
```

## What is implemented

- a small FHIR R4 contract for `Patient`, `Condition`, `Observation` and `Specimen`;
- reference-integrity checks across FHIR resources;
- manifest validation for patient, specimen, genome assembly, path and SHA-256;
- a versioned schema contract with `PASS`, `WARN` and `FAIL` outcomes;
- a value-free SHA-256 schema fingerprint for every accepted delivery;
- breaking drift quarantined before manifest loading or transformation;
- additive drift accepted with explicit warning evidence;
- HMAC-based stable pseudonyms with a secret supplied at run time;
- deterministic patient-level date shifting that keeps within-person intervals;
- removal of name and address fields from research tables;
- bronze source capture, silver clinical tables and a gold joined cohort;
- restricted linkage data kept outside the research-ready gold layer;
- run IDs derived from source digests and pipeline version;
- repeatable execution, staging and atomic publication;
- quarantine evidence for invalid deliveries;
- source digests, contract version, schema fingerprint, code revision and run metrics;
- a Prefect flow with retry boundaries;
- an operations command that aggregates runs, quarantines, warnings and staging state;
- portable JSON and HTML operational evidence with no remote assets;
- Terraform for encrypted AWS landing, quarantine and curated buckets plus a dead-letter queue;
- CI checks for code, tests, sample execution, privacy assertions, operations evidence and Terraform validation.

## Run the pure-Python path

```bash
cd clinical_genomic_pipeline
python -m pip install -e .
python -m clinical_genomic_pipeline.cli \
  --fhir samples/fhir_bundle.json \
  --manifest samples/genomic_manifest.csv \
  --output build/demo \
  --secret 'replace-with-a-long-demo-secret'
```

Run it a second time with the same inputs. The pipeline returns the existing successful run rather than publishing a duplicate.

## Build operations evidence

```bash
clinical-genomic-operations \
  --output build/demo \
  --json build/demo/operations-summary.json \
  --html build/demo/operations-dashboard.html
```

The summary reports successful runs, quarantined deliveries, success rate, contract warnings, published sample count and incomplete staging directories. Alerts are generated when the configured success target is missed or evidence requires attention.

## Run with Prefect

```bash
python -m pip install -e '.[orchestration]'
python -c "from clinical_genomic_pipeline.flow import clinical_genomic_flow; clinical_genomic_flow('samples/fhir_bundle.json', 'samples/genomic_manifest.csv', 'build/prefect', 'replace-with-a-long-demo-secret')"
```

## Output contract

```text
build/demo/
├── quarantine/<run_id>/
│   ├── validation_issues.json
│   └── contract_report.json
├── operations-summary.json
├── operations-dashboard.html
└── runs/<run_id>/
    ├── bronze/
    ├── silver/
    ├── gold/research_cohort.csv
    ├── restricted/patient_linkage.csv
    ├── contract_report.json
    ├── lineage.json
    ├── metrics.json
    └── _SUCCESS
```

The `restricted` directory is present to show the security boundary. A production deployment would use separate permissions and storage, not only a directory boundary.

## Contract behaviour

| Observed change | Outcome | Publication behaviour |
|---|---|---|
| Expected fields and columns | `PASS` | Publish after normal validation |
| New field or manifest column | `WARN` | Publish and record the additive drift |
| Missing required field or column | `FAIL` | Quarantine before transformation |
| Invalid identifier, reference, file or checksum | validation error | Quarantine with issue codes |

The schema fingerprint contains field names and resource types only. It does not contain patient values.

## Failure cases covered by tests

- source checksum mismatch;
- invalid patient or specimen reference;
- duplicate resource and sample identifiers;
- unsupported genome assembly;
- path traversal outside the delivery directory;
- attempted use of a short pseudonymisation secret;
- rerun after a successful publication;
- additive schema drift with warning evidence;
- breaking manifest drift quarantined before loading;
- combined operations reporting for successful and quarantined runs.

## Production gaps

A real implementation would still require approved identity and access management, managed secrets and keys, complete FHIR profile validation, approved terminology services, transfer tooling such as Aspera or Globus, malware scanning, object-lock policy, managed Prefect infrastructure, central logs and alerts, data retention controls, formal privacy review and validation with representative source systems. The local HTML dashboard is evidence for this demonstration, not a production monitoring system.
