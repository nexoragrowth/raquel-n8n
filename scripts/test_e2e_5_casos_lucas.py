"""Test E2E de los 5 casos solicitados por Lucas (03/06 PM post-cagada Reconcile + cron iter).
Dispara webhooks simulando mensajes de Lucas al bot. Para cada caso:
- Dispara webhook Evolution con payload realista.
- Espera buffer 22s + procesamiento (~35s total).
- Lee la exec resultante + reporta:
  - intent clasificado por Router
  - sub-agent/sub-wf invocado
  - output final del bot (lo que se envia/envio)
  - status de cada nodo critico

Casos:
1. "hola" -> debe presentarse (regla IDENTIFICACION caso b)
2. "ok gracias" -> debe ser [NO_REPLY] descartado (no enviar)
3. "atienden por OSDE?" -> canned obra social directo
4. "quiero un turno" -> declarar grilla + primer slot
5. "👍" post-recordatorio (recordatorio mock pre-insertado) -> confirmar_post_recordatorio
"""
from __future__ import annotations
import os, sys, io, json, time, uuid
import requests
from dotenv import load_dotenv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

WEBHOOK_URL = "https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2"
PHONE = "5491161461034"
PUSH_NAME = "Lucas Test"


def make_payload(text, key_id=None):
    """Payload Evolution API minimo que el v6 acepta + source=test_e2e_suite para bypass rate limit."""
    return {
        "event": "messages.upsert",
        "instance": "raquel",
        "data": {
            "key": {
                "remoteJid": f"{PHONE}@s.whatsapp.net",
                "fromMe": False,
                "id": key_id or f"TEST{uuid.uuid4().hex[:16]}",
            },
            "pushName": PUSH_NAME,
            "message": {"conversation": text},
            "messageType": "conversation",
            "messageTimestamp": int(time.time()),
            "source": "test_e2e_suite",  # bypass rate limit
        },
    }


def wait_and_find_exec(after_ts, text_hint, timeout=60):
    """Esperar a que aparezca exec del v6 COMPLETA (buffer wait 22s + procesamiento).
    Busca la exec que tiene el texto Y que llegó al final del flow (Buffer 'Soy el ultimo?' = SI o descartada).
    """
    t0 = time.time()
    seen = {}  # exec_id -> full
    while time.time() - t0 < timeout:
        time.sleep(5)
        r = requests.get(f"{BASE}/api/v1/executions", headers=H,
                         params={"workflowId": "O155MqHgOSaNZ9ye", "limit": 20}, timeout=30)
        for e in r.json().get("data", []):
            if e.get("startedAt", "") < after_ts:
                continue
            try:
                full = requests.get(f"{BASE}/api/v1/executions/{e['id']}?includeData=true", headers=H, timeout=30).json()
                runs = full.get("data", {}).get("resultData", {}).get("runData", {})
                webhook_match = False
                for k in runs:
                    if "ebhook" in k:
                        try:
                            j = runs[k][0]["data"]["main"][0][0]["json"]
                            b = j.get("body", j); dt = b.get("data", b)
                            msg = dt.get("message", {}).get("conversation", "")
                            if text_hint in msg or msg == text_hint:
                                webhook_match = True
                                break
                        except: pass
                if not webhook_match:
                    continue
                # PREFERIR exec que llegó hasta el final (Sub-Agent ejecutado, o Evolution Send, o Descartar)
                completo = any(k in runs for k in ["Evolution API - Enviar Mensaje", "Descartar [NO_REPLY]", "Sub-Agent General", "Sub-Agent Confirmar", "Sub-Agent Agendar", "Sub-Agent Urgencia", "Execute Sub-WF Cancelar"])
                seen[e["id"]] = (full, completo)
                if completo:
                    return e["id"], full
            except: pass
    # No encontramos completo — devolver el ultimo seen (capaz fue NO el ultimo del buffer)
    if seen:
        eid = list(seen.keys())[-1]
        return eid, seen[eid][0]
    return None, None


def analyze(exec_id, full):
    runs = full.get("data", {}).get("resultData", {}).get("runData", {})
    info = {"exec_id": exec_id, "status": full.get("data", {}).get("status", "?")}
    # Intent
    try:
        info["intent"] = runs["Parse Intent"][0]["data"]["main"][0][0]["json"].get("intent", "?")
    except: info["intent"] = "?"
    # Sub-agent o sub-wf invocado
    info["sub"] = next((k for k in runs if k.startswith("Sub-Agent") and "LM" not in k and "Memory" not in k), "?")
    if info["sub"] == "?":
        if "Execute Sub-WF Cancelar" in runs:
            info["sub"] = "Execute Sub-WF Cancelar"
    # Output final enviado a Evolution
    info["enviado"] = None
    if "Evolution API - Enviar Mensaje" in runs:
        try:
            send = runs["Evolution API - Enviar Mensaje"][0].get("data", {}).get("main", [[]])[0]
            for it in send:
                txt = it.get("json", {}).get("data", {}).get("message", {}).get("conversation", "")
                if txt:
                    info["enviado"] = txt
                    break
        except: pass
    else:
        info["enviado"] = "(NO ENVIADO — exec corto, paso por descartar o label humano)"
    # Status nodos clave
    info["descartado"] = "Descartar [NO_REPLY]" in runs
    info["gate_replaced"] = False
    if "Gate Error Tecnico" in runs:
        try:
            info["gate_replaced"] = runs["Gate Error Tecnico"][0]["data"]["main"][0][0]["json"].get("_gate_replaced", False)
        except: pass
    return info


