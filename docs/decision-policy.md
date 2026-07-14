# Decision policy

## Safety statement

The policy is a demonstration built for synthetic files. It is not UK Biobank policy and must not be used to decide whether real participant data can be released.

## Decision model

Every check returns a finding code. The rule catalogue defines its category, severity and default workflow action. The final automated decision is the most restrictive action among all findings.

```text
BLOCK  >  REVIEW  >  ALLOW
```

A file with no findings is routed to `ALLOW`. `REVIEW` requires a reviewer decision and rationale. Automated evidence remains in the record after manual review.

## Main rule groups

| Group | Example | Default action | Reason for the control |
|---|---|---:|---|
| File integrity | extension and binary signature disagree | BLOCK | prevents the parser from trusting a misleading filename |
| Direct identifiers | participant identifier column, email, phone-like value | BLOCK | indicates direct disclosure risk |
| Quasi-identifiers | UK postcode-like or labelled date-of-birth-like value | BLOCK | combinations can identify a person |
| Aggregate disclosure | count below five | REVIEW | a reviewer may need suppression or aggregation |
| Uniqueness | a near-unique column | REVIEW | may indicate row-level or highly identifying output |
| Free text | notes or comments column | REVIEW | unstructured text can contain identifiers |
| Spreadsheet behaviour | formula-like cell | REVIEW | opening a file can trigger formula interpretation |
| Partial inspection | row scan cap reached | REVIEW | the system cannot claim a complete inspection |
| Metadata | image GPS or document parsing problem | REVIEW or BLOCK | hidden metadata or failed inspection needs action |

## Risk score

The score is a display aid based on the most severe findings. It is not a probability of disclosure and is not calibrated against real incidents. Workflow decisions are made from explicit actions, not from a hidden probability threshold.

## Policy simulation

The simulator re-maps stored findings under candidate severity actions. It estimates changes in workflow counts and automation rate without changing stored decisions.

It answers questions such as:

- How much reviewer work results if all high-severity findings require review rather than block?
- How many past decisions would change under a proposed mapping?
- Does a higher automation rate come from accepting more risk or from blocking more outputs?

It does not re-run file checks and does not measure real disclosure-control accuracy.

## Policy change process for a deployed service

1. Define the new rule or action and its intended safety effect.
2. Add unit tests and synthetic benchmark cases.
3. Run retrospective simulation on approved test data.
4. Review false-positive and false-negative examples with policy specialists.
5. Record approval and assign a new policy version.
6. Deploy with monitoring and a rollback path.
7. Recheck selected historical cases when justified.
