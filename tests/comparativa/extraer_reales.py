# -*- coding: utf-8 -*-
"""
Arma casos de comparativa con mensajes REALES de pacientes (solo lectura de n8n_chat_histories). La salida tiene datos de pacientes:
va SIEMPRE fuera del repo (scratchpad o data/ ignorado). Los casos se corren con el número de Lucas (el webhook de pruebas no acepta otro).
USO: python tests/comparativa/extraer_reales.py <salida.json> [dias=30] [max=60] [--contexto]

--contexto (12/11, "espejo" del agente con mensajes reales): cada caso lleva el CONTEXTO REAL del paciente copiado a un escenario (fichas y turnos de
Dentalink, solo lectura; recordatorios abiertos), con ids cambiados por falsos (990…), y correr.py lo corre con el celular SINTÉTICO: nada toca el
estado del paciente real (Redis, memoria, agenda). Los turnos son los vigentes HOY desde la fecha del mensaje, no los de ese momento.
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
CONTEXTO = "--contexto" in sys.argv
args = [a for a in sys.argv[1:] if a != "--contexto"]
salida, dias, maximo = Path(args[0]), int(args[1]) if len(args) > 1 else 30, int(args[2]) if len(args) > 2 else 60
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
        casos.append({"id": f"r{len(casos)+1:03d}", "cat": "real", "fecha": t0.isoformat(), "tel": s, "texto": "\n".join(partes), "hist": hist,
                      "esperado": "(real) " + (f"{resp['quien']}: {resp['texto']}" if resp else "nadie contestó en 30 min")})
        i = j + 1
casos.sort(key=lambda x: x["fecha"], reverse=True)
casos = casos[:maximo]


def _dl(ruta, q=None):
    import urllib.parse, urllib.request
    url = "https://api.dentalink.healthatom.com/api/v1" + ruta + (("?q=" + urllib.parse.quote(json.dumps(q))) if q else "")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Token " + TOKEN}), timeout=25) as r:
        return json.loads(r.read().decode()).get("data") or []


_CACHE = {}


def contexto(tel, fecha):
    """Fichas y turnos vigentes del celular (Dentalink, solo lectura) + recordatorios abiertos, con ids falsos coherentes entre sí."""
    if tel not in _CACHE:
        fichas = _dl("/pacientes", {"celular": {"lk": tel[-10:]}})
        _CACHE[tel] = (fichas, {f["id"]: _dl(f"/pacientes/{f['id']}/citas", {"fecha": {"gte": fecha}}) for f in fichas})
    fichas, citas = _CACHE[tel]
    ids = {}

    def falso(base, real):
        if (base, real) not in ids:
            ids[(base, real)] = base + 1 + sum(1 for k in ids if k[0] == base)
        return ids[(base, real)]
    esc = {"fichas": [], "citas": {}}
    for f in fichas:
        fid = falso(990000000, f["id"])
        esc["fichas"].append({"id": fid, "nombre": f.get("nombre"), "apellidos": f.get("apellidos"), "rut": "4" + str(fid)[-7:]})
        for x in citas.get(f["id"], []):
            if str(x.get("fecha", "")) < fecha or x.get("estado_anulacion"):
                continue
            esc["citas"].setdefault(str(fid), []).append({"id": falso(990000100, x["id"]), "id_paciente": fid, "fecha": x["fecha"],
                                                         "hora_inicio": str(x.get("hora_inicio", ""))[:8], "id_estado": x.get("id_estado"), "estado_anulacion": 0})
    cur.execute("""select id_cita_dentalink, id_paciente_dentalink, nombre_paciente, fecha_turno, hora_turno from recordatorios_enviados
      where telefono = %s and fecha_turno >= %s::date""", (tel, fecha))
    recs = []
    for cid, pid, nom, ft, ht in cur.fetchall():
        if (990000000, pid) in ids and (990000100, cid) in ids:   # si el turno ya no está vigente, el recordatorio no va
            recs.append({"id_cita_dentalink": ids[(990000100, cid)], "id_paciente_dentalink": ids[(990000000, pid)], "nombre_paciente": nom,
                         "fecha_turno": str(ft), "hora_turno": str(ht)[:5]})
    return (esc if esc["fichas"] else None), recs


if CONTEXTO:
    sys.path.insert(0, str(ROOT / "scripts"))
    from migrar_dentalink import leer_token
    TOKEN = leer_token()
    for x in casos:
        try:
            x["escenario"], x["recordatorios"] = contexto(x["tel"], x["fecha"][:10])
        except Exception as e:
            x["escenario"], x["recordatorios"], x["error_contexto"] = None, [], str(e)[:200]
    print("con ficha:", sum(1 for x in casos if x.get("escenario")), "· sin ficha (nuevos):", sum(1 for x in casos if not x.get("escenario")),
          "· errores:", sum(1 for x in casos if x.get("error_contexto")))
salida.write_text(json.dumps(casos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(len(casos), "casos de", len({x['id'] for x in casos}), "->", salida)
from collections import Counter
print(Counter(x["esperado"].split(":")[0] for x in casos))
