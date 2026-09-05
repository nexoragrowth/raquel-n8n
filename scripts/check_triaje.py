# -*- coding: utf-8 -*-
"""
check_triaje.py — UN comando que dice si el triaje está sano. Correr ANTES de cualquier PUT al v6
y cuando algo "anda raro". No cambia nada.

Chequea: tests unitarios (gate 29 + nodos 46), textos vs Banlist vivo (--db), config en Supabase
(activo, piloto, videos activos con URL que responde 200), workflows n8n activos (v6, sombra,
panel, helper), instancia Evolution conectada, y últimas ejecuciones del v6 con error.

Uso: python scripts/check_triaje.py
"""
import json, os, subprocess, sys, urllib.request, urllib.error
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import env, require  # noqa: E402
import psycopg2
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
fallas = []
def ok(msg): print("  ✅", msg)
def bad(msg): print("  ❌", msg); fallas.append(msg)

print("1) Tests")
r = subprocess.run(["node", "triaje/test_gate.js"], capture_output=True, text=True, encoding="utf-8"); (ok if r.returncode == 0 else bad)("gate_red_flags: " + r.stdout.strip().splitlines()[-1])
r = subprocess.run(["node", "tests/test_triaje_nodos.js"], capture_output=True, text=True, encoding="utf-8"); (ok if r.returncode == 0 else bad)("nodos triaje: " + r.stdout.strip().splitlines()[-1])
r = subprocess.run([sys.executable, "tests/test_triaje_textos_banlist.py", "--db"], capture_output=True, text=True, encoding="utf-8"); (ok if r.returncode == 0 else bad)("banlist sobre textos (DB): " + (r.stdout.strip().splitlines() or ["?"])[-1])

print("2) Config en Supabase")
def load_env(path, keys):
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        if k in keys: out[k] = v.strip().strip('"').strip("'")
    return out
db = load_env(".env", {"SUPABASE_DB_HOST","SUPABASE_DB_PORT","SUPABASE_DB_NAME","SUPABASE_DB_USER","SUPABASE_DB_PASSWORD"})
conn = psycopg2.connect(host=db["SUPABASE_DB_HOST"], port=db["SUPABASE_DB_PORT"], dbname=db["SUPABASE_DB_NAME"], user=db["SUPABASE_DB_USER"], password=db["SUPABASE_DB_PASSWORD"], sslmode="require")
cur = conn.cursor()
cur.execute("SELECT activo, telefonos_piloto, modo FROM triaje_config WHERE id=1"); cfg = cur.fetchone()
(ok if cfg else bad)(f"triaje_config: activo={cfg[0] if cfg else None} piloto={cfg[1] if cfg else None} modo={cfg[2] if cfg else None}")
cur.execute("SELECT tipo, opcion, url FROM triaje_videos WHERE activo ORDER BY tipo, opcion"); vids = cur.fetchall()
for tipo, op, url in vids:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=15) as r: ok(f"video {tipo}/op{op} -> HTTP {r.status} ({r.headers.get('Content-Length')} bytes)")
    except Exception as e: bad(f"video {tipo}/op{op} URL no responde: {e}")
if not vids: bad("no hay videos activos")
cur.execute("SELECT count(*) FROM triaje_urgencias_log WHERE created_at > NOW() - INTERVAL '24 hours' AND (razon ILIKE 'error_llm%' OR razon ILIKE 'envio_fallo%' OR razon ILIKE '%NOTIFY_FALLO%' OR razon ILIKE 'config_no_disponible%')")
n = cur.fetchone()[0]; (ok if n == 0 else bad)(f"triaje degradado últimas 24h: {n} caso(s)")
cur.close(); conn.close()

print("3) n8n")
base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/"); key = require("N8N_API_KEY")
def n8n(p):
    with urllib.request.urlopen(urllib.request.Request(f"{base}/api/v1{p}", headers={"X-N8N-API-KEY": key}), timeout=60) as r: return json.loads(r.read().decode())
for wid, nombre in (("O155MqHgOSaNZ9ye", "v6"), ("Gm7ofyGohOJ2bI44", "sombra triaje"), ("jzxb5zUKCaJcvCgp", "panel acciones staff"), ("S5U6tSipzlgFHCkf", "helper notify grupo"), ("Yjl6kyLnALhIfbFX", "health check")):
    try:
        w = n8n(f"/workflows/{wid}"); (ok if w.get("active") else bad)(f"{nombre}: active={w.get('active')} nodos={len(w.get('nodes', []))}")
    except Exception as e: bad(f"{nombre}: {e}")
v6 = n8n("/workflows/O155MqHgOSaNZ9ye")
names = {n["name"] for n in v6["nodes"]}
(ok if "Triaje: Evaluar" in names and "Triaje: Decidir" in names else bad)("nodos Triaje presentes en el v6")
conns = v6["connections"]
(ok if conns["Switch sobre Intent"]["main"][2][0]["node"] == "Triaje: Cargar Config" else bad)("Switch sobre Intent[2] -> Triaje: Cargar Config")
errs = n8n("/executions?workflowId=O155MqHgOSaNZ9ye&status=error&limit=5").get("data", [])
(ok if not errs else bad)(f"ejecuciones del v6 con error (últimas): {[(e['id'], e.get('startedAt','')[:16]) for e in errs] or 'ninguna'}")

print("4) Evolution GO")
enviar = next(n for n in v6["nodes"] if n["name"] == "Evolution API - Enviar Mensaje")
apikey = next(h["value"] for h in enviar["parameters"]["headerParameters"]["parameters"] if h["name"].lower() == "apikey")
try:
    with urllib.request.urlopen(urllib.request.Request(enviar["parameters"]["url"].split("/send/")[0] + "/instance/status", headers={"apikey": apikey}), timeout=20) as r:
        d = json.loads(r.read().decode()).get("data", {}); (ok if d.get("Connected") and d.get("LoggedIn") else bad)(f"instancia: Connected={d.get('Connected')} LoggedIn={d.get('LoggedIn')}")
except Exception as e: bad(f"instancia: {e}")

print("\n" + ("✅ TODO SANO" if not fallas else f"❌ {len(fallas)} problema(s): " + " | ".join(fallas)))
sys.exit(1 if fallas else 0)
