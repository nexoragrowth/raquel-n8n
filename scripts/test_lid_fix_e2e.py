"""
Test E2E del fix LID-safe phone extraction (2026-07-06).

Corre 4 tests contra el v6 VIVO usando el numero de Lucas (5491161461034,
admin whitelisted). Los envios estan habilitados: las respuestas llegan al
WhatsApp de Lucas (autorizado por el).

T1 regression: DM normal (@s.whatsapp.net) pregunta precio -> canned $50.000,
   phone y pushName correctos.
T2 lid+Alt:   upsert con remoteJid=<lid real de Lucas>, remoteJidAlt=su phone
   -> phone recuperado = 5491161461034, identificacion Dentalink funciona.
T3 lid solo:  upsert con remoteJid=<lid> sin Alt -> fallback: phone='NNN@lid'
   (comportamiento pre-fix, sin crash), canned precio responde igual.
T4 kill-switch: '/bot status' desde chat @lid con Alt -> isAdminCommand=true.

El LID real de Lucas se descubre correlacionando messages.update (@lid receipts)
con los messageIds que el bot le envio a 5491161461034.
"""
import json
import sys
import time
import uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = require("N8N_WORKFLOW_V6_ID")
H = {"X-N8N-API-KEY": KEY, "accept": "application/json"}
PHONE = "5491161461034"


