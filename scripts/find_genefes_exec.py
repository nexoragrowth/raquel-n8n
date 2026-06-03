"""
Busca la exec de hoy donde el paciente respondio 'Confirmados' al recordatorio
del chat Manuel/Guillermina Genefes y el bot escalo en vez de confirmar.

Lista todas las execs de hoy con input que contenga 'confirmad' (case insensitive)
y muestra el reasoning completo del Sub-Agent Confirmar.
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N_BASE_URL = require("N8N_BASE_URL").rstrip("/")
N8N_API_KEY = require("N8N_API_KEY")
WF_V6 = require("N8N_WORKFLOW_V6_ID")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Accept": "application/json"}

ARG = timezone(timedelta(hours=-3))
now_arg = datetime.now(ARG)
start_arg = now_arg.replace(hour=0, minute=0, second=0, microsecond=0)
start_utc = start_arg.astimezone(timezone.utc)

# Pull todas las execs de hoy
def fetch_today():
    url = f"{N8N_BASE_URL}/api/v1/executions"
    out = []
    cursor = None
    while True:
        p = {"workflowId": WF_V6, "limit": 250, "includeData": "false"}
        if cursor: p["cursor"] = cursor
        r = requests.get(url, headers=HEADERS, params=p, timeout=30)
        r.raise_for_status()
        j = r.json()
        items = j.get("data", [])
        out.extend(items)
        cursor = j.get("nextCursor")
        if items:
            last_st = items[-1].get("startedAt") or items[-1].get("stoppedAt")
            if last_st:
                ts = datetime.fromisoformat(last_st.replace("Z", "+00:00"))
                if ts < start_utc:
                    break
        if not cursor:
            break
    today = []
    for e in out:
        st = e.get("startedAt") or e.get("stoppedAt")
        if st:
            ts = datetime.fromisoformat(st.replace("Z", "+00:00"))
            if ts >= start_utc:
                today.append(e)
    return today

print("Fetching execs de hoy...")
execs = fetch_today()
print(f"  total hoy: {len(execs)}")

def detail(eid):
    return requests.get(f"{N8N_BASE_URL}/api/v1/executions/{eid}?includeData=true",
                        headers=HEADERS, timeout=30).json()

print("\nBuscando execs con 'confirmad' en input...\n")
matches = []
for e in execs:
    eid = e["id"]
    try:
        d = detail(eid)
    except Exception as ex:
        continue
    rd = d.get("data", {}).get("resultData", {}).get("runData", {})
    wh = rd.get("Webhook - Evolution API", [])
    if not wh: continue
    try:
        body = wh[0]["data"]["main"][0][0]["json"]["body"]
        k = body["data"]["key"]
        jid = k.get("remoteJid", "")
        phone = jid.replace("@s.whatsapp.net", "").replace("@g.us", "")
        fromMe = k.get("fromMe", False)
        msg = body["data"].get("message", {}) or {}
        text = (msg.get("conversation") or
                (msg.get("extendedTextMessage") or {}).get("text") or "")
    except Exception:
        continue
    if not text: continue
    if "confirmad" not in text.lower(): continue
    if fromMe: continue  # solo input del paciente
    ts = e.get("startedAt", "")
    matches.append({
        "exec": eid, "phone": phone, "text": text, "ts": ts,
        "last": d.get("data", {}).get("resultData", {}).get("lastNodeExecuted", "?"),
        "runData": rd,
    })

print(f"Encontradas: {len(matches)}\n")
for m in matches:
    print(f"=== exec {m['exec']} | phone={m['phone']} | {m['ts']} | last={m['last']} ===")
    print(f"IN: {m['text'][:200].encode('ascii','replace').decode('ascii')}")
    rd = m["runData"]

    # Router output
    r_router = rd.get("Router - Clasificar Intent", [])
    if r_router:
        try:
            out_r = r_router[0]["data"]["main"][0][0]["json"]
            print(f"  Router intent: {out_r.get('output', '')[:200]}")
        except Exception:
            pass

    # Sub-Agent Confirmar reasoning
    for sub_name in ["Sub-Agent Confirmar", "Sub Agent Confirmar", "SubAgent Confirmar",
                     "Agent Confirmar", "Sub-Agent: Confirmar Turno"]:
        if sub_name in rd:
            print(f"\n  >>> {sub_name} runs: {len(rd[sub_name])}")
            for i, run in enumerate(rd[sub_name]):
                try:
                    out_data = run["data"]["main"][0][0]["json"]
                    print(f"  run {i}: output keys={list(out_data.keys())[:8]}")
                    if "output" in out_data:
                        print(f"    output: {str(out_data['output'])[:500]}")
                    if "intermediateSteps" in out_data:
                        steps = out_data["intermediateSteps"]
                        print(f"    intermediateSteps: {len(steps)}")
                        for s in steps[:5]:
                            try:
                                action = s.get("action", {})
                                tool = action.get("tool", "?")
                                tool_input = action.get("toolInput", "")
                                obs = s.get("observation", "")
                                print(f"      - tool={tool} input={str(tool_input)[:200]}")
                                print(f"        obs={str(obs)[:200]}")
                            except Exception:
                                pass
                except Exception as ex:
                    print(f"    err: {ex}")

    # Tools called
    tools_in_rd = [k for k in rd.keys() if any(x in k.lower() for x in
                   ["confirmar_turno", "ver_turnos", "buscar_paciente", "escalar"])]
    if tools_in_rd:
        print(f"\n  Tools en runData: {tools_in_rd}")
        for tn in tools_in_rd:
            print(f"    -- {tn} ({len(rd[tn])} runs) --")
            for run in rd[tn]:
                try:
                    inp = run.get("data", {}).get("main", [[{}]])[0][0].get("json", {})
                    print(f"      in/out: {json.dumps(inp, ensure_ascii=False)[:400]}")
                except Exception:
                    pass

    # Output final
    sm = rd.get("Split en Mensajes", [])
    if sm:
        try:
            for ru in sm:
                for p in ru["data"]["main"][0]:
                    print(f"\n  OUT FINAL: {(p['json'].get('message') or '')[:300]}")
        except Exception:
            pass
    print()
