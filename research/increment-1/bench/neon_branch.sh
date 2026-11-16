cd $NEON_SRC
export PATH=$PWD/target/release:$PATH NEON_REPO_DIR=$NEON_DATA/repo POSTGRES_DISTRIB_DIR=$PWD/pg_install LD_LIBRARY_PATH=$PWD/pg_install/v17/lib
P=$PWD/pg_install/v17/bin; C="-h 127.0.0.1 -p 55432 -U cloud_admin -d postgres"
ms(){ date +%s%3N; }
$P/psql $C -Atc "create table big as select g as id, md5(g::text) as v from generate_series(1,2000000) g; select pg_size_pretty(pg_total_relation_size('big'));"
LSN=$($P/psql $C -Atc "select pg_current_wal_flush_lsn()"); echo "lsn_before_delete=$LSN"
$P/psql $C -Atc "delete from big where id <= 1000000; select 'main rows after delete', count(*) from big;"
sleep 2
t=$(ms); neon_local timeline branch --branch-name b1 >/dev/null; echo "branch_create_ms=$(( $(ms)-t ))"
t=$(ms); neon_local endpoint create b1ep --branch-name b1 --pg-version 17 --pg-port 55440 --external-http-port 55441 --internal-http-port 55442 >/dev/null 2>&1; neon_local endpoint start b1ep >/dev/null 2>&1; echo "branch_endpoint_create_start_ms=$(( $(ms)-t ))"
$P/psql -h 127.0.0.1 -p 55440 -U cloud_admin -d postgres -Atc "update big set v='branch' where id=1500000; select 'b1 rows', count(*) from big; select 'b1 changed', v from big where id=1500000;"
$P/psql $C -Atc "select 'main v unchanged', v from big where id=1500000;"
t=$(ms); neon_local timeline branch --branch-name pitr --ancestor-branch-name main --ancestor-start-lsn $LSN >/dev/null; echo "pitr_branch_create_ms=$(( $(ms)-t ))"
neon_local endpoint create pitrep --branch-name pitr --pg-version 17 --pg-port 55450 --external-http-port 55451 --internal-http-port 55452 >/dev/null 2>&1; neon_local endpoint start pitrep >/dev/null 2>&1
$P/psql -h 127.0.0.1 -p 55450 -U cloud_admin -d postgres -Atc "select 'pitr rows (before delete)', count(*) from big;"
t=$(ms); neon_local endpoint stop main >/dev/null 2>&1; neon_local endpoint start main >/dev/null 2>&1; echo "main_compute_restart_ms=$(( $(ms)-t ))"
t=$(ms); $P/psql $C -Atc "select 'cold read', count(*) from big;"; echo "cold_full_scan_ms=$(( $(ms)-t ))"
t=$(ms); $P/psql $C -Atc "select 'warm read', count(*) from big;"; echo "warm_full_scan_ms=$(( $(ms)-t ))"
du -sh $NEON_DATA/repo/pageserver_1 $NEON_DATA/repo/local_fs_remote_storage 2>/dev/null
