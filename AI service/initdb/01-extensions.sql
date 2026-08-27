-- Run automatically by the Postgres container the first time it initialises an
-- empty data directory (see the /docker-entrypoint-initdb.d mount in
-- docker-compose.yml). Keeps setup reproducible: clone the repo, `docker compose
-- up -d`, and the database is ready with no manual psql step.
--
-- Note this only fires on a FRESH volume. On an existing database, run it by hand:
--   docker compose exec postgres psql -U postgres -f /docker-entrypoint-initdb.d/01-extensions.sql

-- pgvector: adds the VECTOR column type and the distance operators (<=> for
-- cosine) that L2 dense retrieval searches with.
CREATE EXTENSION IF NOT EXISTS vector;

-- pg_search: ParadeDB's BM25 index. This is L1, the lexical half of retrieval --
-- it matches on the actual words used, catching the specifics (a drug name, a
-- person's name) that embeddings blur away.
CREATE EXTENSION IF NOT EXISTS pg_search;
