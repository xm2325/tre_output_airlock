# ADR 0006: Classify schema drift and publish operational evidence

- Status: accepted
- Date: 2026-07-17

## Context

The first clinical–genomic pipeline version checked values and references but did not record whether an upstream source had changed its shape. A delivery could add a field without an operator seeing it, while a missing required field could fail later inside transformation code. Successful runs and quarantined deliveries also had to be inspected one directory at a time.

For clinical and genomic data, the service needs to separate two cases:

1. a breaking change that makes the agreed input contract unsafe or incomplete;
2. an additive change that may be compatible but still requires review and an explicit record.

Operators also need a compact view of successful publication, quarantine volume, warning counts and incomplete staging state.

## Decision

The pipeline uses a versioned contract report with three outcomes:

- `PASS`: the observed shape matches the demonstration contract;
- `WARN`: only additive fields or columns were observed;
- `FAIL`: required fields or columns are missing.

Each report contains a SHA-256 schema fingerprint derived from field names and resource types, not data values. Breaking drift is converted into validation issues and written to quarantine before manifest loading or data transformation. Additive drift is accepted, recorded in `contract_report.json`, included in lineage and counted in run metrics.

A separate operations command scans published runs and quarantine evidence. It creates:

- a machine-readable JSON summary;
- a portable HTML dashboard with no external assets;
- alerts for a success rate below target, quarantined deliveries, contract warnings and incomplete staging directories.

The operations command reads evidence already written by the pipeline. It does not alter source or research data.

## Reasons

This approach makes source-system change visible without blocking every compatible addition. It also prevents missing required fields from becoming less clear exceptions later in the run. A value-free schema fingerprint supports comparison without copying clinical values into monitoring data.

Keeping the operations view separate from the ingestion function avoids coupling publication logic to a dashboard and allows another monitoring service to consume the same JSON later.

## Consequences

The demonstration contract covers only the supported subset of FHIR and the synthetic genomic manifest. A production contract would use approved profiles, terminology validation, owner review and a managed registry. Additive changes still require a human decision about whether the contract should be revised.

The generated dashboard is local operational evidence, not a replacement for central logs, metrics, paging or security monitoring.