# === CASOS ===
CASES = [
    {"id": 1, "text": "hola", "esperado": "Saludo cold -> presentarse Asiri"},
    {"id": 2, "text": "ok gracias", "esperado": "[NO_REPLY] -> NO enviar (descartado)"},
    {"id": 3, "text": "atienden por OSDE?", "esperado": "Canned OS directo (no derivar)"},
    {"id": 4, "text": "quiero un turno", "esperado": "Declarar grilla + primer slot"},
    {"id": 5, "text": "👍", "esperado": "confirmar_post_recordatorio (con recordatorio mock pre-insertado)"},
]


def insert_mock_recordatorio(phone):
    """Pre-insertar un recordatorio + nota interna en memoria del phone para el caso 5."""
    v6 = requests.get(f"{BASE}/api/v1/workflows/O155MqHgOSaNZ9ye", headers=H, timeout=60).json()
    pg = next(n for n in v6["nodes"] if n["type"] == "n8n-nodes-base.postgres")
    creds = pg.get("credentials", {})
    msg_rec = json.dumps({
        "type": "ai",
        "content": "✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\nEstimado Lucas Test,\nLe recordamos su turno con la Dra. Rodríguez Raquel:\n\n📅 Viernes 5 de junio de 2026\n🕔 15:00 hs\n📍 Balcarce Nº37, 2º piso\n\nLe pedimos confirmar su asistencia respondiendo a este mensaje.",
        "tool_calls": [], "additional_kwargs": {"source": "reminder_note"},
        "response_metadata": {}, "invalid_tool_calls": []
    }, ensure_ascii=False)
    msg_int = json.dumps({
        "type": "ai",
        "content": "[NOTA INTERNA - contexto del último recordatorio enviado, NO mencionar al paciente]\nAcabo de enviar un recordatorio TEST del siguiente turno:\n- Cita Dentalink ID: TEST-LUCAS-CITA\n- ID Paciente: TEST\n- Paciente: Lucas Test\n- Fecha: viernes 5 de junio de 2026\n- Hora: 15:00\n- Profesional: Dra. Rodríguez Raquel\nSi el paciente responde sobre este turno, ya conocés todos los datos.",
        "tool_calls": [], "additional_kwargs": {"source": "reminder_note"},
        "response_metadata": {}, "invalid_tool_calls": []
    }, ensure_ascii=False)

    nodes = [
        {"name": "WH", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [200, 300],
         "parameters": {"path": "test-mock-rec", "httpMethod": "POST", "responseMode": "lastNode"}, "webhookId": "test-mock-rec"},
        {"name": "Items", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [400, 300],
         "parameters": {"jsCode": (
             "return ["
             f"{{json:{{session_id:'{phone}',message_json:{json.dumps(msg_rec)}}}}},"
             f"{{json:{{session_id:'{phone}',message_json:{json.dumps(msg_int)}}}}}"
             "];"
         )}},
        {"name": "INS", "type": "n8n-nodes-base.postgres", "typeVersion": 2.5, "position": [600, 300],
         "parameters": {"operation": "executeQuery",
                        "query": "INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb) RETURNING id",
                        "options": {"queryReplacement": "={{ $json.session_id }}, ={{ $json.message_json }}"}},
         "credentials": creds},
    ]
    conns = {"WH": {"main": [[{"node": "Items", "type": "main", "index": 0}]]},
             "Items": {"main": [[{"node": "INS", "type": "main", "index": 0}]]}}
    body = {"name": "TEST - Mock Recordatorio Lucas", "nodes": nodes, "connections": conns, "settings": {"executionOrder": "v1"}}
    existing = requests.get(f"{BASE}/api/v1/workflows", headers=H, params={"name": body["name"]}, timeout=30).json()
    test_wf = next((w for w in existing.get("data", []) if w.get("name") == body["name"]), None)
    if test_wf: wid = test_wf["id"]; requests.put(f"{BASE}/api/v1/workflows/{wid}", headers=H, json=body, timeout=40).raise_for_status()
    else: r = requests.post(f"{BASE}/api/v1/workflows", headers=H, json=body, timeout=40); wid = r.json()["id"]
    requests.post(f"{BASE}/api/v1/workflows/{wid}/activate", headers=H, timeout=30)
    requests.post(f"{BASE.replace('/api/v1','')}/webhook/test-mock-rec", json={}, timeout=30)
    time.sleep(2)
    print(f"  [pre-test] mock recordatorio insertado para {phone}")


def main():
    print(f"=== Test E2E 5 casos Lucas ({PHONE}) ===\n")
    print("ATENCION: estos disparos van a hacer que el bot RESPONDA via Evolution a tu WhatsApp.")
    print("Si tu chat tiene label humano en Chatwoot, el bot procesa pero NO envia (verificable en exec).\n")

    for i, case in enumerate(CASES):
        print(f"--- Caso {case['id']}: {case['text']!r} | esperado: {case['esperado']} ---")
        if case["id"] == 5:
            insert_mock_recordatorio(PHONE)

        before = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        payload = make_payload(case["text"])
        r = requests.post(WEBHOOK_URL, json=payload, timeout=30)
        print(f"  webhook POST: {r.status_code}")

        eid, full = wait_and_find_exec(before, case["text"], timeout=50)
        if not eid:
            print(f"  !! no encontre exec con texto {case['text']!r}\n")
            continue

        info = analyze(eid, full)
        print(f"  exec={info['exec_id']} status={info['status']} intent={info['intent']} sub={info['sub']}")
        print(f"  gate_replaced={info['gate_replaced']} descartado={info['descartado']}")
        print(f"  ENVIADO: {info['enviado']!r}\n")

        # Pausa entre casos para no bombear buffer (buffer wait = 22s, dejar margen)
        if i < len(CASES) - 1:
            print("  ... esperando 35s antes del proximo caso (buffer wait + margen) ...\n")
            time.sleep(35)


if __name__ == "__main__":
    main()
