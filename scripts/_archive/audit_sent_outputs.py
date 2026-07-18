"""
Filtra TODAS las executions del v6 (last 48h) que efectivamente
enviaron un mensaje al paciente (Evolution Send) y muestra IN/OUT.
"""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require  # noqa: E402

N8N_BASE_URL = require("N8N_BASE_URL").rstrip("/")
N8N_API_KEY = require("N8N_API_KEY")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Accept": "application/json"}

REPO = Path(__file__).resolve().parents[1]
audits = sorted((REPO / "tests").glob("audit_executions_v6_*.json"))
execs = json.loads(audits[-1].read_text(encoding="utf-8"))["execs"]
print(f"Scanning {len(execs)} execs for actual sends...\n")

# We need to fetch each to know if Send ran. Could be slow but bounded (500).
# Strategy: fetch each, check runData. Trim to those that hit Send.
results = []
checked = 0
for e in execs:
    eid = e.get("id")
    checked += 1
    if checked % 50 == 0:
        print(f"  ...checked {checked}/{len(execs)}, found {len(results)} sends so far")
    url = f"{N8N_BASE_URL}/api/v1/executions/{eid}?includeData=true"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception:
        continue
    rdata = data.get("data", {})
    result = rdata.get("resultData", {})
    run_data = result.get("runData", {})
    last = result.get("lastNodeExecuted")

    send = run_data.get("Evolution API - Enviar Mensaje")
    if not send:
        continue

    # Get input
    wh = run_data.get("Webhook - Evolution API", [])
    phone = ""
    text = ""
    if wh:
        try:
            body = wh[0]["data"]["main"][0][0]["json"]["body"]
            k = body.get("data", {}).get("key", {})
            phone = k.get("remoteJid", "").replace("@s.whatsapp.net", "")
            msg = body.get("data", {}).get("message", {}) or {}
            text = (msg.get("conversation") or
                    (msg.get("extendedTextMessage") or {}).get("text") or
                    (msg.get("imageMessage") or {}).get("caption") or "")
        except Exception:
            pass

    # Output(s)
    outs = []
    sm = run_data.get("Split en Mensajes", [])
    if sm:
        try:
            for parts in sm[0]["data"]["main"][0]:
                outs.append(parts["json"].get("message", ""))
        except Exception:
            pass
    if not outs:
        # Maybe single message direct from output field
        try:
            outs.append(send[0]["data"]["main"][0][0].get("json", {}).get("output", ""))
        except Exception:
            pass

    # Intent
    intent = ""
    parse = run_data.get("Parse Intent", [])
    if parse:
        try:
            intent = parse[0]["data"]["main"][0][0]["json"].get("intent", "")
        except Exception:
            pass

    # Tools called
    tools_called = []
    for nn in run_data:
        if any(tn in nn for tn in ("buscar_paciente_dentalink", "crear_paciente_dentalink",
                                   "ver_turnos_paciente", "buscar_horarios", "reservar_turno",
                                   "confirmar_turno", "cancelar_turno", "ver_profesionales",
                                   "escalar_a_secretaria", "obtener_historial_paciente",
                                   "buscar_conocimiento")):
            tools_called.append(nn)

    # Banlist
    banlist = ""
    bl = run_data.get("Banlist Validator", [])
    if bl:
        try:
            bj = bl[0]["data"]["main"][0][0]["json"]
            banlist = bj.get("banlist_triggered") or ""
        except Exception:
            pass

    results.append({
        "id": eid,
        "started": data.get("startedAt"),
        "status": data.get("status"),
        "phone": phone,
        "intent": intent,
        "text_in": text,
        "outs": outs,
        "tools": tools_called,
        "banlist": banlist,
        "last": last,
    })

print(f"\nTotal execs that sent a message: {len(results)}\n")

out_path = REPO / "tests" / f"audit_sent_outputs_{audits[-1].stem.split('_')[-2]}_{audits[-1].stem.split('_')[-1]}.json"
out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Saved -> {out_path.relative_to(REPO)}")

# Markdown report
md = [f"# Sent messages last 48h (n={len(results)})\n"]
md.append("|  # | phone | intent | tools | banlist | IN | OUT |")
md.append("|----|-------|--------|-------|---------|----|-----|")
for i, r in enumerate(results, 1):
    out_str = " || ".join((o or "")[:200].replace("\n", " ") for o in r["outs"])
    md.append(
        f"| {i} | ...{(r['phone'] or '')[-6:]} | {r['intent'] or '-'} | "
        f"{','.join(set(r['tools'])) or '-'} | {r['banlist'] or '-'} | "
        f"{(r['text_in'] or '')[:120].replace(chr(10),' ')} | "
        f"{out_str} |"
    )
md_path = REPO / "tests" / f"audit_sent_outputs_{audits[-1].stem.split('_')[-2]}_{audits[-1].stem.split('_')[-1]}.md"
md_path.write_text("\n".join(md), encoding="utf-8")
print(f"Saved md -> {md_path.relative_to(REPO)}")
