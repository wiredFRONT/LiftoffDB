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

## Decision: Rust, if Rust can reach every item (Nov 16)

Checked item by item. Crate versions read from crates.io on Nov 16 2026; repo facts from GitHub the same day.
Rust code reaches the C++ DocDB through `cxx` 1.0.205 at the seams named under Approach.

| # | Item | Rust reaches it? | Crates and prior art |
|---|---|---|---|
| 1 | Crash simulator | Yes | `madsim` 0.2.34 (deterministic runtime, used by RisingWave), `turmoil` 0.7.2 (simulated network for tokio); Turso ships its own deterministic simulator (MIT, active) |
| 2A | Pooled sessions | Yes | `pgwire` 0.42.3 (Postgres wire protocol); PgCat and PgDog are Rust poolers (docs, not checked here) |
| 2B | Threaded backend | **No, not with Postgres compatibility** | See gap below |
| 3 | Faster failover | Yes | `openraft` 0.10.0 (leader lease, pre-vote); `raft` 0.7.0 is TiKV's Raft (last release 2023, maintained in the TiKV tree, Apache-2.0) |
| 4 | Storage per tablet | Yes | Vyrm; `fjall` 3.1.13; TiKV's engine traits as the seam pattern |
| 5 | One-round commit | Yes | TiKV's async commit and 1PC (Rust, Apache-2.0) as prior art; the protocol itself is language-neutral |
| 6 | Single node role | Yes | TiKV raftstore (multi-Raft in Rust) and `openraft` for the catalog group |
| 7 | Filtered vector search | Yes | Qdrant's filterable HNSW (Rust, Apache-2.0); `usearch` 2.26.6 (Rust bindings, C++ core, already in Yugabyte); `lancedb` 0.41.0; `hnsw_rs` 0.3.5 |

### Gap: threaded backend (2B)

The parser, planner, executor and extension ABI are Postgres C code (`src/postgres`, ~3,000 files), kept for compatibility.
Making them run as threads instead of processes means changing that C code (its process-global state), not writing Rust.
The only Rust route is replacing the SQL engine (`datafusion` 55.2.0, `sqlparser` 0.64.0, `pgwire`), as GreptimeDB and RisingWave do,
and that drops Postgres extension compatibility (pgvector, PostGIS and the rest), which contradicts the base choice.
`pgrx` 0.20.0 writes Postgres extensions in Rust but runs inside the same process model, so it does not close the gap.

Status: 2B is held. Everything else proceeds in Rust. 2A (pooling) cuts connect time and session count without touching the backend.

Storage choice (Vyrm or `fjall`) comes after 2B is settled.
