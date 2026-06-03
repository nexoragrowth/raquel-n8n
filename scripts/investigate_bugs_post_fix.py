"""
Investiga execs reales post-22/5 (despues de Round 8) para los 3 bugs sospechosos:
1. Ines Berruezo pattern: multi-turno donde bot muestra opciones y se confunde con horas
2. Evelina Garcia pattern: bot pregunta "querias agendar un turno?" presuntuoso
3. Martina Cazon pattern: paciente elige slot de las opciones, bot escala en lugar de reservar

Para cada uno: busca pattern en outputs del bot en execs de los ultimos 4 dias.
Reporta cuantos casos encontro y muestra ejemplos.
"""
import json, sys, io
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF_V6 = require("N8N_WORKFLOW_V6_ID")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json"}

# Ventana: ultimos 4 dias (post Round 8 que fue 22/5 noche)
ARG = timezone(timedelta(hours=-3))
now_arg = datetime.now(ARG)
since = (now_arg - timedelta(days=4)).astimezone(timezone.utc)
print(f"Investigando execs desde {since.isoformat()} hasta ahora")

# Patrones que indicarian que un bug aun ocurre
PATTERNS = {
    "evelina_querias_agendar": [
        "querias agendar un turno",
        "querías agendar un turno",
    ],
    "martina_escalo_eligiendo_slot": [
        # Pattern: bot ofrecio opciones de horarios + paciente eligio una + bot escalo
        # Detectable solo viendo conversaciones, no por pattern simple en output
    ],
    "ines_confundio_horas": [
        # Bot dice una hora distinta a la que el paciente pidio
        # Detectable solo viendo conversaciones
    ],
    # Confirmacion patterns que indicarian ya curado
    "confirmacion_exitosa": [
        "queda confirmado",
        "confirmados los",
    ],
}

# Pull execs paginadas
execs = []
cursor = None
for _ in range(10):
    params = {"workflowId": WF_V6, "limit": 250}
    if cursor: params["cursor"] = cursor
    import urllib.parse
    q = urllib.parse.urlencode(params)
    j = requests.get(f"{N8N}/api/v1/executions?{q}", headers=H, timeout=30).json()
    execs.extend(j.get("data", []))
    cursor = j.get("nextCursor")
    if not cursor: break
    # filtrar por fecha
    if execs:
        last_st = execs[-1].get("startedAt")
        if last_st:
            ts = datetime.fromisoformat(last_st.replace("Z","+00:00"))
            if ts < since: break

print(f"Total execs cargadas: {len(execs)}")
# Filtrar por fecha
in_window = []
for e in execs:
    st = e.get("startedAt")
    if not st: continue
    ts = datetime.fromisoformat(st.replace("Z","+00:00"))
    if ts >= since:
        in_window.append(e)
print(f"En ventana ({since.isoformat()[:10]}+): {len(in_window)}")

# Sample iterativo para no quemar memoria — agarrar 60 al azar
import random
random.seed(42)
sample = random.sample(in_window, min(60, len(in_window)))
print(f"Sampling {len(sample)} execs para inspect\n")

found = {k: [] for k in PATTERNS.keys()}
errors = 0
for e in sample:
    try:
        d = requests.get(f"{N8N}/api/v1/executions/{e['id']}?includeData=true",
                         headers=H, timeout=30).json()
    except Exception:
        errors += 1; continue
    rd = d.get("data",{}).get("resultData",{}).get("runData",{})
    # Output del bot (Split en Mensajes)
    sm = rd.get("Split en Mensajes", [])
    for run in sm:
        main = run.get("data",{}).get("main",[])
        if main and main[0]:
            for it in main[0]:
                msg = (it.get("json",{}).get("message") or "").lower()
                for pat_name, patterns in PATTERNS.items():
                    for p in patterns:
                        if p.lower() in msg:
                            ef = rd.get("Edit Fields - Extraer Datos", [])
                            phone = ""
                            if ef:
                                try: phone = ef[0]["data"]["main"][0][0]["json"].get("phone","")
                                except: pass
                            ts_str = e.get("startedAt","")[:19].replace("T"," ")
                            found[pat_name].append({
                                "exec": e["id"], "ts": ts_str, "phone": phone[-6:],
                                "msg": msg[:200]
                            })

print(f"\n========== RESULTADOS ==========")
for pat_name, hits in found.items():
    print(f"\n{pat_name}: {len(hits)} matches")
    for h in hits[:5]:
        print(f"  exec={h['exec']} ts={h['ts']} ph=...{h['phone']}")
        print(f"    msg: {h['msg'][:150]}")
