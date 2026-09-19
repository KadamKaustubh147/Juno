-- Aiven for PostgreSQL is fully managed: no custom shared_preload_libraries,
-- no installing extensions outside its allowlist. pg_search/ParadeDB needs
-- both, so it's not an option here -- L1 lexical retrieval uses core Postgres
-- full-text search instead (see 03-memories.sql), which needs no extension.
--
-- pgvector IS on Aiven's allowlist and self-service via CREATE EXTENSION as
-- the default admin user (avnadmin) -- no console step required first.
--
-- Run by hand against the Aiven service (there's no docker-entrypoint-initdb.d
-- equivalent on a managed instance):
--   psql "$DATABASE_URL" -f initdb/01-extensions.sql

-- pgvector: adds the VECTOR column type and the distance operators (<=> for
-- cosine) that L2 dense retrieval searches with.
CREATE EXTENSION IF NOT EXISTS vector;
