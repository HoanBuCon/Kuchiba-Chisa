# Database migration operations

## Ownership boundary

Alembic is the only owner of the production PostgreSQL schema. FastAPI and the
Discord adapter may read and write application rows, but they must never create,
repair, alter, or drop schema at startup. FastAPI readiness checks the current
`alembic_version` against the repository head and fails closed in production when
they differ.

The SQLite file managed by
`app/infrastructure/ingestion/storage/state_db.py` is an auxiliary ingestion-state
store. It is not connected through `DATABASE_URL` and is outside the production
PostgreSQL schema boundary. Its lifecycle must not be used to bootstrap PostgreSQL.

## Forward migration procedure

1. Confirm the target release, database endpoint, maintenance window, and operator
   authorization. Never run a migration against an endpoint inferred from client
   input.
2. Review every migration between the deployed revision and the target head.
3. Take and verify a restorable PostgreSQL backup. A backup is mandatory before
   any destructive, data-rewriting, long-locking, or otherwise irreversible
   migration.
4. Stop or drain application writers when the reviewed migration requires it.
5. Record the starting revision with `python -m alembic current`.
6. Run `python -m alembic upgrade head` as a dedicated deployment step, before
   starting FastAPI or Discord.
7. Verify `python -m alembic current` reports the expected head and run
   `python -m alembic check` to detect ORM/migration drift.
8. Start services and verify readiness. A revision mismatch is a deployment
   failure; do not repair it from application startup.

## Rollback and downgrade limitations

An Alembic downgrade is not automatically safe. Before release, classify each
migration as reversible, conditionally reversible, or restore-only and document
the expected lock/data effects.

Migration `7a8c9d0e1f2b` adopts pre-existing Discord tables without deleting rows.
Its automatic downgrade deliberately refuses to drop those tables because their
ownership and data may predate Alembic. Roll back that release by restoring the
verified pre-migration backup or by applying a separately reviewed, explicitly
authorized forward repair/ownership migration. Do not bypass the guard with an
ad-hoc `DROP TABLE`.

For any failed migration:

1. Keep application writers stopped.
2. Capture the failure and current revision for the audit record.
3. If the migration transaction rolled back cleanly, correct it in a new reviewed
   deployment artifact and retry.
4. If data or schema was partially changed, restore the verified backup or follow
   the migration-specific recovery plan.
5. Run `alembic current`, `alembic check`, integrity checks, and application smoke
   tests before reopening traffic.

## CI drift gate

The isolated Compose verification upgrades an ephemeral PostgreSQL database to
head and then runs `python -m alembic check`. Any new model/schema drift blocks the
gate. The runtime revision check complements this CI test; it does not replace it
and never performs DDL.
