The `memories` table schema now lives in `initdb/03-memories.sql` (auto-applied on a
fresh Postgres volume, same as `messages` — see `initdb/02-messages.sql`). This file
used to hold a copy of the schema that had to be pasted in by hand; that copy is
gone to avoid the two drifting apart.

On an existing volume where init scripts don't re-run, apply it manually:

```sh
docker compose exec postgres psql -U postgres -f /docker-entrypoint-initdb.d/03-memories.sql
```
