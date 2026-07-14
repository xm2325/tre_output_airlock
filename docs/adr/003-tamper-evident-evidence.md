# ADR 003: Tamper-evident reports and audit events

## Status

Accepted for the demonstration.

## Context

A release decision should be linked to its evidence and history. A mutable JSON response or ordinary event table does not show whether content changed later.

## Decision

- Sign the canonical decision report with HMAC-SHA256.
- Link each audit event to the previous event hash.
- Provide endpoints that verify both structures.

## Consequences

This detects changes but does not prevent them. Production should use a managed signing key, restricted database roles and an independent append-only audit sink.
