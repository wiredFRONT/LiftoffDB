import pymongo, random, threading, time
c = pymongo.MongoClient("mongodb://127.0.0.1:27017/?directConnection=true", w="majority")
col = c.t.kv
def worker(stop,cnt):
    n=0
    while not stop[0]:
        k=random.randint(1,100000)
        col.update_one({"_id":k},{"$set":{"v":"x"}},upsert=True); col.find_one({"_id":k}); n+=1
    cnt.append(n)
for th in (1,16):
    stop=[False];cnt=[];ts=[threading.Thread(target=worker,args=(stop,cnt)) for _ in range(th)]
    t0=time.time();[t.start() for t in ts];time.sleep(20);stop[0]=True;[t.join() for t in ts]
    print(f"threads={th} ops/s={sum(cnt)/(time.time()-t0):.0f}")
try:
    col.aggregate([{"$vectorSearch":{"index":"x","path":"e","queryVector":[1,2,3],"numCandidates":10,"limit":1}}]).next()
except Exception as e: print("vectorSearch:", str(e)[:160])
print("version", c.server_info()["version"])
