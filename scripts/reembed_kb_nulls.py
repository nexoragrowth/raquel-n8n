# -*- coding: utf-8 -*-
"""Re-embebe las filas de knowledge_base con embedding NULL (misma receta que el
panel/bot: 'categoria | titulo\ncontenido', text-embedding-3-small, 1536 dims)."""
import json, sys, urllib.request, psycopg2
sys.stdout.reconfigure(encoding="utf-8")

def load_env(path, keys):
    out = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1); v = v.strip().strip('"').strip("'")
        if k in keys: out[k] = v
    return out

db = load_env(".env", {"SUPABASE_DB_HOST","SUPABASE_DB_PORT","SUPABASE_DB_NAME","SUPABASE_DB_USER","SUPABASE_DB_PASSWORD"})
oa = load_env("../nexora-whatsapp-agent/.env.local", {"OPENAI_API_KEY"})
KEY = oa.get("OPENAI_API_KEY")
if not KEY:
    print("!! falta OPENAI_API_KEY"); sys.exit(1)

def embed(text):
    req = urllib.request.Request("https://api.openai.com/v1/embeddings",
        data=json.dumps({"model":"text-embedding-3-small","dimensions":1536,"input":text}).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())["data"][0]["embedding"]

conn = psycopg2.connect(host=db["SUPABASE_DB_HOST"], port=db["SUPABASE_DB_PORT"],
    dbname=db["SUPABASE_DB_NAME"], user=db["SUPABASE_DB_USER"],
    password=db["SUPABASE_DB_PASSWORD"], sslmode="require", connect_timeout=20)
conn.autocommit = True; cur = conn.cursor()
cur.execute("SELECT id, categoria, titulo, contenido FROM knowledge_base WHERE embedding IS NULL ORDER BY id;")
rows = cur.fetchall()
print(f"filas a re-embeddar: {len(rows)}")
for (rid, cat, tit, cont) in rows:
    text = f"{cat} | {tit}\n{cont}"
    vec = embed(text)
    assert len(vec) == 1536, f"dims {len(vec)}"
    cur.execute("UPDATE knowledge_base SET embedding = %s::vector WHERE id = %s;", ("[" + ",".join(map(str, vec)) + "]", rid))
    print(f"  ✓ id {rid} '{tit}' -> embedding {len(vec)} dims")

cur.execute("SELECT count(*) FROM knowledge_base WHERE embedding IS NULL;")
print("embeddings NULL restantes:", cur.fetchone()[0], "(esperado 0)")
cur.close(); conn.close()
print("✅ re-embed OK — la key funciona")
