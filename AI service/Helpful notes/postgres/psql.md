# Getting into the database

```sh
docker compose exec postgres psql -U postgres
```

Connects you straight into `psql` inside the running container. Default connects to the `postgres` database — for a different one:

```sh
docker compose exec postgres psql -U postgres -d juno
```

To run a `.sql` file without an interactive session (e.g. the init script):

```sh
docker compose exec postgres psql -U postgres -f /docker-entrypoint-initdb.d/01-extensions.sql
```

## Meta-commands (psql only -- no semicolon, not SQL)

```
\l          list all databases
\c juno     switch to database "juno"
\dt         list tables in the CURRENT database
\d memories describe a table -- columns, types, indexes
\di         list indexes
\dx         list installed extensions
\q          quit
\! clear
```

`\dt` only shows tables in whichever database you're currently connected to. If you created `memories` in `juno` but you're still connected to `postgres`, `\dt` won't show it -- `\c juno` first.

## Same things, as plain SQL (works from any client, not just psql)

```sql
SELECT datname FROM pg_database WHERE datistemplate = false;          -- \l
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';  -- \dt
SELECT extname FROM pg_extension ORDER BY extname;                    -- \dx
```

## Gotchas we actually hit

- **No `USE`.** That's MySQL. Postgres switches database with `\c dbname` in psql, or by connecting with `-d dbname` from the shell -- there's no SQL statement for it, a connection is scoped to one database.
- **Unquoted identifiers get lowercased.** `CREATE DATABASE Juno;` actually creates `juno`. `CREATE TABLE Memories (...)` creates `memories`. Only matters if you quote one half and not the other later (`"Memories"` vs `memories` are then different names).
- **`CREATE TABLE name;` with no column list is a syntax error.** Postgres needs at least the parens, even for a table you plan to fill in later: `CREATE TABLE name ();` is valid, `CREATE TABLE name;` is not.
