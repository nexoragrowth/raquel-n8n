"""
Simula un mensaje entrante de Evolution API al v6 (sin necesidad de que
el paciente real mande algo desde WA). POSTea al webhook /webhook/evolution-v2
con el mismo shape que Evolution envia.

Pasos:
1. Disable nodes de send en v6 (Enviar Mensaje, Typing, Admin Confirm)
2. POST al webhook simulando mensaje
3. Sleep 8s para que la ejecucion termine
4. Leer ultima execution del v6 + reportar tools llamadas + outputs
5. Re-enable send nodes

Uso:
  python scripts/simulate_v6_message.py "Confirmados"
  python scripts/simulate_v6_message.py "Confirmo el de Jana"
"""
import json
import sys
import time
import io
import uuid
import urllib.request
from datetime import datetime
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF_V6 = require("N8N_WORKFLOW_V6_ID")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}

REPO = Path(__file__).resolve().parents[1]
hist = REPO / "workflows" / "history"

MSG = sys.argv[1] if len(sys.argv) > 1 else "Confirmados"
PHONE = "5491161461034"
PUSH_NAME = "Lucas (TEST SIMULATED)"
SEND_NODES = ["Evolution API - Enviar Mensaje", "Evolution - Typing", "HTTP Send Admin Confirm"]
# Si KEEP_SEND_ENABLED=True, no disable los nodos de send (autorizado por Lucas
# porque todos los turnos test/recordatorios apuntan a su phone, no a pacientes reales)
KEEP_SEND_ENABLED = True

print(f"Mensaje a simular: '{MSG}'")
print(f"Phone: {PHONE}\n")

def put_v6(wf_obj):
    allowed = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
               "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
               "executionOrder", "callerPolicy", "callerIds"}
    settings = {k: v for k, v in (wf_obj.get("settings") or {}).items() if k in allowed}
    payload = {"name": wf_obj["name"], "nodes": wf_obj["nodes"],
               "connections": wf_obj["connections"], "settings": settings}
    if wf_obj.get("staticData") is not None:
        payload["staticData"] = wf_obj["staticData"]
    r = requests.put(f"{N8N}/api/v1/workflows/{WF_V6}", headers=H,
                     data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=60)
    return r.status_code, r.text

def set_send_disabled(disabled):
    wf = requests.get(f"{N8N}/api/v1/workflows/{WF_V6}", headers=H, timeout=30).json()
    changed = []
    for n in wf["nodes"]:
        if n["name"] in SEND_NODES:
            if disabled:
                if not n.get("disabled"):
                    n["disabled"] = True
                    changed.append(n["name"])
            else:
                if n.get("disabled"):
                    n.pop("disabled", None)
                    changed.append(n["name"])
    if not changed:
        print(f"  (ningun cambio en send nodes)")
        return 200
    code, txt = put_v6(wf)
    print(f"  PUT {code} — toggled disabled={disabled} en: {changed}")
    if code >= 400:
        print(f"  {txt[:300]}")
    return code

