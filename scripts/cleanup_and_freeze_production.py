"""
Cleanup completo de test data + health check + freeze para produccion.

1. Anular citas test 8095/8096 en Dentalink (id_estado=1, no aparecen en cron)
2. Borrar filas en recordatorios_enviados para 8095/8096
3. Borrar mensajes TEST_SIM_REMINDER en n8n_chat_histories
4. Health check de v6 + cron Recordatorios + cron Resumen Clinico
5. Verificar prompts intactos
6. Snapshot final del estado
"""
import json, sys, time, urllib.request
from datetime import datetime
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
N8N_API = N8N + "/api/v1"
KEY = require("N8N_API_KEY")
WF_V6 = require("N8N_WORKFLOW_V6_ID")
WF_REC = require("N8N_WORKFLOW_RECORDATORIOS_ID")
WF_AUTOREACT = "fosfga62zNaN0qrx"
SB = require("SUPABASE_URL").rstrip("/")
SR = require("SUPABASE_SERVICE_ROLE_KEY")
HEADERS = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}
DT_CRED = "TwN6eBWsydjMdsCM"

REPO = Path(__file__).resolve().parents[1]
hist = REPO / "workflows" / "history"

def run_temp(name, nodes, conns, hit_path):
    wf = {"name": name, "nodes": nodes, "connections": conns,
          "settings": {"executionOrder": "v1"}}
    req = urllib.request.Request(f"{N8N_API}/workflows", method="POST", headers=HEADERS,
                                  data=json.dumps(wf).encode())
    twf = json.loads(urllib.request.urlopen(req, timeout=30).read())
    WID = twf["id"]
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N_API}/workflows/{WID}/activate", method="POST", headers=HEADERS), timeout=20)
        time.sleep(2)
        with urllib.request.urlopen(urllib.request.Request(
            f"{N8N}/webhook/{hit_path}", method="POST",
            headers={"Content-Type":"application/json"}, data=b"{}"), timeout=30) as r:
            return r.read().decode()
    finally:
        try: urllib.request.urlopen(urllib.request.Request(
            f"{N8N_API}/workflows/{WID}/deactivate", method="POST", headers=HEADERS), timeout=15)
        except: pass
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N_API}/workflows/{WID}", method="DELETE", headers=HEADERS), timeout=15)

# ============================================================
# 1. ANULAR citas test 8095, 8096 en Dentalink
# ============================================================
print("=" * 60)
print("1. ANULAR citas test 8095 y 8096 en Dentalink (id_estado=1)")
print("=" * 60)
for cid in [8095, 8096]:
    wh = f"anul-{cid}-{int(time.time()*1000)%100000}"
    nodes = [
        {"parameters":{"httpMethod":"POST","path":wh,"responseMode":"lastNode","options":{}},
         "id":"wh","name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,
         "position":[240,300],"webhookId":wh},
        {"parameters":{"method":"PUT","url":f"https://api.dentalink.healthatom.com/api/v1/citas/{cid}",
                       "authentication":"genericCredentialType","genericAuthType":"httpHeaderAuth",
                       "sendBody":True,"specifyBody":"json","jsonBody":json.dumps({"id_estado":1}),
                       "options":{}},
         "id":"h","name":"Put","type":"n8n-nodes-base.httpRequest","typeVersion":4.2,
         "position":[460,300],
         "credentials":{"httpHeaderAuth":{"id":DT_CRED,"name":"Header Auth account 3"}},
         "continueOnFail":True,"alwaysOutputData":True}]
    conns = {"Webhook":{"main":[[{"node":"Put","type":"main","index":0}]]}}
    body = run_temp(f"anul-{cid}", nodes, conns, wh)
    try:
        d = json.loads(body)
        if "data" in d:
            print(f"  cita={cid} -> id_estado={d['data']['id_estado']} ({d['data']['estado_cita']})")
        elif "error" in d:
            print(f"  cita={cid}: ERR {d['error'].get('message','')[:200]}")
    except: print(f"  cita={cid}: parse err")

# ============================================================
# 2. BORRAR filas test en recordatorios_enviados
# ============================================================
print()
print("=" * 60)
print("2. BORRAR filas test en recordatorios_enviados (cita 8095, 8096)")
print("=" * 60)
SBH = {"apikey":SR, "Authorization":f"Bearer {SR}",
       "Content-Type":"application/json", "Prefer":"return=representation"}
