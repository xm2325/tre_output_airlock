# Upgrade Policy

This file defines what `持续升级` means for the Genomics England application evidence project.

## Required cycle

Every cycle must:

1. Read `TARGET_JOB.md`, `PROJECT_STATUS.md`, `EVIDENCE.md` and this file first.
2. Inspect the current branch, recent commits and current CI evidence.
3. Compare the repository against P0 and P1 job requirements.
4. Identify the **single highest-value remaining evidence gap**.
5. Decide one action: `BUILD`, `WAIT_FOR_EXTERNAL_DEPENDENCY`, `REPAIR`, or `GOOD_ENOUGH_FOR_APPLICATION`.
6. If `BUILD`, implement one coherent change and add suitable tests or validation.
7. Never weaken tests or remove a meaningful gate only to obtain a pass.
8. Update `EVIDENCE.md` and `PROJECT_STATUS.md` with the observed result.
9. Commit only evidence that is internally consistent and clearly scoped.
10. Stop adding features when further work has low value for this application.

## Priority order

Prefer work in this order:

1. Missing P0 requirement with no direct evidence.
2. A P0 requirement that currently has only reference evidence and can safely gain direct evidence.
3. Real end-to-end execution or external-system integration.
4. Failure handling, security, reproducibility and operational evidence.
5. Quantitative validation and regression tests.
6. P1 requirements when they fit a real service need.
7. Documentation needed to prevent incorrect claims or stale project state.

Do not add a technology only to match a keyword if it has no defensible role in the system.

## Claim safety

- Synthetic data must remain labelled synthetic.
- Mocked IdP tests must not be described as a live Okta integration.
- Terraform validation must not be described as a deployed AWS service.
- Reference infrastructure must stay labelled `REFERENCE` until it is safely applied and the result is recorded.
- Historical test counts must not be presented as current when newer CI evidence exists.

## Stop conditions

Return `GOOD_ENOUGH_FOR_APPLICATION` instead of writing more code when:

- all P0 areas have direct or clearly labelled reference evidence;
- Python, API, database, identity and automated-test evidence is reproducible;
- CI is green;
- remaining gaps require external credentials, production access or mainly cover optional P1 items;
- further work is unlikely to improve the application enough to justify delaying submission.

`GOOD_ENOUGH_FOR_APPLICATION` does not mean the software is production-ready. It means project work should no longer delay the job application.

## External-dependency rule

If the best next step requires AWS credentials, an IdP tenant, paid resources or access not currently available, do not fake the result. Record `WAIT_FOR_EXTERNAL_DEPENDENCY` for that step and select the next safe, useful task only if it has clear evidence value.

## State integrity

A cycle must repair stale status or validation records before using them to select the next task. The repository files are the long-term project state; chat history is supporting context rather than the source of truth.
