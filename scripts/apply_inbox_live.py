# -*- coding: utf-8 -*-
"""
apply_inbox_live.py — "bandeja en vivo": que el panel muestre el mensaje del paciente EN EL
INSTANTE en que llega a WhatsApp, no 30-45 s después cuando el bot termina de procesarlo.

PROBLEMA (5/9, Lucas: "le mandé un mensaje y no renderizó, hay que hacer F5"): el panel lee
n8n_chat_histories, pero la fila 'human' la escribe la memoria LangChain AL FINAL del turno
(buffer 22 s + Router + sub-agent). Hasta entonces no existe en ningún lado que el panel lea.

FIX (2 partes):
  1. Tabla `mensajes_entrantes_live` (key_id PK, telefono, texto, from_me, push_name, created_at).
  2. v6: nodo Postgres `Inbox Live` colgado de `Edit Fields - Extraer Datos` como RAMA MUERTA
     (misma forma que `Get Paciente Context`: nadie lo referencia, onError continue) que inserta
     cada mensaje crudo apenas entra (antes del buffer, del kill-switch de humano, de todo).
  El panel (nexora-whatsapp-agent lib/chat-data.ts + conversaciones-data.ts) mergea esas filas
  como burbujas "pendientes" hasta que aparece la fila real en memoria (dedupe por texto).

Blast radius: 1 nodo nuevo sin salidas, 1 conexión agregada (no se cambia ninguna existente).
Backup PRE/POST, webhookId verificado, dry-run con diff.

Uso: python scripts/apply_inbox_live.py [--tabla] [--apply]
"""
import argparse, copy, json, os, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import env, require  # noqa: E402
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
WF_ID = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
PG_CRED = {"id": "TpYhZX4UT61xAKSV", "name": "Postgres Supabase Nexora v3"}
NODE = "Inbox Live"
UPSTREAM = "Edit Fields - Extraer Datos"
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}

DDL = """
CREATE TABLE IF NOT EXISTS public.mensajes_entrantes_live (
  key_id     TEXT PRIMARY KEY,               -- Info.ID de WhatsApp (dedupe natural)
  telefono   TEXT NOT NULL,
  texto      TEXT NOT NULL,
  from_me    BOOLEAN NOT NULL DEFAULT false,  -- true = lo mandó el consultorio (staff), no el paciente
  push_name  TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inbox_live_tel_created ON public.mensajes_entrantes_live (telefono, created_at DESC);
"""

# Inserta solo si hay texto (multimedia sin caption no aporta al panel). $1..$5 por queryReplacement:
# n8n evalúa cada expresión por separado (mismo patrón probado que "Postgres - Save fromMe").
QUERY = ("INSERT INTO mensajes_entrantes_live (key_id, telefono, texto, from_me, push_name) "
         "SELECT $1, $2, $3, $4::boolean, $5 WHERE length($3) > 0 AND length($2) > 0 ON CONFLICT (key_id) DO NOTHING")
REPL = "={{ $json.key_id }}, ={{ $json.phone }}, ={{ $json.text || '' }}, ={{ $json.fromMe ? 'true' : 'false' }}, ={{ $json.pushName || '' }}"

def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    req = urllib.request.Request(f"{base}/api/v1{path}", data=json.dumps(payload).encode() if payload is not None else None,
                                 method=method, headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r: return json.loads(r.read().decode())

def crear_tabla():
    import psycopg2
    def load_env(path, keys):
        out = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1)
            if k in keys: out[k] = v.strip().strip('"').strip("'")
        return out
    db = load_env(str(ROOT / ".env"), {"SUPABASE_DB_HOST","SUPABASE_DB_PORT","SUPABASE_DB_NAME","SUPABASE_DB_USER","SUPABASE_DB_PASSWORD"})
    conn = psycopg2.connect(host=db["SUPABASE_DB_HOST"], port=db["SUPABASE_DB_PORT"], dbname=db["SUPABASE_DB_NAME"], user=db["SUPABASE_DB_USER"], password=db["SUPABASE_DB_PASSWORD"], sslmode="require")
    conn.autocommit = True; cur = conn.cursor(); cur.execute(DDL); cur.close(); conn.close()
    print("✅ tabla mensajes_entrantes_live lista")

def build(wf):
    new = copy.deepcopy(wf); nodes = new["nodes"]; conns = new["connections"]; names = {n["name"]: n for n in nodes}
    if UPSTREAM not in names: sys.exit(f"ERROR: falta {UPSTREAM!r}")
    up = names[UPSTREAM]
    node = {"id": "inbox-live", "name": NODE, "type": "n8n-nodes-base.postgres", "typeVersion": 2.5,
            "position": [up["position"][0] + 260, up["position"][1] + 380],
            "parameters": {"operation": "executeQuery", "query": QUERY, "options": {"queryReplacement": REPL}},
            "credentials": {"postgres": PG_CRED}, "onError": "continueRegularOutput", "alwaysOutputData": False}
    cambios = []
    if NODE in names:
        prev = names[NODE]; node["id"] = prev["id"]; node["position"] = prev["position"]; nodes[nodes.index(prev)] = node; cambios.append(f"ACTUALIZA {NODE!r}")
    else:
        nodes.append(node); cambios.append(f"AGREGA {NODE!r} (Postgres, rama muerta)")
    targets = [c["node"] for c in conns[UPSTREAM]["main"][0]]
    if NODE not in targets:
        conns[UPSTREAM]["main"][0].append({"node": NODE, "type": "main", "index": 0}); cambios.append(f"CONECTA {UPSTREAM}[0] -> {NODE} (se suma a {targets})")
    else:
        cambios.append("conexión ya existía (idempotente)")
    return new, cambios

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--tabla", action="store_true")
    args = ap.parse_args()
    if args.tabla: crear_tabla(); return
    wf = api(f"/workflows/{WF_ID}")
    print(f"v6 vivo: {len(wf['nodes'])} nodos, activo={wf['active']}, updatedAt={wf.get('updatedAt')}")
    new, cambios = build(wf)
    print("CAMBIOS:"); [print("  -", c) for c in cambios]
    print("Query:", QUERY); print("Params:", REPL)
    if not args.apply: print("[DRY-RUN] no se tocó n8n. --tabla crea la tabla; --apply hace el PUT."); return
    ts = time.strftime("%Y%m%d_%H%M%S"); hist = ROOT / "workflows" / "history"; hist.mkdir(parents=True, exist_ok=True)
    (hist / f"v6_PRE_inbox_live_{ts}.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    body = {k: new[k] for k in PUT_KEYS if k in new}; body["settings"] = {k: v for k, v in (new.get("settings") or {}).items() if k in SETTINGS_OK}
    assert next(n for n in body["nodes"] if n["name"] == "Webhook - Evolution API")["webhookId"] == "evo-webhook-v2"
    api(f"/workflows/{WF_ID}", "PUT", body)
    after = api(f"/workflows/{WF_ID}")
    (hist / f"v6_POST_inbox_live_{ts}.json").write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = any(n["name"] == NODE for n in after["nodes"]) and NODE in [c["node"] for c in after["connections"][UPSTREAM]["main"][0]]
    print("verificación:", "OK" if ok else "FALLÓ"); print(f"✅ v6: {len(after['nodes'])} nodos" if ok else "revisar")

if __name__ == "__main__":
    main()
