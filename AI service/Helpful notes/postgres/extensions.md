# Extensions: pgvector + pg_search

We're on `paradedb/paradedb:latest` -- Postgres 18.6 with `vector` (pgvector) and
`pg_search` (BM25) compiled in. Plain `postgres:18` has neither; `CREATE EXTENSION`
only *activates* an extension that's already in the image, it can't install one
from nothing.

## Enabling them (per-database)

Extensions are enabled per-database, not per-cluster. Run once per database that
needs them:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_search;
```

Already wired into `initdb/01-extensions.sql`, which the container runs
automatically -- but only when Postgres initialises a brand-new, empty data
directory. It will NOT re-run against our existing volume, so on an existing
database apply it by hand:

```sh
docker compose exec postgres psql -U postgres -d juno -f /docker-entrypoint-initdb.d/01-extensions.sql
```

## pg_search needs preloading

`pg_search` hooks into the query planner, so it has to be loaded when the Postgres
*process* starts, not when `CREATE EXTENSION` runs. Miss this and you get:

```
ERROR:  pg_search must be loaded via shared_preload_libraries.
```

Set in `docker-compose.yml`'s `command:` (not relied on from the image defaults --
see the note below on why):

```yaml
command:
  - postgres
  - -c
  - shared_preload_libraries=pg_search,pg_cron,pg_stat_statements
```

### Why not just trust the image's own config?

`postgresql.conf` -- where the image would normally set this -- lives *inside the
data directory*, i.e. inside our Docker volume. The image only writes its defaults
into that file when it initialises a brand-new data directory. Our volume was
created under plain `postgres:18` (before we switched images), so it already had a
`postgresql.conf` with nothing about `pg_search` in it, and swapping the image
underneath it did not touch that file. Setting `shared_preload_libraries` via
`command:` applies at server start regardless of what's already in the volume, so
it's the fix that works both for old volumes and for anyone cloning fresh.

## Checking what's actually enabled

```sql
\dx                                    -- installed on the current database
SELECT name FROM pg_available_extensions WHERE name IN ('vector','pg_search');
SHOW shared_preload_libraries;
```

If `\dx` doesn't list `vector` or `pg_search`, you're either on the wrong database
(`\c juno` first -- extensions are per-database) or the init script hasn't been
run against it yet.
