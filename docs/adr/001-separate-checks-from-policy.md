# ADR 001: Separate detection checks from release policy

- Status: accepted
- Date: 2026-07-14

## Context

A detector can identify a condition, but the release response depends on policy. Combining detection and final action inside each rule makes policy changes hard to audit and test. It also creates problems if a future machine-learning detector produces uncertain evidence.

## Decision

Each rule returns a finding with a stable code, severity, message and redacted evidence. A separate policy converts the combined findings into `ALLOW`, `REVIEW` or `BLOCK`. The policy has a version that is stored with every submission.

## Consequences

Positive effects:

- rules can be tested independently;
- policy changes are explicit;
- machine-learning findings can enter the same workflow;
- historic decisions retain their policy version;
- reviewer evidence is consistent.

Costs:

- policy and rule catalogues must remain aligned;
- a production system needs formal policy ownership and migrations;
- additive risk scores are only a demonstration and require validation.
