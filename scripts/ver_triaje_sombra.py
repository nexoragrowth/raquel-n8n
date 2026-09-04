# -*- coding: utf-8 -*-
"""
ver_triaje_sombra.py — muestra lo que va registrando "Áurea — Triaje Urgencias (sombra)"
en `triaje_urgencias_log` (teléfonos enmascarados) + distribución por tipo y flags del gate.

Uso: python scripts/ver_triaje_sombra.py [--dias 7] [--limit 50]
"""
import sys, argparse, psycopg2
from collections import Counter
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

def load_env(path, keys):
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1); v = v.strip().strip('"').strip("'")
        if k in keys: out[k] = v
    return out

ap = argparse.ArgumentParser(); ap.add_argument("--dias", type=int, default=7); ap.add_argument("--limit", type=int, default=50)
args = ap.parse_args()
db = load_env(".env", {"SUPABASE_DB_HOST","SUPABASE_DB_PORT","SUPABASE_DB_NAME","SUPABASE_DB_USER","SUPABASE_DB_PASSWORD"})
conn = psycopg2.connect(host=db["SUPABASE_DB_HOST"], port=db["SUPABASE_DB_PORT"], dbname=db["SUPABASE_DB_NAME"],
                        user=db["SUPABASE_DB_USER"], password=db["SUPABASE_DB_PASSWORD"], sslmode="require", connect_timeout=20)
cur = conn.cursor()
cur.execute("""
    SELECT id, escalacion_id, telefono, escalacion_created_at, tipo, confianza, gate_escala, gate_red_flags, razon, motivo_bot, mensaje_paciente, modo, accion, created_at
    FROM triaje_urgencias_log
    WHERE created_at > NOW() - (%s || ' days')::interval
    ORDER BY escalacion_created_at DESC LIMIT %s
""", (str(args.dias), args.limit))
rows = cur.fetchall()
print(f"filas en triaje_urgencias_log (últimos {args.dias} días): {len(rows)}\n")
tipos, flags = Counter(), Counter()
for (rid, eid, tel, ecat, tipo, conf, gesc, gflags, razon, motivo, msg, modo, accion, cat) in rows:
    tipos[tipo] += 1
    for f in (gflags or []): flags[f] += 1
    tel_m = ("…" + tel[-4:]) if tel and len(tel) >= 4 else "…"
    print(f"#{rid} esc={eid} {ecat:%d/%m %H:%M} tel {tel_m} | {tipo} ({conf}) gate={'ESCALA' if gesc else 'ok'} {gflags} | {modo}/{accion}")
    print(f"   motivo: {(motivo or '')[:110]}")
    if msg: print(f"   paciente: {msg.replace(chr(10), ' / ')[:110]}")
    print(f"   razón: {(razon or '')[:110]}\n")
print("por tipo:", dict(tipos))
print("flags:", dict(flags))
cur.close(); conn.close()
