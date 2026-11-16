import fdb, time, random, threading
fdb.api_version(730)
db = fdb.open()
N=100000
@fdb.transactional
def upsert_read(tr, k):
    key = b'kv/' + k.to_bytes(4,'big')
    tr[key] = b'x'
    return tr[key]
def worker(stop, cnt):
    c=0
    while not stop[0]:
        upsert_read(db, random.randint(1,N)); c+=1
    cnt.append(c)
for threads in (1, 16):
    stop=[False]; cnt=[]; ts=[threading.Thread(target=worker,args=(stop,cnt)) for _ in range(threads)]
    t0=time.time(); [t.start() for t in ts]; time.sleep(20); stop[0]=True; [t.join() for t in ts]
    print(f"threads={threads} txn/s={sum(cnt)/(time.time()-t0):.0f}")
