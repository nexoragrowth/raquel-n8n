"""
Chequea ejecuciones de los ultimos 3 dias en:
- v6 (mensajes clientes)
- Recordatorios cron (7RqTApkvVavRmq3R)
- Resumen clinico cron (BO1cdE8xmqln4IeO)

Para entender que paso post-fixes (Round 6/7/8 = 22/5 noche).
"""
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter, defaultdict

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require, env  # noqa: E402

N8N_BASE_URL = require("N8N_BASE_URL").rstrip("/")
N8N_API_KEY = require("N8N_API_KEY")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Accept": "application/json"}

WORKFLOWS = {
    "v6 (mensajes)": require("N8N_WORKFLOW_V6_ID"),
    "Recordatorios": env("N8N_WORKFLOW_RECORDATORIOS_ID", "7RqTApkvVavRmq3R"),
    "Resumen clinico": "BO1cdE8xmqln4IeO",
    "Notify Grupo": "S5U6tSipzlgFHCkf",
}

ADMIN_PHONES = {"5491161461034", "5493885786946", "5493513976787"}

ARG = timezone(timedelta(hours=-3))
now_arg = datetime.now(ARG)
days_back = 3
start_arg = (now_arg - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
start_utc = start_arg.astimezone(timezone.utc)

print(f"Ventana: desde {start_arg.isoformat()} (ARG) -> {now_arg.isoformat()} (ARG)\n")

def fetch_execs(wf_id):
    url = f"{N8N_BASE_URL}/api/v1/executions"
    out = []
    cursor = None
    while True:
        p = {"workflowId": wf_id, "limit": 250, "includeData": "false"}
        if cursor:
            p["cursor"] = cursor
        r = requests.get(url, headers=HEADERS, params=p, timeout=30)
        r.raise_for_status()
        j = r.json()
        items = j.get("data", [])
        out.extend(items)
        cursor = j.get("nextCursor")
        if items:
            last_st = items[-1].get("startedAt") or items[-1].get("stoppedAt")
            if last_st:
                try:
                    ts = datetime.fromisoformat(last_st.replace("Z", "+00:00"))
                    if ts < start_utc:
                        break
                except Exception:
                    pass
        if not cursor:
            break
    return out

for name, wf_id in WORKFLOWS.items():
    print(f"=== {name} ({wf_id}) ===")
    try:
        all_e = fetch_execs(wf_id)
    except Exception as ex:
        print(f"  ERR: {ex}\n")
        continue
    in_window = []
    for e in all_e:
        st = e.get("startedAt") or e.get("stoppedAt")
        if not st:
            continue
        try:
            ts = datetime.fromisoformat(st.replace("Z", "+00:00"))
            if ts >= start_utc:
                in_window.append((ts, e))
        except Exception:
            pass
    if not in_window:
        print(f"  Sin ejecuciones en los ultimos {days_back} dias.\n")
        continue
    # Group by ARG day
    by_day = defaultdict(lambda: Counter())
    for ts, e in in_window:
        d = ts.astimezone(ARG).strftime("%Y-%m-%d")
        by_day[d][e.get("status", "?")] += 1
    print(f"  Total en ventana: {len(in_window)}")
    for d in sorted(by_day.keys()):
        stats = by_day[d]
        print(f"  {d}: total={sum(stats.values())}  detalle={dict(stats)}")
    print()