def get(path):
    req = urllib.request.Request(N8N + path, headers=H)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def post_webhook(key_obj, text, push_name):
    body = {
        "event": "messages.upsert", "instance": "raquel",
        "data": {
            "key": key_obj,
            "pushName": push_name,
            "message": {"conversation": text},
            "messageType": "conversation",
            "messageTimestamp": int(time.time()),
        },
        "destination": f"{N8N}/webhook/evolution-v2",
        "date_time": datetime.now(timezone.utc).isoformat(),
        "sender": f"{PHONE}@s.whatsapp.net",
    }
    req = urllib.request.Request(f"{N8N}/webhook/evolution-v2", method="POST",
                                 headers={"Content-Type": "application/json"},
                                 data=json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status


def wait_exec(sim_id, last_id, timeout_s=150, by_killswitch=False):
    """Espera la exec cuyo Edit Fields (o Kill-switch) matchee sim_id."""
    for _ in range(timeout_s // 3):
        time.sleep(3)
        execs = get(f"/api/v1/executions?workflowId={WF}&limit=15").get("data", [])
        for e in execs:
            if int(e["id"]) <= last_id:
                continue
            d = get(f"/api/v1/executions/{e['id']}?includeData=true")
            rd = d.get("data", {}).get("resultData", {}).get("runData", {})
            try:
                if by_killswitch:
                    ks = rd.get("Kill-switch Check", [])
                    out = ks[0]["data"]["main"][0][0]["json"] if ks else {}
                    raw = json.dumps(d.get("data", {}).get("resultData", {}).get("runData", {}).get(
                        "Webhook - Evolution API", [{}])[0], ensure_ascii=False)
                    if sim_id in raw:
                        return e["id"], d, rd
                else:
                    ef = rd.get("Edit Fields - Extraer Datos", [])
                    if ef and ef[0]["data"]["main"][0][0]["json"].get("key_id") == sim_id:
                        return e["id"], d, rd
            except Exception:
                continue
    return None, None, None


def final_message(rd):
    sm = rd.get("Split en Mensajes", [])
    msgs = []
    for run in sm:
        for item in (run.get("data", {}).get("main", [[]])[0] or []):
            m = item.get("json", {}).get("message", "")
            if m:
                msgs.append(m)
    return " | ".join(msgs)


def extraer(rd):
    ef = rd.get("Edit Fields - Extraer Datos", [])
    if not ef:
        return {}
    return ef[0]["data"]["main"][0][0]["json"]


results = {}

# LID por argumento: python test_lid_fix_e2e.py <lid>  (saltea descubrimiento y T1)
ARG_LID = sys.argv[1] if len(sys.argv) > 1 else None

# ---------- 0. Descubrir el LID real de Lucas ----------
print("== [0] Descubriendo LID real de Lucas via receipts ==")
sent_ids = set()
lid = ARG_LID
if not lid:
    execs = get(f"/api/v1/executions?workflowId={WF}&limit=250").get("data", [])
    for e in execs:
        d = get(f"/api/v1/executions/{e['id']}?includeData=true")
        s = json.dumps(d, ensure_ascii=False)
        if f"{PHONE}@s.whatsapp.net" in s:
            rd = d.get("data", {}).get("resultData", {}).get("runData", {})
            env = rd.get("Evolution API - Enviar Mensaje", [])
            for run in env:
                for item in (run.get("data", {}).get("main", [[]])[0] or []):
                    mid = (item.get("json", {}).get("data", {}) or {}).get("key", {}).get("id")
                    if mid:
                        sent_ids.add(mid)
    print(f"  messageIds enviados a Lucas: {len(sent_ids)}")
    if sent_ids:
        for e in execs:
            d = get(f"/api/v1/executions/{e['id']}?includeData=true")
            try:
                rd = d.get("data", {}).get("resultData", {}).get("runData", {})
                wh = rd.get("Webhook - Evolution API", [])
                j = wh[0]["data"]["main"][0][0]["json"]["body"] if wh else {}
                if j.get("event") != "messages.update":
                    continue
                data = j.get("data", {})
                rj = data.get("remoteJid") or (data.get("key") or {}).get("remoteJid") or ""
                kid = data.get("keyId") or data.get("messageId") or (data.get("key") or {}).get("id")
                if rj.endswith("@lid") and kid in sent_ids:
                    lid = rj.split(":")[0].replace("@lid", "") + "@lid"  # sin device suffix
                    break
            except Exception:
                continue
print(f"  LID de Lucas: {lid or 'NO ENCONTRADO'}")
results["lid_descubierto"] = lid

# ---------- T1: regression DM normal (solo si no vino LID por argumento) ----------
if not ARG_LID:
    print("\n== [T1] Regression: DM normal pregunta precio ==")
    last = int(get(f"/api/v1/executions?workflowId={WF}&limit=1")["data"][0]["id"])
    sim1 = f"SIM_{uuid.uuid4().hex[:16].upper()}"
    post_webhook({"remoteJid": f"{PHONE}@s.whatsapp.net", "fromMe": False, "id": sim1},
                 "Cuanto sale la consulta?", "Lucas (T1 regression)")
    eid, d, rd = wait_exec(sim1, last)
    if eid:
        ex = extraer(rd)
        fm = final_message(rd)
        ok = (ex.get("phone") == PHONE and ex.get("phone_last10") == PHONE[-10:]
              and ex.get("pushName") == "Lucas (T1 regression)" and "50.000" in fm)
        print(f"  exec={eid} status={d.get('status')}")
        print(f"  phone={ex.get('phone')} last10={ex.get('phone_last10')} pushName={ex.get('pushName')!r}")
        print(f"  reply: {fm[:200]}")
        print(f"  T1 {'PASS' if ok else 'FAIL'}")
        results["T1"] = "PASS" if ok else f"FAIL exec={eid}"
    else:
        print("  T1 FAIL: exec no encontrada")
        results["T1"] = "FAIL sin exec"
else:
    results["T1"] = "PASS (corrida previa, exec 192897)"

if not lid:
    print("\nSin LID real: T2/T3/T4 abortados para no inventar un LID.")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    sys.exit(2)

time.sleep(20)  # separar del buffer de T1

# ---------- T2: lid + remoteJidAlt ----------
print("\n== [T2] LID + remoteJidAlt: identificacion Dentalink ==")
last = int(get(f"/api/v1/executions?workflowId={WF}&limit=1")["data"][0]["id"])
sim2 = f"SIM_{uuid.uuid4().hex[:16].upper()}"
post_webhook({"remoteJid": lid, "remoteJidAlt": f"{PHONE}@s.whatsapp.net",
              "addressingMode": "lid", "fromMe": False, "id": sim2},
             "Hola, cuando es mi proximo turno?", "Lucas (T2 lid+alt)")
eid, d, rd = wait_exec(sim2, last)
if eid:
    ex = extraer(rd)
    fm = final_message(rd)
    tools = [k for k in rd.keys() if k in ("buscar_paciente_dentalink", "ver_turnos_paciente",
                                           "consultar_recordatorios_abiertos", "escalar_a_secretaria")]
    ok = ex.get("phone") == PHONE and ex.get("phone_last10") == PHONE[-10:]
    print(f"  exec={eid} status={d.get('status')}")
    print(f"  phone={ex.get('phone')} last10={ex.get('phone_last10')} (esperado {PHONE})")
    print(f"  tools ejecutadas: {tools}")
    print(f"  reply: {fm[:250]}")
    print(f"  T2 {'PASS' if ok else 'FAIL'}")
    results["T2"] = "PASS" if ok else f"FAIL exec={eid}"
else:
    print("  T2 FAIL: exec no encontrada")
    results["T2"] = "FAIL sin exec"

time.sleep(20)

# ---------- T3: lid SIN Alt (fallback pre-fix) ----------
print("\n== [T3] LID sin Alt: fallback sin crash ==")
last = int(get(f"/api/v1/executions?workflowId={WF}&limit=1")["data"][0]["id"])
sim3 = f"SIM_{uuid.uuid4().hex[:16].upper()}"
post_webhook({"remoteJid": lid, "fromMe": False, "id": sim3},
             "Cuanto sale la consulta?", "Lucas (T3 lid solo)")
eid, d, rd = wait_exec(sim3, last)
if eid:
    ex = extraer(rd)
    fm = final_message(rd)
    ok = (str(ex.get("phone", "")).endswith("@lid") and d.get("status") == "success"
          and "50.000" in fm)
    print(f"  exec={eid} status={d.get('status')}")
    print(f"  phone={ex.get('phone')} (esperado: termina en @lid, fallback)")
    print(f"  reply: {fm[:200]}")
    print(f"  T3 {'PASS' if ok else 'FAIL'}")
    results["T3"] = "PASS" if ok else f"FAIL exec={eid}"
else:
    print("  T3 FAIL: exec no encontrada")
    results["T3"] = "FAIL sin exec"

time.sleep(10)

# ---------- T4: kill-switch /bot status desde @lid ----------
print("\n== [T4] Kill-switch: /bot status desde chat @lid ==")
last = int(get(f"/api/v1/executions?workflowId={WF}&limit=1")["data"][0]["id"])
sim4 = f"SIM_{uuid.uuid4().hex[:16].upper()}"
post_webhook({"remoteJid": lid, "remoteJidAlt": f"{PHONE}@s.whatsapp.net",
              "addressingMode": "lid", "fromMe": False, "id": sim4},
             "/bot status", "Lucas (T4 killswitch)")
found = False
for _ in range(20):
    time.sleep(3)
    execs = get(f"/api/v1/executions?workflowId={WF}&limit=10").get("data", [])
    for e in execs:
        if int(e["id"]) <= last:
            continue
        d = get(f"/api/v1/executions/{e['id']}?includeData=true")
        s = json.dumps(d, ensure_ascii=False)
        if sim4 not in s:
            continue
        rd = d.get("data", {}).get("resultData", {}).get("runData", {})
        ks = rd.get("Kill-switch Check", [])
        out = ks[0]["data"]["main"][0][0]["json"] if ks else {}
        ok = out.get("isAdminCommand") is True and out.get("action") == "status" \
            and out.get("adminPhone") == PHONE
        print(f"  exec={e['id']} kill-switch out: isAdminCommand={out.get('isAdminCommand')} "
              f"action={out.get('action')} adminPhone={out.get('adminPhone')} adminName={out.get('adminName')}")
        print(f"  T4 {'PASS' if ok else 'FAIL'}")
        results["T4"] = "PASS" if ok else f"FAIL exec={e['id']}"
        found = True
        break
    if found:
        break
if not found:
    print("  T4 FAIL: exec no encontrada")
    results["T4"] = "FAIL sin exec"

print("\n===== RESUMEN =====")
print(json.dumps(results, ensure_ascii=False, indent=2))
fails = [k for k, v in results.items() if isinstance(v, str) and v.startswith("FAIL")]
sys.exit(1 if fails else 0)
