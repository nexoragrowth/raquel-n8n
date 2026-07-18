import json, sys, time, urllib.request, urllib.error
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\Users\not\Desktop\proyectos\raquel-n8n\scripts")
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
CRED_PG = "EWhpNhb6tkGg1OTp"
H = {"X-N8N-API-KEY": KEY, "accept": "application/json", "content-type": "application/json"}

def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(N8N + path, method=method, headers=H, data=data)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        return json.loads(raw) if raw else None

def run_sql(query, tag):
    ts = int(time.time() * 1000) % 10**9
    wh = f"sql-{tag}-{ts}"
    nodes = [
        {"parameters": {"httpMethod": "POST", "path": wh, "responseMode": "lastNode",
                        "responseData": "allEntries", "options": {}},
         "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
         "position": [200, 300], "webhookId": wh},
        {"parameters": {"operation": "executeQuery", "query": query, "options": {}},
         "id": "q", "name": "Q", "type": "n8n-nodes-base.postgres", "typeVersion": 2.5,
         "position": [420, 300],
         "credentials": {"postgres": {"id": CRED_PG, "name": "Postgres Supabase Nexora v2"}}},
    ]
    wf = api("POST", "/api/v1/workflows",
             {"name": f"TEMP-{tag}", "nodes": nodes,
              "connections": {"Webhook": {"main": [[{"node": "Q", "type": "main", "index": 0}]]}},
              "settings": {"executionOrder": "v1"}})
    wid = wf["id"]
    out = None
    try:
        api("POST", f"/api/v1/workflows/{wid}/activate")
        time.sleep(2)
        req = urllib.request.Request(f"{N8N}/webhook/{wh}", method="POST",
                                     headers={"Content-Type": "application/json"}, data=b"{}")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                out = json.loads(r.read())
        except urllib.error.HTTPError as e:
            out = {"error": e.read().decode()[:300]}
    finally:
        try:
            api("POST", f"/api/v1/workflows/{wid}/deactivate")
        except Exception:
            pass
        api("DELETE", f"/api/v1/workflows/{wid}")
    return out

# 1) canario: logger volvio?
print("1) esperando logger en verde (hasta 90s)...")
ok = False
for _ in range(6):
    lex = api("GET", "/api/v1/executions?workflowId=xsXeHp7WLXnFQc3o&limit=2").get("data", [])
    sts = [e["status"] for e in lex]
    print(f"   logger: {[(e['startedAt'][11:19], e['status']) for e in lex]}")
    if sts and sts[0] == "success":
        ok = True
        break
    time.sleep(20)
print(f"   DB {'VOLVIO' if ok else 'AUN CAIDA'}")
if not ok:
    sys.exit(1)

# 2) extraer los 7 recordatorios del exec fallido 230100
print("\n2) extrayendo recordatorios del exec 230100...")
d = api("GET", "/api/v1/executions/230100?includeData=true")
rd = d["data"]["resultData"]["runData"]
items = []
for run in rd.get("Preparar mensaje", []):
    for arr in run.get("data", {}).get("main", []) or []:
        for item in (arr or []):
            items.append(item.get("json", {}))
print(f"   items en 'Preparar mensaje': {len(items)}")
if items:
    print("   keys:", sorted(items[0].keys()))

def g(it, *keys, default=""):
    for k in keys:
        if it.get(k) not in (None, ""):
            return it[k]
    return default

# 3) chequear existentes + insertar faltantes
vals = []
for it in items:
    tel = str(g(it, "phone", "telefono"))
    jid = str(g(it, "remoteJid", "chat_remote_jid"))
    cita = g(it, "cita_id", "id_cita_dentalink", default="NULL")
    pac = g(it, "id_paciente", "id_paciente_dentalink", "paciente_id", default="NULL")
    nom = str(g(it, "nombre", "nombre_paciente", "paciente")).replace("'", "''")
    fecha = str(g(it, "fecha", "fecha_turno", "fecha_target"))
    hora = str(g(it, "hora", "hora_turno"))
    tipo = str(g(it, "tipo", default="48h"))
    vals.append(f"('{tel}','{jid}',{cita},{pac},'{nom}','{fecha}','{hora}','{tipo}','230100-backfill')")

if not vals:
    print("   SIN ITEMS - revisar manualmente")
    sys.exit(1)

Q = f"""
INSERT INTO recordatorios_enviados
  (telefono, chat_remote_jid, id_cita_dentalink, id_paciente_dentalink,
   nombre_paciente, fecha_turno, hora_turno, tipo, workflow_execution_id)
SELECT v.* FROM (VALUES {', '.join(vals)}) AS v(telefono, chat_remote_jid, id_cita_dentalink,
   id_paciente_dentalink, nombre_paciente, fecha_turno, hora_turno, tipo, workflow_execution_id)
WHERE NOT EXISTS (
  SELECT 1 FROM recordatorios_enviados r
  WHERE r.id_cita_dentalink::text = v.id_cita_dentalink::text
    AND r.fecha_turno::text = v.fecha_turno::text
)
RETURNING id, nombre_paciente, fecha_turno;
""".strip()
# cast de tipos en el VALUES: fecha como date
Q = Q.replace("AS v(telefono", "AS v(telefono")

print("\n3) insertando (con dedup por cita+fecha)...")
res = run_sql(Q, "backfill")
print("   resultado:", json.dumps(res, ensure_ascii=False)[:500])

# verificacion final
chk = run_sql("SELECT count(*)::int AS n FROM recordatorios_enviados WHERE workflow_execution_id = '230100-backfill';", "chk")
print("   filas backfill:", chk)
