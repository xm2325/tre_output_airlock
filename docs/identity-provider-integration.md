# Representative OIDC provider integration

The production authentication adapter uses RFC 7662 token introspection. The CI identity contract uses a real Keycloak server as a representative standards-based provider so that token issuance, introspection, claim validation and application authorisation cross a real HTTP identity-provider boundary.

The CI realm contains researcher, reviewer and admin groups plus an unmapped user. A confidential client obtains user access tokens through a CI-only direct grant and authenticates to the introspection endpoint. The Airlock validates issuer, audience, token activity and expiry, maps the `groups` claim to its internal roles, and uses a dedicated subject claim for the actor name.

This evidence is deliberately narrower than a production identity deployment. Keycloak is not Okta, the CI passwords and client secret are synthetic fixtures, the direct grant exists only to make non-interactive integration testing deterministic, and this repository does not claim access to or operation of a live Genomics England identity tenant. The relevant evidence is interoperability with a real OIDC/RFC 7662 provider and fail-closed application authorisation.
