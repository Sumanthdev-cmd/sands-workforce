# Mobile schema setup

The deployed mobile additions were installed outside the historical Alembic
chain. The public source includes their setup here so they are not lost.

For a **separate development database**, after the Alembic migrations:

1. Apply `mobile_tracking_schema.sql` using your PostgreSQL client.
2. From `backend`, with your local environment configured, create the two push
   tables from the existing definitions:

```bash
python -c "from app.db.session import engine; from app.services.mobile_push_store import metadata; metadata.create_all(engine)"
```

The SQL comes from the mobile tracking installer. The push metadata owns only
`mobile_push_installations` and `mobile_push_deliveries`; projections of other
application tables use a different metadata object.

These steps are documented for reconstruction. A full migration rehearsal on a
new PostgreSQL database has not been performed for this source publication.
Do not run setup commands against a live database merely to browse this project.

## Later workforce updates

After mobile setup, apply SQL files in update_schemas/ in numeric order to a
development database. These preserve installer schema additions outside Alembic.
See [update notes](../../docs/UPDATES_2026_10_24.md).
