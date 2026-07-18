"""
Audit ejecuciones del v6 de HOY (fecha local Argentina), excluyendo admin phones
(Lucas, Iri, Dra) para enfocarse solo en pacientes reales.

Reporta: distribucion por status, ultimo nodo, intent, banlist triggers,
escalaciones, errores, y detecta hardcodes problematicos en outputs.
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require  # noqa: E402

N8N_BASE_URL = require("N8N_BASE_URL").rstrip("/")
N8N_API_KEY = require("N8N_API_KEY")
WF_V6 = require("N8N_WORKFLOW_V6_ID")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Accept": "application/json"}

ADMIN_PHONES = {
    "5491161461034",   # Lucas
    "5493885786946",   # Irina
    "5493513976787",   # Dra Raquel
}

# Hardcodes a buscar en outputs (cosas que NO deberian aparecer)
HARDCODE_PATTERNS = [
    ("ip_vieja_escalar", "187.127.0.110"),
    ("ip_vieja_b", "65302"),
    ("phone_carmen_leak", "5493886869400"),
    ("nombre_carmen_leak", "Carmen Agostini"),
    ("venite_legacy", "venite"),
    ("esperamos_legacy", "los esperamos"),
    ("ahora_mismo_legacy", "ahora mismo"),
]

# Ventana: hoy en Argentina (UTC-3)
ARG = timezone(timedelta(hours=-3))
now_arg = datetime.now(ARG)
start_arg = now_arg.replace(hour=0, minute=0, second=0, microsecond=0)
start_utc = start_arg.astimezone(timezone.utc)
print(f"Ventana: desde {start_arg.isoformat()} (ARG) -> {now_arg.isoformat()} (ARG)")
print(f"         desde {start_utc.isoformat()} (UTC)")

# Pull ejecuciones del workflow v6 (paginado)
def fetch_executions():
    url = f"{N8N_BASE_URL}/api/v1/executions"
    params = {"workflowId": WF_V6, "limit": 250, "includeData": "false"}
    out = []
    cursor = None
    while True:
        p = dict(params)
        if cursor:
            p["cursor"] = cursor
        r = requests.get(url, headers=HEADERS, params=p, timeout=30)
        r.raise_for_status()
        j = r.json()
        items = j.get("data", [])
        out.extend(items)
        cursor = j.get("nextCursor")
        # Parar si la mas vieja ya es de antes de hoy
        if items:
            last_started = items[-1].get("startedAt") or items[-1].get("stoppedAt")
            if last_started:
                try:
                    ts = datetime.fromisoformat(last_started.replace("Z", "+00:00"))
                    if ts < start_utc:
                        break
                except Exception:
                    pass
        if not cursor:
            break
    return out

print("Fetching executions...")
all_execs = fetch_executions()
print(f"  total fetched: {len(all_execs)}")

# Filtrar por fecha hoy
today_execs = []
for e in all_execs:
    st = e.get("startedAt") or e.get("stoppedAt")
    if not st:
        continue
    try:
        ts = datetime.fromisoformat(st.replace("Z", "+00:00"))
        if ts >= start_utc:
            today_execs.append(e)
    except Exception:
        pass
print(f"  hoy: {len(today_execs)}")

if not today_execs:
    print("Sin ejecuciones hoy. Fin.")
    sys.exit(0)

# Para cada exec, traer detalle (includeData=true) y clasificar
def fetch_detail(eid):
    url = f"{N8N_BASE_URL}/api/v1/executions/{eid}?includeData=true"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

stats = {
    "total_today": len(today_execs),
    "real_clients": 0,
    "admin_or_group": 0,
    "no_phone": 0,
    "by_status": Counter(),
    "by_finish_node": Counter(),
    "intents": Counter(),
    "tools_called": Counter(),
    "banlist_triggered": [],
    "no_reply": 0,
    "escalations": 0,
    "outputs_to_evolution": 0,
    "errors": [],
    "hardcode_hits": [],
    "real_phones": Counter(),
    "real_outputs_sample": [],
}

processed = 0
for e in today_execs:
    eid = e.get("id")
    try:
        data = fetch_detail(eid)
    except Exception as ex:
        print(f"  ! exec {eid}: error fetch detail {ex}")
        continue
    processed += 1
    status = data.get("status")
    rdata = data.get("data", {})
    result = rdata.get("resultData", {})
    last = result.get("lastNodeExecuted") or "?"
    run_data = result.get("runData", {})

    # Extract webhook input
    wh = run_data.get("Webhook - Evolution API", [])
    phone = ""
    text = ""
    fromMe = False
    is_group = False
    if wh:
        try:
            body = wh[0].get("data", {}).get("main", [[{}]])[0][0].get("json", {}).get("body", {})
            k = body.get("data", {}).get("key", {})
            jid = k.get("remoteJid", "")
            is_group = "@g.us" in jid
            phone = jid.replace("@s.whatsapp.net", "").replace("@g.us", "")
            fromMe = k.get("fromMe", False)
            msg = body.get("data", {}).get("message", {}) or {}
            text = (msg.get("conversation") or
                    (msg.get("extendedTextMessage") or {}).get("text") or
                    (msg.get("imageMessage") or {}).get("caption") or
                    "")
        except Exception:
            pass

    # Clasificar: admin/grupo/sin phone/real
    if not phone:
        stats["no_phone"] += 1
        continue
    if is_group or phone in ADMIN_PHONES:
        stats["admin_or_group"] += 1
        continue
    # Es cliente real
    stats["real_clients"] += 1
    stats["by_status"][status] += 1
    stats["by_finish_node"][last] += 1
    stats["real_phones"][phone] += 1

    # Intent
    intent = ""
    router = run_data.get("Router - Clasificar Intent", [])
    if router:
        try:
            intent = router[0]["data"]["main"][0][0]["json"].get("output", "").strip().lower()
        except Exception:
            pass
    if not intent:
        parse = run_data.get("Parse Intent", [])
        if parse:
            try:
                intent = parse[0]["data"]["main"][0][0]["json"].get("intent", "")
            except Exception:
                pass
    if intent:
        stats["intents"][intent] += 1

    # Banlist
    banlist = run_data.get("Banlist Validator", [])
    if banlist:
        try:
            bj = banlist[0]["data"]["main"][0][0]["json"]
            if bj.get("banlist_triggered"):
                stats["banlist_triggered"].append({
                    "exec": eid,
                    "trigger": bj["banlist_triggered"],
                    "original": (bj.get("banlist_original_output") or "")[:300],
                    "intent": intent,
                    "phone_tail": phone[-4:],
                })
        except Exception:
            pass

    if "no_reply" in (last or "").lower() or "descartar" in (last or "").lower() or "pre-filtro" in (last or "").lower():
        stats["no_reply"] += 1
    if "escalar" in (last or "").lower():
        stats["escalations"] += 1

    # Tools called
    for node_name, runs in run_data.items():
        lname = node_name.lower()
        if any(k in lname for k in ["tool", "buscar_", "reservar_", "confirmar_", "cancelar_",
                                     "ver_turnos", "crear_paciente", "buscar_paciente",
                                     "escalar_", "obtener_historial", "buscar_horarios",
                                     "ver_profesionales"]):
            stats["tools_called"][node_name] += len(runs)

    # Send to evolution
    send = run_data.get("Evolution API - Enviar Mensaje", [])
    output_text = ""
    if send:
        stats["outputs_to_evolution"] += 1

    # Capturar outputs (Split en Mensajes) y buscar hardcodes
    sm = run_data.get("Split en Mensajes", [])
    if sm:
        try:
            for ru in sm:
                parts = ru["data"]["main"][0]
                for p in parts:
                    msg_out = p["json"].get("message") or ""
                    output_text += " || " + msg_out
                    # Hardcode scan
                    for name, pat in HARDCODE_PATTERNS:
                        if pat.lower() in msg_out.lower():
                            stats["hardcode_hits"].append({
                                "exec": eid,
                                "pattern": name,
                                "match": pat,
                                "context": msg_out[:200],
                                "phone_tail": phone[-4:],
                                "intent": intent,
                            })
        except Exception:
            pass

    # Sample (10 reales)
    if status not in ("error", "crashed") and len(stats["real_outputs_sample"]) < 12:
        stats["real_outputs_sample"].append({
            "exec": eid,
            "phone_tail": phone[-4:],
            "in": text[:140],
            "intent": intent,
            "last": last,
            "out": output_text[:300] if output_text else "(sin output)",
        })

    # Errores
    if status in ("error", "crashed"):
        err = result.get("error") or {}
        stats["errors"].append({
            "exec": eid,
            "last": last,
            "phone_tail": phone[-4:],
            "text": text[:120],
            "intent": intent,
            "err_msg": (err.get("message") or "")[:200],
            "err_node": (err.get("node") or {}).get("name") if isinstance(err.get("node"), dict) else "",
        })

# Save raw JSON + print resumen
out_path = Path(__file__).resolve().parents[1] / "tests" / f"audit_today_{now_arg.strftime('%Y%m%d')}.json"
out_path.parent.mkdir(exist_ok=True)
out_path.write_text(json.dumps({
    "generated_at": now_arg.isoformat(),
    "stats": {k: (dict(v) if isinstance(v, Counter) else v) for k, v in stats.items()},
}, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"\n=== RESUMEN HOY {now_arg.strftime('%Y-%m-%d')} (ARG) ===")
print(f"Total execs hoy: {stats['total_today']}")
print(f"  - clientes reales: {stats['real_clients']}")
print(f"  - admin/grupo:     {stats['admin_or_group']}")
print(f"  - sin phone:       {stats['no_phone']}")
print()
print(f"Status (solo reales):")
for s, c in stats["by_status"].most_common():
    print(f"  {c:3d}  {s}")
print()
print(f"Intents (solo reales):")
for i, c in stats["intents"].most_common():
    print(f"  {c:3d}  {i}")
print()
print(f"Ultimo nodo (top 12, solo reales):")
for n, c in stats["by_finish_node"].most_common(12):
    print(f"  {c:3d}  {n}")
print()
print(f"Tools llamadas (top 15):")
for n, c in stats["tools_called"].most_common(15):
    print(f"  {c:3d}  {n}")
print()
print(f"NO_REPLY: {stats['no_reply']}  |  Escalaciones: {stats['escalations']}  |  Sends a Evolution: {stats['outputs_to_evolution']}")
print()
print(f"Banlist triggered: {len(stats['banlist_triggered'])}")
for b in stats["banlist_triggered"][:10]:
    print(f"  - exec={b['exec']} ph=...{b['phone_tail']} trigger='{b['trigger']}' intent={b['intent']}")
    print(f"    original: {b['original'][:160]}")
print()
print(f"=== HARDCODES DETECTADOS: {len(stats['hardcode_hits'])} ===")
if not stats["hardcode_hits"]:
    print("  (ninguno — limpio)")
for h in stats["hardcode_hits"][:20]:
    print(f"  - exec={h['exec']} ph=...{h['phone_tail']} pattern={h['pattern']} match='{h['match']}'")
    print(f"    ctx: {h['context'][:160]}")
print()
print(f"Errores: {len(stats['errors'])}")
for e in stats["errors"][:10]:
    print(f"  - exec={e['exec']} last={e['last']} ph=...{e['phone_tail']}")
    print(f"    in: {e['text']}")
    print(f"    err@{e['err_node']}: {e['err_msg']}")
print()
print(f"Top phones reales:")
for p, c in stats["real_phones"].most_common(15):
    print(f"  {c:3d}  ...{p[-6:]}")
print()
print(f"--- Sample outputs reales (max 12) ---")
for s in stats["real_outputs_sample"]:
    safe_in = s['in'].encode('ascii', 'replace').decode('ascii')
    safe_out = s['out'].encode('ascii', 'replace').decode('ascii')
    print(f"  exec={s['exec']} ph=...{s['phone_tail']} intent={s['intent']} last={s['last']}")
    print(f"    IN : {safe_in}")
    print(f"    OUT: {safe_out}")
print()
print(f"Saved -> {out_path.relative_to(Path(__file__).resolve().parents[1])}")
