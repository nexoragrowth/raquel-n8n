# -*- coding: utf-8 -*-
"""
seed_examen_v7.py — siembra y limpia el ESTADO REAL que el examen del v7 no puede fingir: la fila de recordatorio abierta en
`recordatorios_enviados` (lo que confirmar_turno y el contexto del cerebro leen) para una cita REAL de prueba en Dentalink.
La cita la crea Lucas a mano en Dentalink (ficha "Test - Lucas", id 608); este script NO toca Dentalink.

  python tests/seed_examen_v7.py --estado                                   # qué hay hoy para el celular de prueba
  python tests/seed_examen_v7.py --sembrar --cita 9999 --fecha 2026-10-14 --hora 09:10 [--tipo 48h]   # fila de recordatorio abierta (idempotente)
  python tests/seed_examen_v7.py --reabrir                                   # vuelve a dejar abierto el recordatorio (confirmado_at/cancelado_at = NULL) entre repeticiones
  python tests/seed_examen_v7.py --limpiar                                   # borra las filas sembradas por este script + memoria del celular (regla 9)

Necesita SUPABASE_DB_HOST/PORT/NAME/USER/PASSWORD (como el resto de scripts/). Marca todo lo que siembra con workflow_execution_id = 'examen-v7'.
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from lib_env import env  # noqa: E402

import psycopg2  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PHONE = "5491161461034"
JID = PHONE + "@s.whatsapp.net"
PACIENTE_ID = 608
NOMBRE = "Test - Lucas"
MARCA = "examen-v7"


def conectar():
    faltan = [k for k in ("SUPABASE_DB_HOST", "SUPABASE_DB_USER", "SUPABASE_DB_PASSWORD") if not env(k)]
    if faltan:
        sys.exit("faltan variables de entorno: " + ", ".join(faltan))
    return psycopg2.connect(host=env("SUPABASE_DB_HOST"), port=int(env("SUPABASE_DB_PORT", "5432")), dbname=env("SUPABASE_DB_NAME", "postgres"),
                            user=env("SUPABASE_DB_USER"), password=env("SUPABASE_DB_PASSWORD"), connect_timeout=15)


def estado(cur, phone):
    cur.execute("SELECT id, id_cita_dentalink, nombre_paciente, fecha_turno, hora_turno, tipo, confirmado_at, cancelado_at, workflow_execution_id "
                "FROM recordatorios_enviados WHERE telefono = %s ORDER BY id DESC LIMIT 10", (phone,))
    filas = cur.fetchall()
    print(f"recordatorios_enviados del {phone}: {len(filas)} fila(s) recientes")
    for f in filas:
        print("   id=%s cita=%s %s %s %s tipo=%s confirmado=%s cancelado=%s origen=%s" % f)
    cur.execute("SELECT count(*) FROM n8n_chat_histories WHERE session_id = %s", (phone,))
    print(f"n8n_chat_histories del {phone}: {cur.fetchone()[0]} fila(s)")
    cur.execute("SELECT human_takeover, human_takeover_at FROM pacientes WHERE telefono = %s", (phone,))
    r = cur.fetchone()
    print(f"pacientes.human_takeover: {r[0] if r else '(sin fila)'} ({r[1] if r else ''})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phone", default=PHONE)
    ap.add_argument("--estado", action="store_true"); ap.add_argument("--sembrar", action="store_true"); ap.add_argument("--reabrir", action="store_true"); ap.add_argument("--limpiar", action="store_true")
    ap.add_argument("--cita", type=int, help="id de la cita REAL de prueba en Dentalink"); ap.add_argument("--fecha"); ap.add_argument("--hora"); ap.add_argument("--tipo", default="48h")
    a = ap.parse_args()
    con = conectar(); con.autocommit = False; cur = con.cursor()
    try:
        if a.estado or not (a.sembrar or a.reabrir or a.limpiar):
            estado(cur, a.phone); return
        if a.sembrar:
            if not (a.cita and a.fecha and a.hora):
                sys.exit("--sembrar necesita --cita <id> --fecha YYYY-MM-DD --hora HH:MM (la cita real que creaste en Dentalink)")
            cur.execute("""INSERT INTO recordatorios_enviados (telefono, chat_remote_jid, id_cita_dentalink, id_paciente_dentalink, nombre_paciente, fecha_turno, hora_turno, tipo, workflow_execution_id)
                           SELECT %s, %s, %s, %s, %s, %s::date, %s::time, %s, %s
                           WHERE NOT EXISTS (SELECT 1 FROM recordatorios_enviados WHERE id_cita_dentalink = %s AND workflow_execution_id = %s)
                           RETURNING id""", (a.phone, a.phone + "@s.whatsapp.net", a.cita, PACIENTE_ID, NOMBRE, a.fecha, a.hora, a.tipo, MARCA, a.cita, MARCA))
            r = cur.fetchone(); con.commit()
            print(f"recordatorio sembrado: {'id ' + str(r[0]) if r else 'ya existía (idempotente)'} · cita {a.cita} {a.fecha} {a.hora} · marca {MARCA}")
        if a.reabrir:
            cur.execute("UPDATE recordatorios_enviados SET confirmado_at = NULL, cancelado_at = NULL WHERE telefono = %s AND workflow_execution_id = %s RETURNING id", (a.phone, MARCA))
            n = cur.rowcount; con.commit(); print(f"recordatorios reabiertos: {n}")
        if a.limpiar:
            cur.execute("DELETE FROM recordatorios_enviados WHERE telefono = %s AND workflow_execution_id = %s", (a.phone, MARCA)); n1 = cur.rowcount
            cur.execute("DELETE FROM n8n_chat_histories WHERE session_id = %s", (a.phone,)); n2 = cur.rowcount
            con.commit(); print(f"limpieza: {n1} recordatorio(s) sembrado(s) borrado(s), {n2} fila(s) de memoria del celular borradas. La cita de Dentalink la anula Lucas a mano.")
        estado(cur, a.phone)
    finally:
        con.close()


if __name__ == "__main__":
    main()
