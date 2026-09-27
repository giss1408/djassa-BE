# Database Migrations

Djassa uses Alembic for schema changes. Application startup does not create or alter tables; migrations must be applied as a deployment step.

## Apply migrations

Set the same database URL used by the API, then run:

```bash
export DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DATABASE
alembic -c alembic.ini upgrade head
```

Check the current revision:

```bash
alembic -c alembic.ini current
```

## Create a migration

1. Change the SQLAlchemy model.
2. Generate a candidate migration:

   ```bash
   alembic -c alembic.ini revision --autogenerate -m "describe_the_change"
   ```

3. Review the generated file manually. Confirm indexes, constraints, nullability, data backfills, and downgrade behavior.
4. Test upgrade and downgrade against PostgreSQL.
5. Commit the model and migration together.

## Roll back

Roll back one revision only after checking application compatibility:

```bash
alembic -c alembic.ini downgrade -1
```

Never run a destructive downgrade against production without a verified backup and an approved recovery plan.

## Deployment rules

- Back up production before schema changes.
- Apply migrations before starting a new application version when the change is backward-compatible.
- Use expand-and-contract migrations for changes requiring multiple releases.
- Do not use `Base.metadata.create_all()` as a production migration mechanism.
- Verify the resulting revision in deployment logs.