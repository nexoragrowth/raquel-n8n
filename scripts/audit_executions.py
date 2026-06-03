"""
Analiza executions del v6 — samplea N execs, extrae intent, banlist triggers,
escalaciones, NO_REPLY, errores. Reporta distribucion.
"""
import json
import sys
import random
from pathlib import Path
from collections import Counter

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require  # noqa: E402

N8N_BASE_URL = require("N8N_BASE_URL").rstrip("/")
N8N_API_KEY = require("N8N_API_KEY")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Accept": "application/json"}

REPO = Path(__file__).resolve().parents[1]
SAMPLE_N = int(sys.argv[1]) if len(sys.argv) > 1 else 80

audits = sorted((REPO / "tests").glob("audit_executions_v6_*.json"))
META = json.loads(audits[-1].read_text(encoding="utf-8"))
execs = META["execs"]
print(f"Total exec metadata: {len(execs)}")

# Stratified sample: prioritize errors + spread time evenly + random
errors = [e for e in execs if e.get("status") in ("error", "crashed")]
ok = [e for e in execs if e.get("status") not in ("error", "crashed")]
random.seed(42)
ok_sample = random.sample(ok, min(SAMPLE_N - len(errors), len(ok)))
sample = errors + ok_sample
print(f"Sampling {len(sample)} executions ({len(errors)} errors + {len(ok_sample)} ok)\n")

stats = {
    "by_status": Counter(),
    "by_finish_node": Counter(),
    "tools_called": Counter(),
    "intents_seen": Counter(),
    "banlist_triggered": [],
    "no_reply": 0,
    "escalations": 0,
    "phones": Counter(),
    "outputs_to_evolution": 0,
    "sample_outputs": [],
}

out_md_lines = [f"# Sample exec analysis (N={SAMPLE_N})\n"]

for e in sample:
    eid = e.get("id")
    url = f"{N8N_BASE_URL}/api/v1/executions/{eid}?includeData=true"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as ex:
        out_md_lines.append(f"## exec {eid}: ERR {ex}\n")
        continue
    status = data.get("status")
    stats["by_status"][status] += 1
    rdata = data.get("data", {})
    result = rdata.get("resultData", {})
    last = result.get("lastNodeExecuted")
    stats["by_finish_node"][last or "?"] += 1
    run_data = result.get("runData", {})

    # Webhook input
    wh = run_data.get("Webhook - Evolution API", [])
    phone = ""
    text = ""
    fromMe = False
    if wh:
        try:
            body = wh[0].get("data", {}).get("main", [[{}]])[0][0].get("json", {}).get("body", {})
            k = body.get("data", {}).get("key", {})
            jid = k.get("remoteJid", "")
            phone = jid.replace("@s.whatsapp.net", "").replace("@g.us", "")
            fromMe = k.get("fromMe", False)
            msg = body.get("data", {}).get("message", {}) or {}
            text = (msg.get("conversation") or
                    (msg.get("extendedTextMessage") or {}).get("text") or
                    (msg.get("imageMessage") or {}).get("caption") or
                    "")
        except Exception:
            pass
    if phone:
        stats["phones"][phone] += 1

    # Parse intent from Router output
    router = run_data.get("Router - Clasificar Intent", [])
    intent = ""
    if router:
        try:
            out_json = router[0]["data"]["main"][0][0]["json"]
            intent = out_json.get("output", "").strip().lower()
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
        stats["intents_seen"][intent] += 1

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
                })
        except Exception:
            pass

    # NO_REPLY paths
    if last in ("Descartar [NO_REPLY]", "Set NO_REPLY", "Pre-filtro Cierre"):
        stats["no_reply"] += 1
    # escalation indicator
    if "escalar" in (last or "").lower() or "escalation" in (last or "").lower():
        stats["escalations"] += 1

    # Tools called (langchain agents log tool calls in their run output)
    for node_name, runs in run_data.items():
        if "tool" in node_name.lower() or "buscar_" in node_name or "reservar_" in node_name or "confirmar_" in node_name or "cancelar_" in node_name or "ver_turnos" in node_name or "crear_paciente" in node_name or "buscar_paciente" in node_name or "escalar_" in node_name or "obtener_historial" in node_name or "buscar_horarios" in node_name or "ver_profesionales" in node_name:
            stats["tools_called"][node_name] += len(runs)

    # Did we send to evolution?
    send = run_data.get("Evolution API - Enviar Mensaje", [])
    if send:
        stats["outputs_to_evolution"] += 1

    # Sample output for review (random 10 only, of OK ones)
    if status not in ("error", "crashed") and len(stats["sample_outputs"]) < 10:
        try:
            sm = run_data.get("Split en Mensajes", [])
            if sm:
                for ru in sm:
                    parts = ru["data"]["main"][0]
                    for p in parts:
                        stats["sample_outputs"].append({
                            "exec": eid,
                            "phone": phone[-4:] if phone else "",
                            "in": text[:120],
                            "intent": intent,
                            "out": (p["json"].get("message") or "")[:300],
                        })
        except Exception:
            pass

    # Errors
    if status in ("error", "crashed"):
        err = result.get("error") or {}
        out_md_lines.append(f"## exec {eid} [{status}]")
        out_md_lines.append(f"- last node: {last}")
        out_md_lines.append(f"- phone: {phone}  fromMe: {fromMe}")
        out_md_lines.append(f"- text: {text[:200]}")
        out_md_lines.append(f"- error msg: {err.get('message')}")
        out_md_lines.append(f"- error desc (300): {str(err.get('description') or '')[:300]}")
        out_md_lines.append("")

