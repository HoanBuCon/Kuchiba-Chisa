# Production deployment security baseline

This document operationalizes `SEC-07`, `SEC-DATA-003`, `SEC-DATA-004`, and `TD-021` for the supplied Compose deployment.

## Secrets and rotation

Provision `POSTGRES_PASSWORD_FILE`, `REDIS_PASSWORD_FILE`, and `QDRANT_API_KEY` from the deployment secret manager. The two file variables must reference files outside version control; `secrets/` is intentionally ignored. Never place production values in `.env`, a Compose file, logs, or a database URL committed to source.

Rotate a credential by creating a new secret version, applying it to the dependent service, verifying its health, then revoking the previous version. PostgreSQL and Redis rotation must be coordinated with their clients to avoid partial availability. Qdrant clients use `QDRANT_API_KEY`; rotate it through the deployment secret manager and redeploy Qdrant plus the application as one controlled change.

## Network and transport

`chisa_data` is an internal Compose network. PostgreSQL, Redis, and Qdrant have no host-published ports. The application is bound only to loopback by default; deploy a managed ingress/reverse proxy in front of it.

The ingress MUST terminate TLS 1.2 or later, validate certificates, redirect HTTP to HTTPS, and set HSTS. Use TLS or mTLS for any service traffic that leaves the private deployment network. Do not expose database, cache, vector-store, or object-store ports through the ingress.

## Persistence and encryption at rest

PostgreSQL, Redis AOF, Qdrant storage, object storage, and backups MUST use encrypted volumes/buckets with KMS-managed keys. Test restore procedures at least quarterly. Redis persists AOF with `everysec`; its ACL disables the default user and grants the application account only after a password is loaded from the runtime secret mount.

## Deployment checks

Before release, verify that the secret files are provisioned, `QDRANT_API_KEY` is supplied, no data service has a host port, ingress TLS is valid, encrypted storage and backup retention are configured, and logs contain no secret values.
