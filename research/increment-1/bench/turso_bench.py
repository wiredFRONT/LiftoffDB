import turso, random, threading, time, os, sys
def run(path, feats, mode, threads, secs=15):
    for f in os.listdir('.'):
        if f.startswith(path): os.remove(f)
    c0 = turso.connect(path, experimental_features=feats, isolation_level=None)
    if mode=='mvcc':
        try: c0.execute("PRAGMA journal_mode = 'experimental_mvcc'").fetchall()
        except Exception as e: print("mvcc pragma:", e)
    c0.execute("create table kv(k integer primary key, v text)"); c0.commit() if c0.in_transaction else None
    stop=[False]; cnt=[]; errs=[]
    def w():
        c = turso.connect(path, experimental_features=feats, isolation_level=None); n=0; e=0
        while not stop[0]:
            k=random.randint(1,100000)
            try:
                c.execute("BEGIN CONCURRENT" if mode=='mvcc' else "BEGIN")
                c.execute("insert into kv(k,v) values(?,'x') on conflict(k) do update set v=excluded.v",(k,))
                c.execute("select v from kv where k=?",(k,)).fetchall()
                c.execute("COMMIT"); n+=1
            except Exception as ex:
                e+=1
                try: c.execute("ROLLBACK")
                except Exception: pass
                if e==1: errs.append(str(ex)[:120])
        cnt.append((n,e))
    ts=[threading.Thread(target=w) for _ in range(threads)]; t0=time.time()
    [t.start() for t in ts]; time.sleep(secs); stop[0]=True; [t.join() for t in ts]
    dt=time.time()-t0; print(f"{mode} threads={threads} commits/s={sum(n for n,_ in cnt)/dt:.0f} errors/s={sum(e for _,e in cnt)/dt:.0f} first_err={errs[:1]}")
print("pyturso", turso.sqlite_version)
run("wal.db", None, "wal", 1); run("wal.db", None, "wal", 8)
run("mv.db", "mvcc", "mvcc", 1); run("mv.db", "mvcc", "mvcc", 8)
