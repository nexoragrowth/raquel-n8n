# -*- coding: utf-8 -*-
"""
create_triaje_urgencias_log_table.py — crea la tabla `triaje_urgencias_log` en Supabase v3.

Es el registro del triaje de urgencias (Capa 6 del diseño del 2/9): una fila por urgencia
evaluada, con lo que dijo el gate determinístico de red flags, lo que clasificó el LLM y
qué acción se tomó. En Fase 1 (sombra) la llena el workflow satélite "Áurea — Triaje
Urgencias (sombra)" leyendo `escalaciones_log`; en fases posteriores la llena el v6 en
línea. Tabla propia (no `escalaciones_log`) para que la sombra NO ensucie /aprendizaje ni
el reportero semanal — y para que el futuro "scoring de urgencias" del reportero lea de acá.

Aditiva e idempotente (IF NOT EXISTS). No toca ninguna tabla existente.

Uso: python scripts/create_triaje_urgencias_log_table.py [--apply]
"""
import sys, argparse, psycopg2
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

DDL = """
CREATE TABLE IF NOT EXISTS triaje_urgencias_log (
    id                     BIGSERIAL PRIMARY KEY,
    escalacion_id          BIGINT UNIQUE REFERENCES escalaciones_log(id) ON DELETE SET NULL,
    telefono               TEXT,
    exec_id                TEXT,
    escalacion_created_at  TIMESTAMPTZ,
    motivo_bot             TEXT,
    mensaje_paciente       TEXT,
    gate_red_flags         JSONB NOT NULL DEFAULT '[]'::jsonb,
    gate_escala            BOOLEAN NOT NULL DEFAULT FALSE,
    tipo                   TEXT,        -- red_flag | alambre_pincha | bracket_suelto | alambre_girado | ligadura_pincha | otra_urgencia | no_urgencia | error_llm
    confianza              TEXT,        -- alta | media | baja
    razon                  TEXT,
    modelo                 TEXT,
    modo                   TEXT NOT NULL DEFAULT 'sombra',    -- sombra | piloto | live
    accion                 TEXT NOT NULL DEFAULT 'escalado',  -- escalado | video
    video_enviado          TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_triaje_created ON triaje_urgencias_log (created_at);
CREATE INDEX IF NOT EXISTS idx_triaje_tipo    ON triaje_urgencias_log (tipo);
"""

ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); args = ap.parse_args()
db = load_env(".env", {"SUPABASE_DB_HOST","SUPABASE_DB_PORT","SUPABASE_DB_NAME","SUPABASE_DB_USER","SUPABASE_DB_PASSWORD"})
conn = psycopg2.connect(host=db["SUPABASE_DB_HOST"], port=db["SUPABASE_DB_PORT"], dbname=db["SUPABASE_DB_NAME"],
                        user=db["SUPABASE_DB_USER"], password=db["SUPABASE_DB_PASSWORD"], sslmode="require", connect_timeout=20)
conn.autocommit = True; cur = conn.cursor()

cur.execute("SELECT to_regclass('public.triaje_urgencias_log')")
print("tabla existe antes:", cur.fetchone()[0])
cur.execute("SELECT rol, count(*) FROM conversaciones GROUP BY rol ORDER BY 2 DESC")
print("valores reales de conversaciones.rol:", cur.fetchall())

if not args.apply:
    print("\n(preview — no se creó nada). DDL:\n" + DDL + "\nPara aplicar: --apply")
else:
    cur.execute(DDL)
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='triaje_urgencias_log' ORDER BY ordinal_position")
    print("\ncolumnas creadas:")
    for c in cur.fetchall(): print("  ", c[0], c[1])
    print("✅ triaje_urgencias_log lista")
cur.close(); conn.close()
