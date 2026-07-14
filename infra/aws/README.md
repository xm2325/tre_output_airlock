# AWS quarantine baseline

`quarantine-baseline.yml` is a small CloudFormation example, not a complete deployment. It creates:

- a KMS key and alias;
- a private, versioned S3 quarantine bucket;
- an encrypted SQS scan queue and dead-letter queue;
- S3 event delivery to the scan queue;
- a CloudWatch alarm when the dead-letter queue is non-empty;
- a 30-day lifecycle rule for non-current object versions.

A complete deployment still needs the API and worker compute, RDS PostgreSQL, private networking, managed identity, container registry, WAF/rate limits, log retention, alarms and environment promotion.