# Backup pre
wf_pre = requests.get(f"{N8N}/api/v1/workflows/{WF_V6}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRE_SIM_{ts}.json").write_text(
    json.dumps(wf_pre, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre v6 -> v6_PRE_SIM_{ts}.json")

try:
    if KEEP_SEND_ENABLED:
        print(f"\n[1/4] SKIP disable send (KEEP_SEND_ENABLED=True) — send va a Lucas")
    else:
        print(f"\n[1/4] Disable send nodes ...")
        if set_send_disabled(True) >= 400:
            sys.exit(1)
        time.sleep(2)

    print(f"\n[2/4] POST simulated webhook ...")
    # Shape Evolution API messages.upsert
    body = {
        "event": "messages.upsert",
        "instance": "raquel",
        "data": {
            "key": {
                "remoteJid": f"{PHONE}@s.whatsapp.net",
                "fromMe": False,
                "id": f"SIM_{uuid.uuid4().hex[:16].upper()}",
            },
            "pushName": PUSH_NAME,
            "message": {
                "conversation": MSG,
            },
            "messageType": "conversation",
            "messageTimestamp": int(time.time()),
            "instanceId": "test-sim",
            "source": "android",
        },
        "destination": "https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2",
        "date_time": datetime.utcnow().isoformat(),
        "sender": f"{PHONE}@s.whatsapp.net",
        "server_url": "https://evolution.example",
        "apikey": "sim",
    }
    url = "https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2"
    req = urllib.request.Request(url, method="POST",
                                  headers={"Content-Type": "application/json"},
                                  data=json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = r.read().decode()
            print(f"  webhook status: {r.status}")
            print(f"  webhook body (300): {resp[:300]}")
    except urllib.error.HTTPError as e:
        print(f"  webhook HTTP {e.code}: {e.read().decode()[:300]}")
    except Exception as ex:
        print(f"  webhook err: {ex}")

    print(f"\n[3/4] Esperando 20s para que termine ejecucion ...")
    time.sleep(20)

    print(f"\n[4/4] Buscando MI exec entre las ultimas 20 ...")
    execs = requests.get(f"{N8N}/api/v1/executions?workflowId={WF_V6}&limit=20",
                         headers=H, timeout=30).json().get("data", [])
    if not execs:
        print("  Sin ejecuciones recientes.")
        sys.exit(0)
    eid = None
    for e in execs:
        try:
            dd = requests.get(f"{N8N}/api/v1/executions/{e['id']}?includeData=true",
                              headers=H, timeout=30).json()
            ef = dd.get("data", {}).get("resultData", {}).get("runData", {}).get("Edit Fields - Extraer Datos", [])
            if ef:
                kid = ef[0]["data"]["main"][0][0]["json"].get("key_id", "")
                if "SIM_" in kid and kid in body["data"]["key"]["id"]:
                    eid = e["id"]
                    print(f"  Encontrada: exec={eid} key_id={kid}")
                    break
        except Exception: pass
    if not eid:
        eid = execs[0]["id"]
        print(f"  No match SIM_ exacto, uso ultima exec={eid}")

    d = requests.get(f"{N8N}/api/v1/executions/{eid}?includeData=true",
                     headers=H, timeout=30).json()
    rd = d.get("data", {}).get("resultData", {}).get("runData", {})
    last = d.get("data", {}).get("resultData", {}).get("lastNodeExecuted", "?")
    err = d.get("data", {}).get("resultData", {}).get("error")
    print(f"\n  exec {eid}: status={d.get('status')} last_node='{last}'")
    if err:
        print(f"  ERROR: {json.dumps(err, ensure_ascii=False)[:400]}")
    print(f"\n  Nodos ejecutados ({len(rd)}):")
    for nname in rd.keys():
        print(f"    - {nname}")

    # Detalles clave
    keys_of_interest = [
        "Router - Clasificar Intent", "Router LM",
        "Sub-Agent Confirmar", "LM Sub-Agent Confirmar",
        "consultar_recordatorios_abiertos", "confirmar_turno",
        "marcar_recordatorio_confirmado", "escalar_a_secretaria",
        "ver_turnos_paciente", "buscar_paciente_dentalink",
        "Banlist Validator", "Split en Mensajes",
    ]
    print(f"\n  === Detalles de nodos relevantes ===")
    for k in keys_of_interest:
        if k not in rd:
            continue
        runs = rd[k]
        print(f"\n  >>> {k} ({len(runs)} run(s))")
        for i, run in enumerate(runs[:3]):
            main = run.get("data", {}).get("main", [])
            ai_tool = run.get("data", {}).get("ai_tool", [])
            ai_lm = run.get("data", {}).get("ai_languageModel", [])
            err_r = run.get("error")
            if err_r:
                print(f"    run {i} ERROR: {str(err_r)[:300]}")
                continue
            if ai_tool:
                for ent in (ai_tool[0] if isinstance(ai_tool[0], list) else ai_tool)[:2]:
                    if isinstance(ent, list): ent = ent[0] if ent else {}
                    js = ent.get("json", {}) if isinstance(ent, dict) else {}
                    resp = js.get("response", "")
                    print(f"    run {i} ai_tool resp: {str(resp)[:400]}")
            if ai_lm:
                for ent in (ai_lm[0] if isinstance(ai_lm[0], list) else ai_lm)[:2]:
                    if isinstance(ent, list): ent = ent[0] if ent else {}
                    js = ent.get("json", {}) if isinstance(ent, dict) else {}
                    resp = js.get("response", {}).get("generations", [[{}]])[0][0].get("text", "")
                    tokens = js.get("tokenUsage", {})
                    print(f"    run {i} ai_lm text: {str(resp)[:300]}")
                    print(f"    run {i} tokens: {tokens}")
            if main and main[0]:
                for j, item in enumerate(main[0][:2]):
                    js = item.get("json", {})
                    print(f"    run {i} out[{j}] keys: {list(js.keys())[:10]}")
                    if "output" in js:
                        print(f"      output: {str(js['output'])[:400]}")
                    if "message" in js:
                        print(f"      message: {str(js['message'])[:400]}")
                    if "intent" in js:
                        print(f"      intent: {js['intent']}")

finally:
    if KEEP_SEND_ENABLED:
        print(f"\n[cleanup] SKIP re-enable (send no se toco)")
    else:
        print(f"\n[cleanup] Re-enable send nodes ...")
        set_send_disabled(False)
    print("Done.")
