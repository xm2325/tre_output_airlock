# Goal Control

Goal ID: genomics-england-v0.4.0
Status: ACTIVE
Repository: `xm2325/tre_output_airlock`
Branch: `genomics-england-python-backend-v0.4`
Target role: Genomics England — Software Engineer - Python

## /goal

Produce a defensible `v0.4.0` application-evidence release for the Genomics England Software Engineer - Python role, maximising direct, verifiable evidence for core job requirements without overstating production experience.

## Success criteria

The goal is reached only when all of the following are true:

1. Core Python backend, REST API, relational database/SQL, automated testing, security/identity and production-style engineering requirements have direct repository evidence or are explicitly bounded as reference evidence.
2. AWS architecture evidence is clearly separated into implemented/tested application behaviour versus statically validated reference infrastructure; no live-deployment claim is made without a real applied environment.
3. OIDC/IdP evidence is labelled accurately; mocked introspection tests are not described as a real Okta integration.
4. Clinical/genomic examples remain explicitly labelled synthetic unless real public non-participant data is introduced with provenance.
5. CI is green and current validation evidence is recorded.
6. `TARGET_JOB.md`, `PROJECT_STATUS.md`, `EVIDENCE.md`, `UPGRADE_POLICY.md`, `VALIDATION.md` and production-readiness documentation agree with the current repository state.
7. Backend, frontend and changelog release metadata are consistent for `0.4.0`.
8. Reproducible run and validation instructions are current.
9. Remaining gaps either require unavailable external credentials/resources or have lower application value than applying/interview preparation.

## Cycle policy

Every automated cycle must read this file first, then classify the next action as one of:

- `REPAIR`: fix stale, inconsistent or incorrect evidence/state.
- `BUILD`: implement one coherent high-value gap and validate it.
- `WAIT_FOR_EXTERNAL_DEPENDENCY`: do not fake work that requires unavailable AWS credentials, IdP access, paid resources or other external access.
- `RELEASE_READY`: no further feature work is needed; finish version/release consistency and validation.
- `GOAL_REACHED`: make no feature changes unless a regression or stale evidence is discovered.

Do not add Lambda, DynamoDB, extra frameworks, version bumps or cosmetic features merely to create activity. Do not weaken tests or gates. Prefer application evidence value over project size.

## Stop behaviour

When every success criterion is satisfied, set `Status: GOAL_REACHED` and record the final validated commit in `PROJECT_STATUS.md`. Future cycles should only check for regressions or stale evidence and otherwise make no repository changes.
