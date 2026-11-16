# Increment 3: what to rewrite in Yugabyte's baseline

Draft for review. Each row names the Yugabyte part, why it changes (with evidence from increments 1 and 2),
what replaces it, and how we will know it worked. Order is the proposed build order.

Evidence tags as in increment 2: **run**, **src**, **docs**.

## Build order

| # | Area | Yugabyte today | Rewrite | Done when |
|---|---|---|---|---|
| 1 | Test harness | Integration tests on real processes (`src/yb/integration-tests`, ~230 files, src) | Deterministic simulation: whole cluster in one process, simulated clock, disk and network, seeded faults, replayable (FoundationDB pattern) | A seeded run kills nodes, partitions the network and corrupts a disk write, and replays bit-for-bit |
| 2 | Sessions | One OS process per connection; each loads its own catalog cache. 106 ms connect (run) | Stage A: pooled sessions through the existing Odyssey connection manager (`src/odyssey`, src). Stage B: threaded backend with a shared catalog cache | Connect under 10 ms; idle session memory under 1 MB; 10k sessions on one node |
| 3 | Failover | 1-of-3 hard kill stalled writes about 14 s (run). Lease 2 s and 6 missed heartbeats before election (src: `ht_lease_duration_ms`, `leader_failure_max_missed_heartbeat_periods`) | Leader leases tied to Raft leadership, faster failure detection, pre-vote; clean-room from CockroachDB's public design | Same kill test stalls 3 s or less, 0 failed transactions |
| 4 | Storage | RocksDB fork (`src/yb/rocksdb`, ~470 files, src); two instances per tablet, committed data and intents (docs) | One engine per tablet with intents in-band, behind a storage trait. Candidate: Vyrm | Write amplification per transactional write measured and lower; same correctness suite passes |
| 5 | Commit | Transaction status tablet plus intent resolution, more than one consensus round on commit (docs) | 1-round commit: record STAGING with the last write batch (clean-room, parallel commits idea) | p50 commit latency drops by one consensus round on the KV bench |
| 6 | Control plane | Separate yb-master role, 35 threads on top of tserver's 59 (run) | Symmetric nodes: catalog and placement in system tablets every node can host | One binary, one process per node |
| 7 | Vector | Vector LSM over usearch/hnswlib, MVCC-filtered (src, docs) | Keep. Add filtered ANN with predicates pushed into the index and vector+row co-location | Filtered top-k recall and latency tracked in the bench |

## Modules on top (not rewrites)

- `lift-doc`: document API and path indexes over `jsonb`; Mongo-style aggregation compiled to SQL plans; change streams over CDC.
- `lift-branch`: copy-on-write branches and point-in-time restore on DocDB snapshots and Yugabyte's database clone (docs), with Neon's timeline model as the reference.
- `lift-embed` and `lift-sync`: in-process engine from Turso (MIT, Rust) using liftoffDB's row format, syncing with a cluster over CDC.
- `lift-placement`: multi-region DDL (`REGIONAL BY ROW`, `GLOBAL`) over Yugabyte tablespaces.

## Keep as is

- PostgreSQL parser, planner, executor and extension ABI (`src/postgres`, ~3,000 C files). Rewriting this would cost Postgres compatibility, which is the point of the base.
- `pggate`, the boundary between the PG backend and DocDB. It becomes the stable seam that lets rewritten layers slot in under the SQL layer.
- Per-tablet Raft, HLC, tablet splitting, CDC and xCluster, until items 3 to 6 replace parts of them.

## Approach

Strangler pattern: every rewrite lands behind an existing seam (`pggate`, the storage interface, the consensus interface),
runs in the simulator first (item 1), then replaces the old part. Nothing is rewritten without a test that fails on the old part.

## Open decision (one per pass)

**Language for rewritten parts.** This gates items 1, 3, 4, 5 and 6.

1. **Rust:** matches your full-Rust stack and Vyrm; new code is memory-safe; cost is a C++/Rust boundary at each seam for years.
2. **C++:** same language as Yugabyte; no boundary cost; every rewrite stays in the codebase it replaces.

Storage choice (Vyrm or a cleaned RocksDB) follows from this answer and comes next.
