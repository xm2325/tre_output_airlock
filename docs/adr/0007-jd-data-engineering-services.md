# ADR 0007: Secure transfer, OMOP-aligned outputs and curated AWS publication

## Status

Accepted for the synthetic portfolio implementation.

## Context

The data-engineering role targeted by this repository expects large-scale clinical and genomic ingestion, secure transfer tooling such as Aspera or Globus, healthcare standards, Prefect orchestration, AWS storage and compute practices, data quality, observability, testing, automation and clean integration with product, QA and architecture teams.

The existing pipeline validated local FHIR and VCF inputs and recorded lineage, but it did not prove how files arrived, did not create a standard clinical research model, and did not test the boundary between restricted linkage and curated cloud publication.

## Decision

The pipeline will use four explicit interfaces.

### Receiver-side transfer receipt

A versioned JSON receipt records transfer ID, tool, source and destination endpoints, status, byte counts, retries, resume state and SHA-256 for each delivered file. The receiver validates this evidence against files on disk before clinical transformation starts. `ASPERA` and `GLOBUS` describe the transfer context; this repository does not call vendor APIs.

### OMOP-aligned research model

Validated FHIR records are written to a small OMOP-aligned subset: `person`, `condition_occurrence`, `measurement` and `specimen`. A versioned terminology table maps source codes to standard concept IDs. Unknown codes remain explicit review items rather than receiving invented mappings.

### Staged Prefect orchestration

The flow exposes three task boundaries with separate retry policies: preflight, clinical-genomic processing and evidence summary. Validation remains inside the core pipeline as a defence-in-depth control, so bypassing Prefect does not bypass safety checks.

### Curated AWS publication

A publication plan selects only gold data and operational evidence. Bronze, silver and restricted linkage paths are excluded. Uploads require SSE-KMS and carry digest and classification metadata. CI tests this boundary using a fake boto3-compatible client; no deployed AWS service is claimed.

## Consequences

The run ID now includes the transfer receipt and terminology-map digests. Changes in delivery evidence or reference mappings create a new run. Successful runs contain transfer and data-quality reports, OMOP-aligned tables and richer lineage. Product, QA and operations consumers can use stable machine-readable reports without receiving raw patient identifiers.

## Limits

A production service still needs managed transfer credentials and APIs, malware scanning, approved FHIR profiles, a governed vocabulary release process, full OMOP validation, private networking, workload identity, object retention policy, managed Prefect infrastructure, central telemetry and formal privacy review.
