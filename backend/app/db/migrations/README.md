# Migrations -- placeholder

Empty for now. The actual schema-creation SQL (extensions, `messages`,
`memories`) still lives in `backend/initdb/*.sql`, run by hand against
whatever Postgres instance is configured. Left there deliberately: this
refactor pass doesn't touch DB connection/config wiring, so moving those
files wasn't done here to avoid touching that layer. Consolidating them into
a real migration tool (Alembic or similar) here is a separate follow-up.
