\set k random(1, 100000)
INSERT INTO kv(k,v) VALUES (:k, 'x') ON CONFLICT (k) DO UPDATE SET v=excluded.v;
SELECT v FROM kv WHERE k = :k;
