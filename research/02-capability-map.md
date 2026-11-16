# Increment 2: capability map

What each engine does best, how it does it, and how liftoffDB takes it in.
Base is YugabyteDB (Apache-2.0). Everything here maps onto a configurable module.

Evidence tags:
- **run**: seen in our own runs (`increment-1/runs/`), single 4-core host, relative numbers only.
- **src**: read in the engine's source tree.
- **docs**: from the engine's public docs or papers, not yet verified here.

How we may take it in, by license:
- **copy**: code may be copied (Apache-2.0, MIT, PostgreSQL License).
- **clean-room**: study, run and read papers; reimplement from public design only, never from source (CockroachDB CSL, MongoDB SSPL).

## Summary

| Engine | Best at | Take in as | Module |
|---|---|---|---|
| YugabyteDB | PG-compatible SQL on Raft-sharded storage, per-tablet MVCC, Vector LSM | base (copy) | everything not replaced |
| CockroachDB | symmetric single binary, fast failover, 1-RTT commit, multi-region SQL, goroutine-per-session | clean-room | `lift-tx`, `lift-placement`, `lift-session` |
| FoundationDB | deterministic simulation testing, unbundled roles, strict serializability | copy (ideas and some code) | `lift-sim`, `lift-tx` |
| Turso | in-process embedded engine, MVCC concurrent writers, embedded replicas that sync | copy (MIT, Rust) | `lift-embed`, `lift-sync` |
| Neon | storage/compute split, copy-on-write branching, PITR by LSN, scale to zero | copy | `lift-branch`, `lift-compute` |
| MongoDB | document model, aggregation pipeline, change streams | clean-room | `lift-doc` |

## YugabyteDB (base)

What it is (src): a forked PostgreSQL 15 backend (`src/postgres`, ~3,000 C files) talks through `pggate` to DocDB.
DocDB is a C++ layer (`src/yb/docdb`, `tablet`, `consensus`) over a RocksDB fork (`src/yb/rocksdb`, ~470 files).
Each tablet is its own Raft group with its own RocksDB instances (one for committed data, one for intents).
A separate yb-master holds the catalog and placement. Connection pooling is an Odyssey fork (`src/odyssey`).

Keep:
- PG wire and SQL surface, planner and extensions (pgvector 0.8.0-yb ships, run).
- Per-tablet Raft, hybrid logical clocks, distributed transactions with provisional records (src, docs).
- Automatic tablet splitting, colocated tables, tablegroups, CDC, xCluster (docs, `architecture/design/`).
- Vector LSM: HNSW via usearch/hnswlib, LSM-style immutable index files merged by compaction, MVCC-filtered at read (src: `src/yb/vector_index`, `hnsw`, `ann_methods`; docs: `architecture/design/vector-index.md`).

Weak spots (these feed increment 3):
- Process per connection: 106 ms to connect vs 5.6 ms on CockroachDB (run). Each backend loads its own catalog cache.
- Failover: hard kill of 1 of 3 nodes stalled writes about 14 s, against 5 s or less on CockroachDB, with 0 failed transactions on both (run).
- Throughput: 901 tps vs 1,140 on the same KV script and host (run).
- Two RocksDB instances per tablet (regular + intents): extra write amplification on every transactional write (src, docs).
- Split roles (master + tserver + postgres processes): 35 + 59 threads plus one process per session per node (run).

## CockroachDB (clean-room only)

Observed (run): 1,140 tps, 5.6 ms connect, write stall 5 s or less when 1 of 3 nodes was killed, C-SPANN vector index works (behind a cluster setting, and writes pause while it builds). One Go process, 15 threads, 624 MB RSS.

