#!/usr/bin/env bash
set -euo pipefail

BRANCH="keycloak-oidc-integration-v0.19"
TRIGGER=".delivery/v019-trigger"

if [[ "$(git branch --show-current)" != "$BRANCH" ]]; then
  echo "unexpected branch" >&2
  exit 1
fi
if [[ "$(cat VERSION)" != "0.18.0" ]]; then
  echo "expected 0.18.0 baseline" >&2
  exit 1
fi
if [[ ! -f "$TRIGGER" ]]; then
  echo "missing release trigger" >&2
  exit 1
fi

python - <<'PY'
from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one release anchor, found {count}")
    file_path.write_text(text.replace(old, new), encoding="utf-8")


Path("VERSION").write_text("0.19.0\n", encoding="utf-8")
replace("backend/app/version.py", '__version__ = "0.18.0"', '__version__ = "0.19.0"')
replace('backend/pyproject.toml', 'version = "0.18.0"', 'version = "0.19.0"')
replace('frontend/package.json', '"version": "0.18.0"', '"version": "0.19.0"')

replace(
    "README.md",
    "| Identity and authorisation | OAuth2/OIDC token introspection with issuer/audience/expiry checks, configurable IdP group-to-RBAC mapping, explicit 401/403/503 paths, and a bounded short-lived successful-introspection cache |",
    "| Identity and authorisation | OAuth2/OIDC token introspection with issuer/audience/expiry checks, configurable IdP group-to-RBAC mapping, explicit 401/403/503 paths, a bounded short-lived successful-introspection cache, and a pinned Keycloak real-provider CI contract covering token issuance, RFC7662 introspection and route-level RBAC |",
)
replace(
    "README.md",
    "- OAuth2/OIDC token-introspection identity with configurable IdP group-to-role mapping;",
    "- OAuth2/OIDC token-introspection identity with configurable IdP group-to-role mapping, plus a pinned Keycloak real-provider CI path that obtains access tokens and exercises the production introspection adapter over HTTP;",
)

replace(
    "docs/identity-and-backend-platform.md",
    "The tests mock the IdP network boundary. They do not contact or claim a real Okta tenant.",
    "Unit and concurrency tests still mock the IdP network boundary for deterministic failure, cache and single-flight coverage. A separate CI contract now starts pinned Keycloak 26.7.2, imports a synthetic realm, obtains real access tokens, lets the production RFC 7662 adapter introspect them over HTTP and verifies researcher/reviewer/admin route-level RBAC. This is representative provider-integration evidence and does not contact or claim a real Okta tenant.",
)
replace(
    "docs/identity-and-backend-platform.md",
    "The current v0.14 backend contract collects 92 tests. The standard SQLite coverage path passes 90 with two PostgreSQL-only skips at 90.23% coverage, while the dedicated PostgreSQL 16 path passes 91 with one SQLite-only skip. The PostgreSQL path additionally exercises the barrier-forced upload-idempotency race and the existing pool-saturation contract.",
    "The v0.18 backend contract collects 122 tests. The standard SQLite coverage path passes 119 with three environment-specific skips at 90.16% coverage, while the dedicated PostgreSQL 16 path passes 121 with one environment-specific skip. The PostgreSQL path also exercises claim-token stale-worker fencing, bounded pool exhaustion, upload-idempotency races and the cursor query-plan contract.",
)
replace(
    "docs/identity-and-backend-platform.md",
    "Passing these checks supports claims about tested Python/PostgreSQL behavior, explicit per-task database connection budgets and statically validated Terraform. The OIDC tests use a simulated IdP boundary, including the threaded single-flight cases. These checks do **not** support a claim that the AWS stack has been applied, that the reference pool values have been calibrated against a real RDS instance, that a real IdP integration has been operated, or that single-flight coordination spans multiple service tasks.",
    "Passing these checks supports claims about tested Python/PostgreSQL behavior, explicit per-task database connection budgets, statically validated Terraform and a real CI identity-provider integration boundary. OIDC unit/concurrency tests still use simulated responses, while the dedicated provider contract uses pinned Keycloak with real token issuance and HTTP introspection. These checks do **not** support a claim that the AWS stack has been applied, that the reference pool values have been calibrated against a real RDS instance, that a live Okta or production IdP has been operated, or that single-flight coordination spans multiple service tasks.",
)

changelog = Path("CHANGELOG.md")
text = changelog.read_text(encoding="utf-8")
anchor = "## 0.18.0 — 2026-08-24\n"
if text.count(anchor) != 1:
    raise SystemExit("CHANGELOG: missing 0.18.0 anchor")
entry = """## 0.19.0 — 2026-08-25

### Real OIDC provider integration evidence

- Added a dedicated CI contract with pinned Keycloak 26.7.2 and a synthetic Airlock realm for researcher, reviewer and admin identities.
- Obtained real OAuth2 access tokens from the provider and exercised the production RFC 7662 introspection adapter over HTTP rather than injecting mocked introspection responses.
- Added explicit access-token audience and group-membership mappers so Keycloak introspection returns the claims required by the existing strict Airlock issuer/subject/group contract.
- Verified `/api/v1/me` actor mapping, researcher denial on the review queue, reviewer/admin access, inactive-token rejection and missing-bearer rejection.
- Retained deterministic mocked IdP unit/concurrency tests for cache, failure and single-flight behavior while adding this separate end-to-end provider boundary.

### Boundary

- Keycloak is representative CI integration evidence. This release does not claim a live Okta tenant, production identity-provider operation or Genomics England infrastructure.

"""
changelog.write_text(text.replace(anchor, entry + anchor), encoding="utf-8")
PY

(
  cd backend
  uv lock
  uv sync --frozen --all-extras
)
(
  cd frontend
  npm install --package-lock-only --ignore-scripts
  npm ci
)
python scripts/check_release_version.py

# Restore the registered CI workflow to the read-only main version before creating the release tree.
git show origin/main:.github/workflows/ci.yml > .github/workflows/ci.yml
rm -f .delivery/finalize-v019.sh .delivery/v019-trigger .delivery/v019-synchronize

git add -A
git diff --cached --check
python scripts/check_release_version.py

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "release: finalize v0.19.0 real OIDC provider evidence"
git push origin HEAD:"$BRANCH"
