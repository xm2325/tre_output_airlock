# Clinical–Genomic Platform Extension

## Decision summary

The TRE Output Airlock already demonstrates controlled release after research analysis. This extension adds the upstream half of the data path: receiving synthetic clinical and genomic source data, checking delivery integrity, removing direct identifiers, producing research-ready tables and recording source lineage.

## User and operational questions

| Question | Demonstrated answer |
|---|---|
| Did the delivered genomic file arrive without alteration? | The manifest digest is checked against a streamed SHA-256 calculation. |
| Do clinical resources and genomic rows refer to known people and specimens? | FHIR references and manifest foreign keys are checked before transformation. |
| Can direct names or addresses enter the research-ready table? | The normaliser selects only allowed fields and replaces patient, specimen and sample identifiers. |
| Can an incomplete run look successful? | Data is written to a staging directory and published atomically only after metrics and lineage are complete. |
| What happens when validation fails? | The delivery is not published; machine-readable issues are written under quarantine. |
| Can the same delivery be processed twice? | A run ID is derived from source digests and pipeline version, and `_SUCCESS` causes safe reuse. |
| Can an operator trace an output to source files and code? | `lineage.json` records source paths, sizes, digests, configuration digest and code revision. |
| Is the raw-to-pseudonym link mixed with research data? | It is written to a separate restricted zone and excluded from the gold cohort. |

## Data contract

The demonstration accepts a FHIR `Bundle` with four resource types:

- `Patient` supplies a source identifier, year of birth and administrative sex;
- `Condition` carries a coded diagnosis and onset date;
- `Observation` carries a coded measurement, value, unit and date;
- `Specimen` links a collected sample to a patient.

The genomic manifest contains:

```text
sample_id
patient_reference
specimen_reference
vcf_path
expected_sha256
assembly
```

The patient and specimen fields act as foreign keys into the FHIR delivery. `GRCh37` and `GRCh38` are accepted in the demo.

## De-identification boundary

The package demonstrates four controls:

1. HMAC-based stable pseudonyms use a run-time secret rather than a plain hash.
2. Patient names and addresses are not selected into research tables.
3. Dates receive one deterministic shift per patient, which preserves intervals within that patient.
4. The source-to-pseudonym table is written to a restricted path and is not present in the gold cohort.

This is not a complete anonymisation method. A production service would need a formal privacy model, managed keys, access separation, review of rare attributes, approved retention rules and testing against real source profiles.

## Reliability controls

- streamed file hashing avoids loading a genomic file into memory;
- path resolution blocks manifest entries that escape the delivery directory;
- duplicate resource and sample IDs fail validation;
- source-reference checks run before any join;
- staging plus atomic rename prevents partial publication;
- a successful run can be replayed without duplicate output;
- Prefect separates the delivery task and supplies retry policy;
- metrics and lineage are produced for each successful run;
- CI runs both a valid delivery and an invalid-checksum case.

## AWS mapping

The Terraform baseline maps local zones to managed services:

| Local path | AWS baseline |
|---|---|
| source delivery | encrypted landing S3 bucket |
| validation failure | encrypted quarantine S3 bucket |
| gold research tables | encrypted curated S3 bucket |
| patient linkage | encrypted restricted S3 bucket with separate access policy |
| pending delivery | encrypted SQS queue |
| repeated failure | encrypted dead-letter queue |

A production design would add private endpoints, workload identity, per-zone roles, object-lock choices, CloudTrail data events, CloudWatch alerts, malware scanning and central security monitoring.

## Relation to the existing Airlock

The extension is intentionally separate from the release API. The ingestion path prepares traceable research data; the Airlock checks files that researchers later request to release. Joining these parts in one repository shows the full control path without claiming that one service should own every security boundary.