# Print summary
print("=== STATS ===")
print(f"By status: {dict(stats['by_status'])}")
print(f"Last node distribution (top 15):")
for n, c in stats["by_finish_node"].most_common(15):
    print(f"  {c:3d}  {n}")
print(f"\nIntents (router classification):")
for n, c in stats["intents_seen"].most_common():
    print(f"  {c:3d}  {n}")
print(f"\nTools called (top 15):")
for n, c in stats["tools_called"].most_common(15):
    print(f"  {c:3d}  {n}")
print(f"\nBanlist triggered: {len(stats['banlist_triggered'])}")
for b in stats["banlist_triggered"][:10]:
    print(f"  - exec={b['exec']} trigger='{b['trigger']}' intent={b['intent']}")
    print(f"    original: {b['original'][:200]}")
print(f"\nNO_REPLY (last node was descartar/set NO_REPLY/pre-filtro cierre): {stats['no_reply']}")
print(f"Escalations (last node mentions escalar): {stats['escalations']}")
print(f"Sends to evolution: {stats['outputs_to_evolution']}")
print(f"\nTop phones (n={SAMPLE_N}):")
for p, c in stats["phones"].most_common(10):
    print(f"  {c:3d}  {p}")

# Save full FIRST (avoid stdout encoding crash losing data)
out_path = REPO / "tests" / f"audit_exec_sample_{audits[-1].stem.split('_')[-2]}_{audits[-1].stem.split('_')[-1]}.json"
out_path.write_text(json.dumps({
    "n": len(sample),
    "stats": {
        "by_status": dict(stats["by_status"]),
        "by_finish_node": dict(stats["by_finish_node"]),
        "tools_called": dict(stats["tools_called"]),
        "intents_seen": dict(stats["intents_seen"]),
        "banlist_triggered": stats["banlist_triggered"],
        "no_reply": stats["no_reply"],
        "escalations": stats["escalations"],
        "outputs_to_evolution": stats["outputs_to_evolution"],
        "phones": dict(stats["phones"]),
        "sample_outputs": stats["sample_outputs"],
    }
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nSaved -> {out_path.relative_to(REPO)}")

# Now safe to print samples (ascii-safe)
try:
    print("\n--- Sample OK outputs (random 10) ---")
    for s in stats["sample_outputs"][:10]:
        safe_in = s['in'].encode('ascii', 'replace').decode('ascii')
        safe_out = s['out'].encode('ascii', 'replace').decode('ascii')
        print(f"  exec={s['exec']} ph=...{s['phone']} intent={s['intent']}")
        print(f"    IN : {safe_in}")
        print(f"    OUT: {safe_out}")
except Exception as e:
    print(f"(print sample failed: {e}; data is in JSON above)")
