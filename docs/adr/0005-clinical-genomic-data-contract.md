# ADR 0005: Keep clinical-genomic ingestion separate from output release

## Status

Accepted for the synthetic portfolio demonstration.

## Context

Clinical and genomic source ingestion has different users, permissions, failure modes and retention rules from research-output release. Adding ingestion code directly to the Airlock API would make one service responsible for both privileged source linkage and outward release decisions.

## Decision

Implement ingestion as a separate Python package and Prefect flow. It writes research-ready and restricted outputs to separate zones. The existing Airlock remains responsible for release review after research use.

## Consequences

- tests and deployment can change without coupling to the FastAPI release service;
- restricted linkage can have a separate access policy;
- lineage can connect the two services later through dataset and run identifiers;
- local duplication exists in logging and configuration until shared platform services are introduced;
- this repository demonstrates the control path but does not claim one production trust boundary.
