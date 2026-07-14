# Security policy

## Demonstration boundary

This repository is a synthetic portfolio project. Do not submit real participant, patient, clinical, confidential or identifying data.

The `X-Demo-User` and `X-Demo-Role` headers are not authentication. They exist only to demonstrate application-level permission logic locally.

## Reporting a security issue

Do not open a public issue containing sensitive details. Use the repository owner's private contact route and include:

- affected component and version;
- minimal reproduction steps using synthetic data;
- expected and observed behaviour;
- possible impact;
- suggested mitigation, when known.

## High-risk areas

Changes to file parsing, role checks, report signing, audit verification, retention, database migrations and policy actions require focused tests and review.

## Secrets

Do not commit `.env` files, signing secrets, database passwords, access tokens or real file samples. The values in `.env.example` are local demonstration defaults and must be replaced outside local use.