Take in (docs, CockroachDB SIGMOD 2020 paper and public engineering posts):
- **Symmetric nodes**: no separate master. Catalog lives in the same replicated KV. One binary, one role list.
- **Leaseholder reads and leader leases**: reads served by the lease holder without a Raft round; lease tied to Raft leadership so failover waits on one election, not two.
- **Parallel commits**: commit in one round of consensus by writing the transaction record in STAGING alongside the intents.
- **Multi-region SQL**: `REGIONAL BY ROW`, `GLOBAL` tables, survival goals as table-level DDL.
- **Follower reads** at bounded staleness.
- **Admission control**: per-node work queues that keep foreground latency stable under overload.
- **Session as a lightweight task** (goroutine), which is why connect is cheap.
- **Vector index on distributed KV** (C-SPANN): partition-based ANN that splits and merges like ranges.

## FoundationDB (copy allowed)

Observed (run): 3,050 txn/s from a GIL-bound Python client on one process, so a floor. fdbserver ran 6 threads (single-threaded run loop per role).

Take in (docs, SIGMOD 2021 paper):
- **Deterministic simulation testing**: the whole cluster runs in one process with simulated network, disk and clock, faults injected, every run replayable from a seed. This is the single most valuable thing to take, and it has to be designed in from the start.
- **Unbundled roles**: sequencer, commit proxies, resolvers, log servers and storage servers scale independently.
- **Strict serializability by default** via a central version sequencer and optimistic conflict resolution.
- **Layers**: data models (record, document) built as libraries over one ordered KV. This is the pattern for liftoffDB modules.

## Turso (copy allowed, MIT, Rust)

Observed (run, pyturso 0.8.3): plain WAL mode falls from 1,973 commits/s (1 writer) to 278 at 8 writers, mostly "database is locked". MVCC mode with `BEGIN CONCURRENT` holds 1,869 commits/s at 8 writers, conflicts surface as write-write errors.

Take in (run, docs):
- **Embedded mode**: the engine runs in-process from a file, no server.
- **MVCC concurrent writers** inside one process.
- **Embedded replicas**: a local copy that syncs with a remote primary (docs; not yet run here).
- **Async I/O core** (io_uring) in Rust (docs, src to read).
- Native vector type and index in the SQLite dialect (docs).

## Neon (copy allowed)

Observed (run): 942 tps on the same KV script (between Yugabyte's 901 and CockroachDB's 1,140), 13.7 ms connect. Branch creation took 19 ms on a 130 MB table, and a point-in-time branch from before a 1M-row delete brought all 2M rows back in 21 ms. Writes on a branch stay off main. First full scan after a compute restart ran 7.3 s against 3.8 s warm, since pages come from the pageserver on first read.

Take in (docs):
- **Storage/compute split**: Postgres compute is stateless; WAL goes to safekeepers (Paxos), pages are served by a pageserver from versioned layer files on object storage.
- **Copy-on-write branching**: a branch is a new timeline pointing at a parent LSN, created in O(1).
- **PITR by LSN** and **scale to zero**.

Limit: Neon has one writer per timeline. Its value for liftoffDB is branching and PITR semantics, rebuilt on DocDB's MVCC and snapshots, not its storage layout. Yugabyte already has instant database clone to a point in time (docs), which is the closest starting point.

## MongoDB (clean-room only)

Observed (run): 1,102 ops/s at w:majority from a GIL-bound Python client, 77 threads. `$vectorSearch` refuses on the community server: it needs Atlas or the separate mongot process.

Take in (docs):
- **Document model**: flexible schema with path indexes. In liftoffDB: `jsonb` plus generated path indexes and a document API, not a second storage engine.
- **Aggregation pipeline** as an alternative query surface compiled to SQL plans.
- **Change streams**: resumable, ordered change feed per collection, on top of Yugabyte CDC.
- Wire protocol compatibility is possible later (FerretDB is Apache-2.0 prior art).

## Open questions for later increments

- Storage engine under DocDB: keep the RocksDB fork, or replace it with Vyrm (your Rust LSM aimed at AI workloads). Decided in increment 3.
- Language for rewritten parts: C++ as in Yugabyte, or Rust. Decided in increment 3.
