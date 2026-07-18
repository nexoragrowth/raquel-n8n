import json, sys, time, urllib.request, urllib.error
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\Users\not\Desktop\proyectos\raquel-n8n\scripts")
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
CRED_PG = "EWhpNhb6tkGg1OTp"
H = {"X-N8N-API-KEY": KEY, "accept": "application/json", "content-type": "application/json"}

def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(N8N + path, method=method, headers=H, data=data)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        return json.loads(raw) if raw else None

Q = "SELECT 1 AS ok, now() AS ts, (SELECT count(*) FROM n8n_chat_histories)::int AS memoria_filas;"
for intento in range(1, 4):
    ts = int(time.time() * 1000) % 10**9
    wh = f"ping-db-{ts}"
    nodes = [
        {"parameters": {"httpMethod": "POST", "path": wh, "responseMode": "lastNode",
                        "responseData": "allEntries", "options": {}},
         "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
         "position": [200, 300], "webhookId": wh},
        {"parameters": {"operation": "executeQuery", "query": Q, "options": {}},
         "id": "q", "name": "Q", "type": "n8n-nodes-base.postgres", "typeVersion": 2.5,
         "position": [420, 300],
         "credentials": {"postgres": {"id": CRED_PG, "name": "Postgres Supabase Nexora v2"}}},
    ]
    wf = api("POST", "/api/v1/workflows",
             {"name": "TEMP-pingdb", "nodes": nodes,
              "connections": {"Webhook": {"main": [[{"node": "Q", "type": "main", "index": 0}]]}},
              "settings": {"executionOrder": "v1"}})
    wid = wf["id"]
    try:
        api("POST", f"/api/v1/workflows/{wid}/activate")
        time.sleep(2)
        req = urllib.request.Request(f"{N8N}/webhook/{wh}", method="POST",
                                     headers={"Content-Type": "application/json"}, data=b"{}")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                print(f"intento {intento}: CONEXION OK -> {r.read().decode()[:200]}")
                break
        except urllib.error.HTTPError as e:
            print(f"intento {intento}: fallo (HTTP {e.code})")
    finally:
        try:
            api("POST", f"/api/v1/workflows/{wid}/deactivate")
        except Exception:
            pass
        api("DELETE", f"/api/v1/workflows/{wid}")
    if intento < 3:
        print("   espero 45s a que se liberen conexiones...")
        time.sleep(45)
