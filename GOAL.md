# Goal Control

Goal ID: genomics-england-backend-application-ready
Status: ACTIVE
Repository: `xm2325/tre_output_airlock`
Branch: `genomics-england-python-backend-v0.4`
Target role: Genomics England — Software Engineer - Python
Target outcome: maximise the probability of reaching interview for the current Backend Python Software Engineer vacancy.
Application deadline: 6 September 2026, 23:00 UK time

## /goal

Make this repository a concise, defensible and interview-ready technical evidence package for the current Genomics England Backend Python Software Engineer vacancy.

The project must show strong, directly verifiable evidence for the role's core backend requirements, close only material evidence gaps, keep all claims honest, and stop development as soon as further engineering work is less valuable than submitting the application and preparing for interview.

A `v0.4.0` release may be used as a clean application checkpoint, but the version number is not itself the goal.

## What the employer needs evidence for

### P0 — core requirements; highest priority

1. **Python backend engineering**
   - well-structured, typed, maintainable Python;
   - clear service boundaries and error handling;
   - evidence of owning a non-trivial backend feature end to end.

2. **Scalable backend services and microservice thinking**
   - independently deployable service boundary;
   - health/readiness behaviour, configuration, failure handling and operational concerns;
   - architecture decisions that are justified rather than added for keyword matching.

3. **REST API engineering**
   - designed and consumed REST APIs;
   - stable schemas/contracts, validation, error semantics and integration tests.

4. **Relational databases / SQL / RDS-relevant engineering**
   - real PostgreSQL path, schema migration and SQL-backed application behaviour;
   - concurrency, migration and failure concerns where relevant;
   - AWS RDS may remain reference infrastructure if no safe live AWS environment exists.

5. **AWS and IAM**
   - direct evidence where possible;
   - otherwise clear, statically validated reference infrastructure with private networking, IAM/secrets boundaries, logging and deployment reasoning;
   - never describe Terraform validation as a live AWS deployment.

6. **Identity and access management / Okta-like IdP integration**
   - authentication and authorisation boundary implemented in code;
   - issuer/audience/expiry/role validation and failure behaviour tested;
   - prefer a real local or test standards-compatible IdP end-to-end integration if it materially strengthens evidence;
   - mocked introspection is not a real Okta integration.

7. **Test automation, TDD-style quality and troubleshooting**
   - automated unit/integration/contract tests;
   - meaningful coverage gate without gaming coverage;
   - failure-path tests, CI, reproducibility and useful operational diagnostics.

8. **Reliable delivery and collaboration evidence**
   - clear commits/PR-quality changes, code review-friendly structure, ADRs/runbooks where useful;
   - documentation should make technical decisions easy to explain in interview.

### P1 — useful differentiators; build only when coherent

- Amazon API Gateway;
- deployment/rollback and migration safety;
- React/JavaScript interoperability;
- security controls and observability;
- realistic clinical/genomic domain workflow;
- code-review and maintainability evidence.

### P2 — optional; do not build only for keywords

- DynamoDB;
- Lambda;
- extra frameworks or services not justified by the system design.

## Evidence-quality rules

Every capability must be classified as one of:

- `DIRECT`: implemented and validated in this repository;
- `DIRECT_WITH_MOCKED_EXTERNAL`: application behaviour is implemented, but an external system is mocked;
- `SYNTHETIC`: implementation is real but data/evaluation uses synthetic examples;
- `REFERENCE`: architecture/IaC exists and is validated, but has not been run in a live target environment;
- `ABSENT`: no defensible evidence.

Never promote a capability to a stronger class without new evidence.

## Success criteria

The goal is reached when all of the following are true:

1. Every P0 requirement has strong `DIRECT` evidence or an explicit, defensible bounded evidence class such as `DIRECT_WITH_MOCKED_EXTERNAL` or `REFERENCE` where external infrastructure is unavailable.
2. There is no major P0 gap that can be closed safely with one or two high-value engineering cycles before application.
3. Backend CI is green with current tests, lint/type checks and meaningful coverage gates.
4. REST, PostgreSQL/migrations, authentication/authorisation, failure paths and operational behaviour are reproducibly demonstrable.
5. AWS/IAM evidence is technically credible and clearly separated from claims of live production operation.
6. Identity evidence is honest about mocked versus real external IdP integration.
7. Clinical/genomic data is labelled synthetic unless provenance proves otherwise.
8. `TARGET_JOB.md`, `PROJECT_STATUS.md`, `EVIDENCE.md`, `VALIDATION.md`, README and production-readiness docs agree with the actual repository state.
9. The repository provides at least 3–5 concise CV/interview-ready evidence statements, each traceable to implementation and validation.
10. Remaining engineering work is either blocked on external credentials/resources, optional P1/P2 work, or lower-value than submitting the application and preparing interview explanations.
11. If a release checkpoint is used, backend/frontend/changelog versions are consistent; `v0.4.0` is allowed only after the release state is coherent and validated.

## Upgrade priority

For each candidate upgrade, rank it by:

`priority = JD importance + evidence gain + interview explainability + validation strength + reuse - implementation cost - claim risk`

Prefer the single highest-value remaining upgrade. In general:

1. missing P0 direct evidence;
2. end-to-end behaviour replacing mocked-only evidence;
3. failure/recovery/security evidence;
4. realistic integration and operational validation;
5. quantitative/reproducible evidence;
6. P1 differentiators;
7. documentation/state repair;
8. P2 keyword additions.

Do not choose a lower-ranked task simply because it is easier.

## Cycle policy

Every cycle must first read this file, the current official job requirements, repository state and latest CI evidence, then choose exactly one state:

- `REPAIR`: evidence/state/version documentation is stale or inconsistent.
- `BUILD`: one material evidence gap can be closed safely now.
- `VALIDATE`: implementation exists but evidence is not yet strong enough.
- `WAIT_FOR_EXTERNAL_DEPENDENCY`: best next step needs unavailable credentials, paid infrastructure, external tenant or other access.
- `APPLICATION_READY`: technical evidence is already strong enough; project work should not delay application.
- `GOAL_REACHED`: application-ready evidence package is coherent and no material safe upgrade remains.

Perform at most one coherent engineering objective per cycle. Never weaken tests or gates to make a cycle pass. Do not make cosmetic changes merely to create activity.

## Application-protection rule

This role closes on 6 September 2026 at 23:00 UK time.

Once `APPLICATION_READY` is reached, additional project development must have a clear and material interview-probability benefit. Otherwise stop coding and prioritise application/CV/interview preparation.

Do not let optional AWS services, Lambda, DynamoDB, version numbers, extra dashboards or architecture polish delay submission.

## Stop behaviour

When the success criteria are satisfied:

1. set `Status: GOAL_REACHED`;
2. record the final validated commit and CI evidence in `PROJECT_STATUS.md`;
3. update `EVIDENCE.md` with supported and unsupported claims;
4. make no further feature changes unless a regression, stale claim or newly identified material JD gap appears;
5. report that the project is application-ready and name the next non-coding application action.