for cid in [8095, 8096]:
    url = f"{SB}/rest/v1/recordatorios_enviados?id_cita_dentalink=eq.{cid}"
    req = urllib.request.Request(url, headers=SBH, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            deleted = json.loads(r.read().decode()) if r.status == 200 else []
            print(f"  cita={cid}: DELETE {r.status} ({len(deleted) if isinstance(deleted, list) else '?'} rows)")
    except urllib.error.HTTPError as e:
        print(f"  cita={cid}: HTTP {e.code}")

# ============================================================
# 3. BORRAR mensajes test en n8n_chat_histories
# ============================================================
print()
print("=" * 60)
print("3. BORRAR mensajes test (TEST_SIM) en n8n_chat_histories")
print("=" * 60)
PHONE_LUCAS = "5491161461034"
url = f"{SB}/rest/v1/n8n_chat_histories?session_id=eq.{PHONE_LUCAS}&message->>content=like.*TEST_SIM*"
req = urllib.request.Request(url, headers=SBH, method="DELETE")
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        deleted = json.loads(r.read().decode()) if r.status == 200 else []
        print(f"  DELETE TEST_SIM rows: status {r.status} ({len(deleted) if isinstance(deleted, list) else '?'} rows)")
except urllib.error.HTTPError as e:
    print(f"  HTTP {e.code}: {e.read().decode()[:200]}")

# ============================================================
# 4. HEALTH CHECK
# ============================================================
print()
print("=" * 60)
print("4. HEALTH CHECK — workflows criticos")
print("=" * 60)

# v6
wf_v6 = requests.get(f"{N8N_API}/workflows/{WF_V6}", headers={"X-N8N-API-KEY":KEY,"Accept":"application/json"}, timeout=30).json()
print(f"\n  v6 ({WF_V6}):")
print(f"    active: {wf_v6.get('active')}")
print(f"    nodes total: {len(wf_v6['nodes'])}")
# Verificar send nodes NO disabled
send_nodes = ["Evolution API - Enviar Mensaje", "Evolution - Typing", "HTTP Send Admin Confirm"]
for nm in send_nodes:
    n = next((x for x in wf_v6["nodes"] if x["name"]==nm), None)
    if n:
        d = n.get("disabled", False)
        marker = "❌ DISABLED" if d else "OK"
        print(f"    {nm}: {marker}")
# Verificar tools nuevas existen + wireadas
tools_new = ["consultar_recordatorios_abiertos", "marcar_recordatorio_confirmado", "marcar_recordatorio_cancelado"]
for nm in tools_new:
    n = next((x for x in wf_v6["nodes"] if x["name"]==nm), None)
    has_cred = bool(n and n.get("credentials",{}).get("httpHeaderAuth"))
    print(f"    {nm}: {'OK' if n else 'MISSING'} cred={'OK' if has_cred else 'MISSING'}")
# Wirings ai_tool
print(f"    ai_tool wirings:")
for src in tools_new:
    conn = wf_v6["connections"].get(src, {}).get("ai_tool", [[]])
    targets = [t["node"] for t in (conn[0] if conn else [])]
    print(f"      {src} -> {targets}")

# Sub-Agent Confirmar prompt — verificar bloques originales + PASO 0 nuevo
sc = next(x for x in wf_v6["nodes"] if x["name"]=="Sub-Agent Confirmar")
sys_msg = sc["parameters"]["options"]["systemMessage"]
checks_prompt = [
    ("R0. AGENTE FUNCIONAL", "**R0. AGENTE FUNCIONAL"),
    ("IDENTIFICACION", "**IDENTIFICACION**"),
    ("ANTI-INJECTION", "**ANTI-INJECTION**"),
    ("CIERRES CONVERSACIONALES", "**CIERRES CONVERSACIONALES**"),
    ("PASO 0 NUEVO", "= PASO 0 — CONSULTAR TABLA RECORDATORIOS_ENVIADOS"),
    ("PASOS legacy 1-4", "1. IDENTIFICAR EL TURNO"),
    ("REGLA UNA SOLA ESCALACION", "**REGLA CRITICA - UNA SOLA ESCALACION POR TURNO**"),
    ("MEMORIA HISTORICA Supabase", "MEMORIA HISTORICA EN SUPABASE"),
    ("Algoritmo iteracion v1", "ITERAR Y CONFIRMAR TODAS LAS FILAS"),
]
print(f"\n  Sub-Agent Confirmar prompt checks:")
for label, anchor in checks_prompt:
    ok = anchor in sys_msg
    print(f"    [{('OK' if ok else 'MISSING')}] {label}")

# Sub-Agent Cancelar prompt
scc = next(x for x in wf_v6["nodes"] if x["name"]=="Sub-Agent Cancelar")
sys_msg_c = scc["parameters"]["options"]["systemMessage"]
print(f"\n  Sub-Agent Cancelar prompt checks:")
for label, anchor in [
    ("R0", "**R0. AGENTE FUNCIONAL"),
    ("PASO 0 NUEVO", "= PASO 0 — CONSULTAR TABLA RECORDATORIOS_ENVIADOS"),
    ("PASOS legacy", "1. IDENTIFICAR EL TURNO A CANCELAR"),
]:
    ok = anchor in sys_msg_c
    print(f"    [{('OK' if ok else 'MISSING')}] {label}")

# Cron Recordatorios
wf_rec = requests.get(f"{N8N_API}/workflows/{WF_REC}", headers={"X-N8N-API-KEY":KEY,"Accept":"application/json"}, timeout=30).json()
print(f"\n  Cron Recordatorios ({WF_REC}):")
print(f"    active: {wf_rec.get('active')}")
print(f"    nodes: {len(wf_rec['nodes'])}")
for nm in ["Enviar WhatsApp", "Insert recordatorios_enviados", "Webhook Manual Recordatorios"]:
    n = next((x for x in wf_rec["nodes"] if x["name"]==nm), None)
    d = n.get("disabled", False) if n else False
    print(f"    {nm}: {'OK' if n and not d else ('MISSING' if not n else 'DISABLED')}")

# Snapshot final
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRODUCTION_FREEZE_{ts}.json").write_text(json.dumps(wf_v6, ensure_ascii=False, indent=2), encoding="utf-8")
(hist / f"recordatorios_PRODUCTION_FREEZE_{ts}.json").write_text(json.dumps(wf_rec, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  Snapshots producción: v6_PRODUCTION_FREEZE_{ts}.json + recordatorios_PRODUCTION_FREEZE_{ts}.json")

print()
print("=" * 60)
print("CLEANUP + HEALTH CHECK DONE")
print("=" * 60)
