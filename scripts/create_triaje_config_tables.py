# -*- coding: utf-8 -*-
"""
create_triaje_config_tables.py — tablas de CONFIGURACIÓN del triaje de urgencias con video
(Fase 2, 2026-09-04). Todo lo que ve el paciente y todo lo que decide el piloto vive acá,
no en n8n: prender/apagar, allow-list de teléfonos piloto, videos por tipo/opción, captions,
pregunta guiada, textos de salida/cierre/escalada, regexes de seguimiento, TTLs, modelo.

- `triaje_config`  (fila única id=1): kill-switch y parámetros globales.
- `triaje_videos`  (tipo, opcion): un video por opción; `activo=false` => el tipo escala como hoy.
- `triaje_urgencias_log`: se le agregan columnas (ADD COLUMN IF NOT EXISTS, no rompe la sombra).

Aditivo e idempotente. Nace con `triaje_config.activo=false` (el v6 sigue escalando todo hasta
que se active por dato). Seeds = textos BORRADOR (los de la Dra. del 28/8 adaptados a la voz del
bot); Raquel los corrige con UPDATE, nunca tocando n8n.

Uso:
  python scripts/create_triaje_config_tables.py                # preview DDL
  python scripts/create_triaje_config_tables.py --apply        # crea tablas + seeds
  python scripts/create_triaje_config_tables.py --activar --piloto 5491161461034   # activa solo para ese teléfono
  python scripts/create_triaje_config_tables.py --activar --piloto ""              # activa para todos
  python scripts/create_triaje_config_tables.py --desactivar                       # kill-switch por dato
  python scripts/create_triaje_config_tables.py --estado                           # muestra config + videos
"""
import sys, argparse, json, psycopg2
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

BUCKET = "https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos"

# ---- Textos (BORRADOR editable por UPDATE). Chequeados contra el Banlist vivo por tests/test_triaje_textos_banlist.py ----
TEXTOS = {
    "texto_escalada": "Recibimos su mensaje. Le pasamos a la Dra. Raquel para que le coordine lo antes posible.",
    "texto_cierre": "Buenísimo, gracias por avisar. Si vuelve a molestar, escríbanos por acá.",
}
SALIDA_OP1 = "Si con eso no alcanza, respóndame \"no me sirvió\" y le mando la Opción 2. Si el dolor es fuerte o hay sangrado, avíseme y le paso a la doctora."
SALIDA_OP2 = "Si tampoco funciona o le sigue doliendo, respóndame por acá y le paso a la Dra. Raquel para coordinar un control."
SALIDA_GENERICA = "Si no mejora, si el dolor es fuerte o hay sangrado, respóndame por acá y le paso a la doctora."

SEEDS_VIDEOS = [
    dict(tipo="alambre_pincha", opcion=1, titulo="Opción 1 — cera de ortodoncia",
         url=f"{BUCKET}/alambre_pincha/opcion1.mp4", filename="alambre_pincha_opcion1.mp4",
         caption="Hola! Soy Asiri, la secretaria virtual de la Dra. Raquel 🤗 Le envío un video con la Opción 1 para aliviar la molestia hasta coordinar un control: colocar cera de ortodoncia en la punta del alambre que pincha, como muestra el video.",
         pregunta_guiada="Para ayudarle mejor: ¿lo que pincha es el alambre principal (el que pasa por todos los brackets) que se salió del tubo de atrás, o es un alambrecito finito de un solo bracket? Respóndame con sus palabras.",
         texto_salida_emergencia=SALIDA_OP1, activo=True, tamano_bytes=3901390),
    dict(tipo="alambre_pincha", opcion=2, titulo="Opción 2 — reinsertar con pinza",
         url=f"{BUCKET}/alambre_pincha/opcion2.mp4", filename="alambre_pincha_opcion2.mp4",
         caption="Opción 2: intentar volver a colocar el alambre en el tubo o bracket de donde se soltó, con ayuda de una pinza de alicate o de cejas, como muestra el video.",
         pregunta_guiada=None, texto_salida_emergencia=SALIDA_OP2, activo=True, tamano_bytes=5143460),
    dict(tipo="bracket_suelto", opcion=1, titulo="Opción 1 (video pendiente de la Dra.)", url=None, filename=None,
         caption="[PENDIENTE] Caption a definir cuando llegue el video.", pregunta_guiada=None,
         texto_salida_emergencia=SALIDA_GENERICA, activo=False, tamano_bytes=None),
    dict(tipo="alambre_girado", opcion=1, titulo="Opción 1 (video pendiente de la Dra.)", url=None, filename=None,
         caption="[PENDIENTE] Caption a definir cuando llegue el video.", pregunta_guiada=None,
         texto_salida_emergencia=SALIDA_GENERICA, activo=False, tamano_bytes=None),
    dict(tipo="ligadura_pincha", opcion=1, titulo="Opción 1 (video pendiente de la Dra.)", url=None, filename=None,
         caption="[PENDIENTE] Caption a definir cuando llegue el video.", pregunta_guiada=None,
         texto_salida_emergencia=SALIDA_GENERICA, activo=False, tamano_bytes=None),
]

