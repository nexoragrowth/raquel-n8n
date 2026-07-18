#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rebuild_v3_backfill_recordatorios.py — Backfill de `recordatorios_enviados` en Supabase v3.

CONTEXTO (2026-07-17)
  El proyecto Supabase v2 (ujfyapjwrdhnvqdvsjwp) murió en crash-loop irrecuperable.
  Los recordatorios del WF "Recordatorio 48HS" (7RqTApkvVavRmq3R) del 16/7 (exec 230100)
  y 17/7 (exec 231766) SÍ salieron por WhatsApp (nodo "Enviar WhatsApp": success=true
  en los 13 items, con message-id de Evolution), pero el nodo
  "Insert recordatorios_enviados" falló porque la base ya estaba caída:
    - 230100: Failed to connect to database: {:error, :econnrefused}
    - 231766: (EAUTHQUERY) authentication query failed: connection to database not available
  Sin estas filas, las confirmaciones/cancelaciones de esos pacientes no matchean
  ningún recordatorio abierto (las tools consultar_recordatorios_abiertos /
  marcar_recordatorio_* no encuentran nada) y todo escala a Iri a mano.

  Los datos de abajo fueron extraídos el 2026-07-17 vía
  GET /api/v1/executions/{id}?includeData=true (runData del nodo "Preparar mensaje",
  cruzado con "Enviar WhatsApp"), ANTES de que n8n purgara el exec del 16/7 (~72h de
  retención). Raw JSON preservado en:
    workflows/history/exec_230100_recordatorio_20260716_raw.json
    workflows/history/exec_231766_recordatorio_20260717_raw.json

CUÁNDO CORRERLO
  Después de crear el proyecto Supabase v3 y correr scripts/rebuild_v3_schema.sql
  (que crea la tabla `recordatorios_enviados`). Orden completo en el epílogo de ese SQL.

CÓMO
  1. Completar NEW_HOST / NEW_USER / NEW_PASSWORD abajo (o exportar
     SUPABASE_V3_DB_HOST / SUPABASE_V3_DB_USER / SUPABASE_V3_DB_PASSWORD).
  2. python scripts/rebuild_v3_backfill_recordatorios.py --dry-run   (ver qué haría)
  3. python scripts/rebuild_v3_backfill_recordatorios.py             (insertar)

  Idempotente: dedup por (id_cita_dentalink, fecha_turno) con check previo
  (la tabla NO tiene UNIQUE sobre ese par — solo un índice normal — así que
  ON CONFLICT no aplica; se usa INSERT ... WHERE NOT EXISTS por fila).
  Requiere: pip install psycopg2-binary
