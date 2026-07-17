# AWS clinical-genomic landing-zone baseline

This Terraform module defines a synthetic-data baseline for the new ingestion pipeline:

- encrypted and versioned landing, quarantine, curated and restricted S3 buckets;
- full public-access blocking;
- one KMS key with rotation;
- an encrypted delivery queue and dead-letter queue;
- a pipeline policy covering only the required buckets, queue and key.

It does not create a runtime service, network boundary, identity provider, approved key policy or monitoring stack. Those controls depend on the deployment environment and security review.

Validate without applying:

```bash
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
```