DDL = """
CREATE TABLE IF NOT EXISTS public.triaje_config (
  id                    smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  activo                boolean NOT NULL DEFAULT false,       -- kill-switch maestro: false => todo escala como hoy
  modo                  text NOT NULL DEFAULT 'piloto' CHECK (modo IN ('sombra','piloto','live')),
  telefonos_piloto      text[] NOT NULL DEFAULT '{}',         -- allow-list; vacío = todos los pacientes
  red_flags_extra       text[] NOT NULL DEFAULT '{}',         -- regex extra (flags iu) sumadas al gate determinístico
  regex_no_sirvio       text,                                 -- NULL = default del nodo Evaluar
  regex_cierre          text,
  regex_nuevo_problema  text,
  regex_aparato         text,
  texto_escalada        text NOT NULL,                        -- canned al paciente ANTES de escalar (siempre)
  texto_cierre          text NOT NULL,                        -- canned cuando dice "listo / gracias"
  aviso_pasivo          boolean NOT NULL DEFAULT false,       -- fila en escalaciones_log (origen triaje_video) por video enviado
  ttl_video_seg         integer NOT NULL DEFAULT 7200,
  ttl_pregunta_seg      integer NOT NULL DEFAULT 1800,
  modelo                text NOT NULL DEFAULT 'gpt-5-mini',
  updated_at            timestamptz NOT NULL DEFAULT now(),
  updated_by            text
);

CREATE TABLE IF NOT EXISTS public.triaje_videos (
  id                      bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  tipo                    text NOT NULL CHECK (tipo ~ '^[a-z_]+$'),
  opcion                  smallint NOT NULL CHECK (opcion BETWEEN 1 AND 9),
  titulo                  text NOT NULL,
  url                     text CHECK (url IS NULL OR url ~ '^https://'),
  filename                text,
  caption                 text NOT NULL,                      -- canned; NUNCA LLM
  pregunta_guiada         text,                               -- solo se usa de la fila opcion=1; NULL = sin pregunta
  texto_salida_emergencia text NOT NULL,                      -- 2º mensaje tras el video
  activo                  boolean NOT NULL DEFAULT false,
  tamano_bytes            bigint,
  updated_at              timestamptz NOT NULL DEFAULT now(),
  updated_by              text,
  CONSTRAINT triaje_videos_tipo_opcion_uq UNIQUE (tipo, opcion),
  CONSTRAINT triaje_videos_activo_con_url CHECK (activo = false OR url IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_triaje_videos_tipo ON public.triaje_videos (tipo, opcion);

ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS opcion_enviada  smallint;
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS chat_history_id bigint;
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS resuelto_at     timestamptz;
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS razon_cierre    text;
CREATE INDEX IF NOT EXISTS idx_triaje_telefono_created ON public.triaje_urgencias_log (telefono, created_at DESC);
"""

def connect():
    db = load_env(".env", {"SUPABASE_DB_HOST","SUPABASE_DB_PORT","SUPABASE_DB_NAME","SUPABASE_DB_USER","SUPABASE_DB_PASSWORD"})
    conn = psycopg2.connect(host=db["SUPABASE_DB_HOST"], port=db["SUPABASE_DB_PORT"], dbname=db["SUPABASE_DB_NAME"],
                            user=db["SUPABASE_DB_USER"], password=db["SUPABASE_DB_PASSWORD"], sslmode="require", connect_timeout=20)
    conn.autocommit = True
    return conn

def estado(cur):
    cur.execute("SELECT activo, modo, telefonos_piloto, aviso_pasivo, ttl_video_seg, ttl_pregunta_seg, modelo, updated_at, updated_by FROM triaje_config WHERE id=1")
    print("triaje_config:", cur.fetchone())
    cur.execute("SELECT tipo, opcion, activo, url IS NOT NULL AS tiene_url, left(caption, 60) FROM triaje_videos ORDER BY tipo, opcion")
    for r in cur.fetchall(): print("  ", r)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--activar", action="store_true")
    ap.add_argument("--desactivar", action="store_true")
    ap.add_argument("--piloto", default=None, help="teléfonos separados por coma; '' = todos")
    ap.add_argument("--estado", action="store_true")
    args = ap.parse_args()

    conn = connect(); cur = conn.cursor()
    if args.estado:
        estado(cur); return
    if args.activar or args.desactivar:
        if args.activar:
            tels = [] if args.piloto is None or args.piloto.strip() == "" else [t.strip() for t in args.piloto.split(",") if t.strip()]
            cur.execute("UPDATE triaje_config SET activo=true, telefonos_piloto=%s, updated_at=now(), updated_by='script' WHERE id=1", (tels,))
            print(f"activado (telefonos_piloto={tels or 'TODOS'})")
        else:
            cur.execute("UPDATE triaje_config SET activo=false, updated_at=now(), updated_by='script' WHERE id=1")
            print("desactivado (kill-switch por dato)")
        estado(cur); return

    if not args.apply:
        print(DDL); print("(preview — nada creado). Para aplicar: --apply"); return

    cur.execute(DDL)
    cur.execute("""INSERT INTO triaje_config (id, texto_escalada, texto_cierre, updated_by) VALUES (1, %s, %s, 'seed_fase2')
                   ON CONFLICT (id) DO NOTHING""", (TEXTOS["texto_escalada"], TEXTOS["texto_cierre"]))
    for s in SEEDS_VIDEOS:
        cur.execute("""INSERT INTO triaje_videos (tipo, opcion, titulo, url, filename, caption, pregunta_guiada, texto_salida_emergencia, activo, tamano_bytes, updated_by)
                       VALUES (%(tipo)s, %(opcion)s, %(titulo)s, %(url)s, %(filename)s, %(caption)s, %(pregunta_guiada)s, %(texto_salida_emergencia)s, %(activo)s, %(tamano_bytes)s, 'seed_fase2_borrador')
                       ON CONFLICT (tipo, opcion) DO NOTHING""", s)
    print("✅ tablas + seeds listos (triaje_config.activo=false hasta --activar)")
    estado(cur)
    cur.close(); conn.close()

if __name__ == "__main__":
    main()