"""

import os
import sys
import argparse

sys.stdout.reconfigure(encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# PARÁMETROS DEL PROYECTO v3 — COMPLETAR AL CREARLO (o vía variables de entorno)
# ─────────────────────────────────────────────────────────────────────────────
NEW_HOST = os.environ.get("SUPABASE_V3_DB_HOST", "")  # ej: aws-1-us-west-2.pooler.supabase.com
NEW_PORT = int(os.environ.get("SUPABASE_V3_DB_PORT", "5432"))
NEW_DBNAME = os.environ.get("SUPABASE_V3_DB_NAME", "postgres")
NEW_USER = os.environ.get("SUPABASE_V3_DB_USER", "")  # ej: postgres.<project_ref_v3>
NEW_PASSWORD = os.environ.get("SUPABASE_V3_DB_PASSWORD", "")
SSLMODE = os.environ.get("SUPABASE_V3_DB_SSLMODE", "require")

# ─────────────────────────────────────────────────────────────────────────────
# DATOS EMBEBIDOS — extraídos de los execs reales el 2026-07-17 (fuente de verdad:
# runData de "Preparar mensaje"; wa_message_id viene de "Enviar WhatsApp" y es solo
# auditoría, NO se inserta). tipo real = "72h" en los 13 (no "48h").
# enviado_at = startedAt del exec (11:00Z = 08:00 ART, el envío es segundos después).
# Ojo: en 231766 hay 2 citas distintas con el MISMO teléfono (Ambar/Delfina,
# 5493884373448) — el dedup por cita+fecha las conserva a ambas, correcto.
# ─────────────────────────────────────────────────────────────────────────────
DATA = [
    # ── exec 230100 · enviado 2026-07-16 11:00Z · turnos del lunes 2026-07-20 ──
    {"telefono": "5493885706739", "chat_remote_jid": "5493885706739@s.whatsapp.net",
     "id_cita_dentalink": 8387, "id_paciente_dentalink": 588, "nombre_paciente": "Amelia",
     "fecha_turno": "2026-07-20", "hora_turno": "15:00", "tipo": "72h",
     "workflow_execution_id": "230100-backfill", "enviado_at": "2026-07-16T11:00:00Z",
     "wa_message_id": "3EB038D03983A2183BC9F2"},
    {"telefono": "5493888650362", "chat_remote_jid": "5493888650362@s.whatsapp.net",
     "id_cita_dentalink": 8373, "id_paciente_dentalink": 382, "nombre_paciente": "Dina",
     "fecha_turno": "2026-07-20", "hora_turno": "18:50", "tipo": "72h",
     "workflow_execution_id": "230100-backfill", "enviado_at": "2026-07-16T11:00:00Z",
     "wa_message_id": "3EB096BC3531A2CE57090E"},
    {"telefono": "5493884040259", "chat_remote_jid": "5493884040259@s.whatsapp.net",
     "id_cita_dentalink": 8341, "id_paciente_dentalink": 427, "nombre_paciente": "Justina",
     "fecha_turno": "2026-07-20", "hora_turno": "15:40", "tipo": "72h",
     "workflow_execution_id": "230100-backfill", "enviado_at": "2026-07-16T11:00:00Z",
     "wa_message_id": "3EB037DEAADB685932946B"},
    {"telefono": "5493513412923", "chat_remote_jid": "5493513412923@s.whatsapp.net",
     "id_cita_dentalink": 8338, "id_paciente_dentalink": 543, "nombre_paciente": "Joaquin",
     "fecha_turno": "2026-07-20", "hora_turno": "16:20", "tipo": "72h",
     "workflow_execution_id": "230100-backfill", "enviado_at": "2026-07-16T11:00:00Z",
     "wa_message_id": "3EB089F8ADB1984C921118"},
    {"telefono": "5493885983004", "chat_remote_jid": "5493885983004@s.whatsapp.net",
     "id_cita_dentalink": 8316, "id_paciente_dentalink": 111, "nombre_paciente": "Juan Jose",
     "fecha_turno": "2026-07-20", "hora_turno": "17:40", "tipo": "72h",
     "workflow_execution_id": "230100-backfill", "enviado_at": "2026-07-16T11:00:00Z",
     "wa_message_id": "3EB0498A6899A28DB55DA0"},
    {"telefono": "5493884840210", "chat_remote_jid": "5493884840210@s.whatsapp.net",
     "id_cita_dentalink": 8252, "id_paciente_dentalink": 587, "nombre_paciente": "Abril",
     "fecha_turno": "2026-07-20", "hora_turno": "17:00", "tipo": "72h",
     "workflow_execution_id": "230100-backfill", "enviado_at": "2026-07-16T11:00:00Z",
     "wa_message_id": "3EB02EC61B05A39B5BCC0F"},
    {"telefono": "5493884045024", "chat_remote_jid": "5493884045024@s.whatsapp.net",
     "id_cita_dentalink": 7130, "id_paciente_dentalink": 108, "nombre_paciente": "David",
     "fecha_turno": "2026-07-20", "hora_turno": "18:20", "tipo": "72h",
     "workflow_execution_id": "230100-backfill", "enviado_at": "2026-07-16T11:00:00Z",
     "wa_message_id": "3EB09AB508A8DFFC2C84A5"},
    # ── exec 231766 · enviado 2026-07-17 11:00Z · turnos del martes 2026-07-21 ──
    {"telefono": "5493883343595", "chat_remote_jid": "5493883343595@s.whatsapp.net",
     "id_cita_dentalink": 8498, "id_paciente_dentalink": 494, "nombre_paciente": "Duilio Ivan",
     "fecha_turno": "2026-07-21", "hora_turno": "08:40", "tipo": "72h",
     "workflow_execution_id": "231766-backfill", "enviado_at": "2026-07-17T11:00:00Z",
     "wa_message_id": "3EB01037F6DD8A1B6A21C5"},
    {"telefono": "5493885086953", "chat_remote_jid": "5493885086953@s.whatsapp.net",
     "id_cita_dentalink": 8386, "id_paciente_dentalink": 459, "nombre_paciente": "Hernán Andres",
     "fecha_turno": "2026-07-21", "hora_turno": "09:20", "tipo": "72h",
     "workflow_execution_id": "231766-backfill", "enviado_at": "2026-07-17T11:00:00Z",
     "wa_message_id": "3EB06E09D902F7D17AE852"},
    {"telefono": "5493884373448", "chat_remote_jid": "5493884373448@s.whatsapp.net",
     "id_cita_dentalink": 8367, "id_paciente_dentalink": 639, "nombre_paciente": "Ambar Sofía",
     "fecha_turno": "2026-07-21", "hora_turno": "11:20", "tipo": "72h",
     "workflow_execution_id": "231766-backfill", "enviado_at": "2026-07-17T11:00:00Z",
     "wa_message_id": "3EB0E2496FDFDBA6001462"},
    {"telefono": "5493884373448", "chat_remote_jid": "5493884373448@s.whatsapp.net",
     "id_cita_dentalink": 8365, "id_paciente_dentalink": 638, "nombre_paciente": "Delfina Aitana",
     "fecha_turno": "2026-07-21", "hora_turno": "10:40", "tipo": "72h",
     "workflow_execution_id": "231766-backfill", "enviado_at": "2026-07-17T11:00:00Z",
     "wa_message_id": "3EB0DBB4FB840E4F1D0854"},
    {"telefono": "5493884889523", "chat_remote_jid": "5493884889523@s.whatsapp.net",
     "id_cita_dentalink": 8352, "id_paciente_dentalink": 110, "nombre_paciente": "Geronimo",
     "fecha_turno": "2026-07-21", "hora_turno": "10:00", "tipo": "72h",
     "workflow_execution_id": "231766-backfill", "enviado_at": "2026-07-17T11:00:00Z",
     "wa_message_id": "3EB057690C3D47AE42F328"},
    {"telefono": "5493885704717", "chat_remote_jid": "5493885704717@s.whatsapp.net",
     "id_cita_dentalink": 8322, "id_paciente_dentalink": 347, "nombre_paciente": "Claudia",
     "fecha_turno": "2026-07-21", "hora_turno": "08:00", "tipo": "72h",
     "workflow_execution_id": "231766-backfill", "enviado_at": "2026-07-17T11:00:00Z",
     "wa_message_id": "3EB0839F922C6FEDCE1282"},
]

EXISTS_SQL = """
SELECT id FROM recordatorios_enviados
WHERE id_cita_dentalink = %(id_cita_dentalink)s
  AND fecha_turno = %(fecha_turno)s::date
