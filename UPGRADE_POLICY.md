# Upgrade Policy

This file defines what `持续升级` means for the Genomics England application evidence project.

## Required cycle

Every cycle must:

1. Read `GOAL.md` first, then `TARGET_JOB.md`, `PROJECT_STATUS.md`, `EVIDENCE.md` and this file.
2. Inspect the current branch, recent commits and current CI evidence.
3. Compare the repository against P0 and P1 job requirements.
4. Identify the **single highest-value remaining evidence gap**.
5. Decide exactly one state: `REPAIR`, `BUILD`, `VALIDATE`, `WAIT_FOR_EXTERNAL_DEPENDENCY`, `APPLICATION_READY`, or `GOAL_REACHED`.
6. If `BUILD`, implement one coherent change and add suitable tests or validation.
7. Never weaken tests or remove a meaningful gate only to obtain a pass.
8. Update evidence/state documentation with observed results when state changes.
9. Commit only evidence that is internally consistent and clearly scoped.
10. Stop adding features when further work has low value for this application.

## Priority order

Prefer work in this order:

1. Missing P0 requirement with no direct evidence.
2. A P0 requirement that currently has only bounded evidence and can safely gain stronger direct evidence.
3. Real end-to-end execution or external-system integration.
4. Failure handling, security, reproducibility and operational evidence.
5. Quantitative validation and regression tests.
6. P1 requirements when they fit a real service need.
7. Documentation needed to prevent incorrect claims or stale project state.
8. P2 extras only when they have a real system role.

Do not add a technology only to match a keyword if it has no defensible role in the system.

## Claim safety

Use only the evidence classes defined in `GOAL.md`: `DIRECT`, `DIRECT_WITH_MOCKED_EXTERNAL`, `SYNTHETIC`, `REFERENCE`, and `ABSENT`.

- Synthetic data must remain labelled synthetic.
- Mocked IdP tests must not be described as a live Okta integration.
- Terraform validation must not be described as a deployed AWS service.
- Reference infrastructure must stay labelled `REFERENCE` until it is safely applied and the result is recorded.
- Historical test counts must not be presented as current when newer CI evidence exists.

## Stop conditions

Return `APPLICATION_READY` instead of writing more code when:

- all P0 areas have direct or clearly labelled bounded evidence;
- Python, API, database, identity and automated-test evidence is reproducible;
- CI is green;
- remaining gaps require external credentials, production access or mainly cover optional P1/P2 items;
- further work is unlikely to improve the application enough to justify delaying submission.

Return `GOAL_REACHED` when the application-ready package is internally consistent, supported/unsupported claims are explicit, final validated code/CI evidence is recorded, and no remaining safe change has material interview-probability benefit.

`APPLICATION_READY` and `GOAL_REACHED` do not mean the software is production-ready. They mean project work should no longer delay the job application.

## External-dependency rule

If the best next step requires AWS credentials, an IdP tenant, paid resources or access not currently available, do not fake the result. Record `WAIT_FOR_EXTERNAL_DEPENDENCY` for that step and select another task only if it has clear, material evidence value and does not delay application.

## State integrity

A cycle must repair stale status or validation records before using them to select the next task. The repository files are the long-term project state; chat history is supporting context rather than the source of truth.
