# liftoffDB

A Postgres-compatible distributed database, forked from YugabyteDB (Apache-2.0) and broken from upstream.

Target: threaded, AI-optimized, FoundationDB/CockroachDB-grade distribution, Turso-style embedded and sync modes,
Mongo-style documents, built as configurable modules.

Status: research. Design doc in progress.

- `research/increment-1/` engine runs (Yugabyte, CockroachDB, FoundationDB, MongoDB, Turso; Neon next) and the scripts used
- `research/02-capability-map.md` what each engine does best and how liftoffDB takes it in