LIMIT 1;
"""

INSERT_SQL = """
INSERT INTO recordatorios_enviados
  (telefono, chat_remote_jid, id_cita_dentalink, id_paciente_dentalink,
   nombre_paciente, fecha_turno, hora_turno, tipo, workflow_execution_id, enviado_at)
SELECT
  %(telefono)s, %(chat_remote_jid)s, %(id_cita_dentalink)s, %(id_paciente_dentalink)s,
  %(nombre_paciente)s, %(fecha_turno)s::date, %(hora_turno)s, %(tipo)s,
  %(workflow_execution_id)s, %(enviado_at)s::timestamptz
WHERE NOT EXISTS (
  SELECT 1 FROM recordatorios_enviados r
  WHERE r.id_cita_dentalink = %(id_cita_dentalink)s
    AND r.fecha_turno = %(fecha_turno)s::date
)
RETURNING id;
"""

VERIFY_SQL = """
SELECT id, telefono, id_cita_dentalink, nombre_paciente,
       fecha_turno::text, hora_turno, tipo, workflow_execution_id
FROM recordatorios_enviados
WHERE workflow_execution_id IN ('230100-backfill', '231766-backfill')
ORDER BY fecha_turno, hora_turno;
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill recordatorios 16/7 + 17/7 en Supabase v3")
    ap.add_argument("--dry-run", action="store_true",
                    help="solo chequea qué falta insertar, no escribe nada")
    args = ap.parse_args()

    if not NEW_HOST or not NEW_USER or not NEW_PASSWORD:
        print("ERROR: completar NEW_HOST / NEW_USER / NEW_PASSWORD arriba del archivo")
        print("       (o exportar SUPABASE_V3_DB_HOST / SUPABASE_V3_DB_USER / SUPABASE_V3_DB_PASSWORD)")
        return 1

    try:
        import psycopg2
    except ImportError:
        print("ERROR: falta psycopg2 -> pip install psycopg2-binary")
        return 1

    print(f"Conectando a {NEW_USER}@{NEW_HOST}:{NEW_PORT}/{NEW_DBNAME} (sslmode={SSLMODE})...")
    conn = psycopg2.connect(
        host=NEW_HOST, port=NEW_PORT, dbname=NEW_DBNAME,
        user=NEW_USER, password=NEW_PASSWORD,
        sslmode=SSLMODE, connect_timeout=20,
    )
    inserted, skipped = 0, 0
    try:
        with conn:  # transacción: commit al salir bien, rollback si explota
            with conn.cursor() as cur:
                # sanity: la tabla existe? (si no -> correr rebuild_v3_schema.sql primero)
                cur.execute("SELECT to_regclass('public.recordatorios_enviados');")
                if cur.fetchone()[0] is None:
                    print("ERROR: la tabla recordatorios_enviados NO existe en esta base.")
                    print("       Correr scripts/rebuild_v3_schema.sql primero.")
                    return 1

                for row in DATA:
                    tag = (f"cita {row['id_cita_dentalink']} {row['fecha_turno']} "
                           f"{row['hora_turno']} {row['nombre_paciente']}")
                    if args.dry_run:
                        cur.execute(EXISTS_SQL, row)
                        if cur.fetchone():
                            print(f"  [dry] YA EXISTE  {tag}")
                            skipped += 1
                        else:
                            print(f"  [dry] INSERTARIA {tag}")
                            inserted += 1
                        continue
                    cur.execute(INSERT_SQL, row)
                    got = cur.fetchone()
                    if got:
                        print(f"  INSERTADO id={got[0]:<5} {tag}")
                        inserted += 1
                    else:
                        print(f"  DEDUP (ya existía)   {tag}")
                        skipped += 1

                verbo = "insertaría" if args.dry_run else "insertados"
                print(f"\nResumen: {verbo}={inserted}  dedup/skip={skipped}  total_data={len(DATA)}")

                if not args.dry_run:
                    cur.execute(VERIFY_SQL)
                    rows = cur.fetchall()
                    print(f"\nVerificación — filas backfill en la base: {len(rows)}")
                    for r in rows:
                        print("   ", r)
                    if len(rows) != len(DATA):
                        print(f"ATENCIÓN: se esperaban {len(DATA)} filas backfill "
                              f"y hay {len(rows)} — revisar dedup vs datos preexistentes.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
