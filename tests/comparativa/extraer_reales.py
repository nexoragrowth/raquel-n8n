# -*- coding: utf-8 -*-
"""
Arma casos de comparativa con mensajes REALES de pacientes (solo lectura de n8n_chat_histories). La salida tiene datos de pacientes:
va SIEMPRE fuera del repo (scratchpad o data/ ignorado). Los casos se corren con el número de Lucas (el webhook de pruebas no acepta otro).
USO: python tests/comparativa/extraer_reales.py <salida.json> [dias=30] [max=60]
"""
import json, re, sys, datetime, psycopg2
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent.parent
env = {}
for l in (ROOT / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
    m = re.match(r"\s*(SUPABASE_DB_[A-Z]+)\s*=\s*(.*)", l)
    if m: env[m.group(1)] = m.group(2).strip().strip("'\"")
ADMIN = {"5491161461034", "5493885786946", "5493513976787"}
QUIEN = {"wa_inbound": "paciente", "asiri_v7": "asiri", "wa_outbound": "staff", "reminder_note": "recordatorio"}
salida, dias, maximo = Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 30, int(sys.argv[3]) if len(sys.argv) > 3 else 60
c = psycopg2.connect(host=env["SUPABASE_DB_HOST"], port=env["SUPABASE_DB_PORT"], dbname=env["SUPABASE_DB_NAME"], user=env["SUPABASE_DB_USER"], password=env["SUPABASE_DB_PASSWORD"], sslmode="require")
c.set_session(readonly=True)
cur = c.cursor()
cur.execute("""select session_id, message, created_at from n8n_chat_histories
  where session_id ~ '^[0-9]+$' and created_at > now() - make_interval(days => %s + 3) order by session_id, created_at, id""", (dias,))
por = {}
for s, m, t in cur.fetchall():
    if s in ADMIN: continue
    src = (m.get("additional_kwargs") or {}).get("source") or ("wa_inbound" if m.get("type") == "human" else "asiri_v7")
    por.setdefault(s, []).append({"src": src, "texto": str(m.get("content") or ""), "t": t})
desde = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=dias)
casos = []
for s, msgs in por.items():
    i = 0
    while i < len(msgs):
        m = msgs[i]
        if m["src"] != "wa_inbound" or m["t"] < desde:
            i += 1; continue
        j = i; partes = [m["texto"]]
        while j + 1 < len(msgs) and msgs[j + 1]["src"] == "wa_inbound" and (msgs[j + 1]["t"] - msgs[j]["t"]).total_seconds() < 120:
            j += 1; partes.append(msgs[j]["texto"])
        t0 = msgs[j]["t"]
        resp = None
        for k in range(j + 1, len(msgs)):
            if msgs[k]["src"] == "wa_inbound": break
            if (msgs[k]["t"] - t0).total_seconds() > 1800: break
            if msgs[k]["src"] in ("asiri_v7", "wa_outbound") or msgs[k]["src"].startswith("triaje"):
                resp = {"quien": "asiri" if msgs[k]["src"] != "wa_outbound" else "secretaria", "texto": msgs[k]["texto"][:600]}; break
        hist = []
        for h in reversed(msgs[max(0, i - 10):i]):
            q = QUIEN.get(h["src"])
            if q: hist.append({"quien": q, "hace_min": max(1, int((t0 - h["t"]).total_seconds() // 60)), "texto": h["texto"][:1500]})
        casos.append({"id": f"r{len(casos)+1:03d}", "cat": "real", "fecha": t0.isoformat(), "texto": "\n".join(partes), "hist": hist,
                      "esperado": "(real) " + (f"{resp['quien']}: {resp['texto']}" if resp else "nadie contestó en 30 min")})
        i = j + 1
casos.sort(key=lambda x: x["fecha"], reverse=True)
casos = casos[:maximo]
salida.write_text(json.dumps(casos, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(casos), "casos de", len({x['id'] for x in casos}), "->", salida)
from collections import Counter
print(Counter(x["esperado"].split(":")[0] for x in casos))
