# ADR 002: Review claims plus optimistic concurrency

## Status

Accepted for the demonstration.

## Context

Two reviewers can open the same queue item. A last-write-wins update can hide another review or record a decision against stale evidence.

## Decision

Use two controls:

1. a reviewer claims an item before deciding it;
2. every change increments `row_version`, and review requests include `expected_version`.

The API returns HTTP 409 when ownership or version checks fail.

## Consequences

The interface must display ownership and refresh after conflicts. A production system also needs claim expiry, abandoned-work recovery and service-level monitoring.
