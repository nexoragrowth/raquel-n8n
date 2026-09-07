# -*- coding: utf-8 -*-
"""
create_media_entrantes.py — infraestructura en Supabase v3 para los adjuntos del paciente:

  1. Bucket PRIVADO `pacientes-media` en Storage (public=false, file_size_limit 50 MB, sin restricción de mime).
     Son fotos de bocas y comprobantes: NUNCA público. El panel genera URLs firmadas (1 h) con la service key.
  2. Tabla `public.media_entrantes` (una fila por archivo; `id` de 16 hex es lo que viaja en el marcador
     ' [MEDIA:<id>]' del texto que va a la memoria) + índices (key_id; telefono, created_at).
  3. RLS habilitado SIN policies (solo service_role llega, como el resto del v3).
  4. Tabla agregada a la publicación `supabase_realtime` (INSERT -> el panel refetchea el chat al instante).

Storage se toca por la API REST con la service key (V3_SUPABASE_URL / V3_SUPABASE_SERVICE_KEY del .env.local del
panel, como upload_urgencia_video_supabase.py; fallback SUPABASE_V3_URL / SUPABASE_V3_SERVICE_ROLE_KEY del .env).
La base se toca por psycopg2 con SUPABASE_DB_* del .env de este repo (apuntan al v3). Nada se imprime.

Aditivo e idempotente (IF NOT EXISTS / chequeo previo). No toca ninguna tabla ni bucket existente que no sea este.
El v6 lo escribe con `scripts/apply_media_entrantes.py` (nodos "Media: *"); DDL documentado en rebuild_v3_schema.sql §12.

Uso:
  python scripts/create_media_entrantes.py            # preview: qué haría (solo lecturas)
  python scripts/create_media_entrantes.py --apply    # crea/ajusta bucket + tabla + índices + RLS + publicación
  python scripts/create_media_entrantes.py --estado   # muestra el estado real; exit 0 si todo está OK, 1 si falta algo
"""
import argparse, json, sys, urllib.error, urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
BUCKET = "pacientes-media"
TABLA = "media_entrantes"
FILE_SIZE_LIMIT = 50 * 1024 * 1024
INDICES = {"idx_media_entrantes_key_id": f"CREATE INDEX IF NOT EXISTS idx_media_entrantes_key_id ON public.{TABLA} (key_id)",
           "idx_media_entrantes_tel_created": f"CREATE INDEX IF NOT EXISTS idx_media_entrantes_tel_created ON public.{TABLA} (telefono, created_at DESC)"}

DDL = f"""
CREATE TABLE IF NOT EXISTS public.{TABLA} (
    id         TEXT PRIMARY KEY CHECK (id ~ '^[0-9a-f]{{16}}$'),   -- aleatorio, no adivinable; viaja en ' [MEDIA:<id>]'
    key_id     TEXT,                                                -- Info.ID del mensaje de WhatsApp (une con mensajes_entrantes_live)
    telefono   TEXT NOT NULL,                                       -- = Extraer Datos.phone tal cual (mismo valor que mensajes_entrantes_live.telefono / session_id)
    from_me    BOOLEAN NOT NULL DEFAULT false,                      -- true = lo mandó el consultorio (fuera de alcance hoy)
    tipo       TEXT NOT NULL CHECK (tipo IN ('image','video','audio','document','sticker')),
    mime       TEXT,                                                -- normalizado (sin '; codecs=…'), corregido por magic bytes
    bucket     TEXT NOT NULL DEFAULT '{BUCKET}',
    path       TEXT NOT NULL,                                       -- <telefono>/<yyyy>/<mm>/<id>.<ext>
    bytes      INTEGER,
    filename   TEXT,                                                -- original (documentos) o <id>.<ext>
    caption    TEXT,                                                -- texto que acompañó al adjunto
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
{INDICES["idx_media_entrantes_key_id"]};
{INDICES["idx_media_entrantes_tel_created"]};
ALTER TABLE public.{TABLA} ENABLE ROW LEVEL SECURITY;
"""

# ---------------- env (sin imprimir valores) ----------------
def load_env(path, keys):
    out = {}
    p = Path(path)
    if not p.exists(): return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1); v = v.strip().strip('"').strip("'")
        if k in keys and v: out[k] = v
    return out

def storage_creds():
    for path in (ROOT / "panel" / ".env.local", ROOT.parent / "nexora-whatsapp-agent" / ".env.local"):
        e = load_env(path, {"V3_SUPABASE_URL", "V3_SUPABASE_SERVICE_KEY"})
        if e.get("V3_SUPABASE_URL") and e.get("V3_SUPABASE_SERVICE_KEY"):
            return e["V3_SUPABASE_URL"].rstrip("/"), e["V3_SUPABASE_SERVICE_KEY"], f"{path.name} del panel"
    e = load_env(ROOT / ".env", {"SUPABASE_V3_URL", "SUPABASE_V3_SERVICE_ROLE_KEY"})
    if e.get("SUPABASE_V3_URL") and e.get("SUPABASE_V3_SERVICE_ROLE_KEY"):
        return e["SUPABASE_V3_URL"].rstrip("/"), e["SUPABASE_V3_SERVICE_ROLE_KEY"], ".env de raquel-n8n"
    sys.exit("ERROR: faltan V3_SUPABASE_URL/V3_SUPABASE_SERVICE_KEY (panel) o SUPABASE_V3_URL/SUPABASE_V3_SERVICE_ROLE_KEY (.env)")

def db_conn():
    import psycopg2
    db = load_env(ROOT / ".env", {"SUPABASE_DB_HOST", "SUPABASE_DB_PORT", "SUPABASE_DB_NAME", "SUPABASE_DB_USER", "SUPABASE_DB_PASSWORD"})
    faltan = [k for k in ("SUPABASE_DB_HOST", "SUPABASE_DB_USER", "SUPABASE_DB_PASSWORD") if k not in db]
    if faltan: sys.exit(f"ERROR: faltan en .env: {faltan}")
    conn = psycopg2.connect(host=db["SUPABASE_DB_HOST"], port=db.get("SUPABASE_DB_PORT", "5432"), dbname=db.get("SUPABASE_DB_NAME", "postgres"),
                            user=db["SUPABASE_DB_USER"], password=db["SUPABASE_DB_PASSWORD"], sslmode="require", connect_timeout=20)
    conn.autocommit = True
    return conn

# ---------------- Storage ----------------
def req(url, key, method="GET", data=None, headers=None, timeout=60):
    h = {"Authorization": f"Bearer {key}", "apikey": key}
    if headers: h.update(headers)
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

def bucket_estado(sb_url, key):
    st, body = req(f"{sb_url}/storage/v1/bucket/{BUCKET}", key)
    if st == 200:
        b = json.loads(body)
        return {"existe": True, "public": bool(b.get("public")), "file_size_limit": b.get("file_size_limit"), "allowed_mime_types": b.get("allowed_mime_types")}
    return {"existe": False, "http": st}

def bucket_ok(est):
    return est.get("existe") and est.get("public") is False and (est.get("file_size_limit") in (None, FILE_SIZE_LIMIT)) and not est.get("allowed_mime_types")

def bucket_aplicar(sb_url, key, est):
    payload = {"public": False, "file_size_limit": FILE_SIZE_LIMIT, "allowed_mime_types": None}
    if not est["existe"]:
        st, body = req(f"{sb_url}/storage/v1/bucket", key, "POST", json.dumps({"id": BUCKET, "name": BUCKET, **payload}).encode(), {"Content-Type": "application/json"})
        print(f"  crear bucket {BUCKET!r} (privado, 50 MB) -> HTTP {st}: {body[:160]}")
        if st not in (200, 201): sys.exit("ERROR: no se pudo crear el bucket")
    elif not bucket_ok(est):
        st, body = req(f"{sb_url}/storage/v1/bucket/{BUCKET}", key, "PUT", json.dumps(payload).encode(), {"Content-Type": "application/json"})
        print(f"  ajustar bucket {BUCKET!r} a privado/50 MB -> HTTP {st}: {body[:160]}")
        if st != 200: sys.exit("ERROR: no se pudo ajustar el bucket")
    else:
        print(f"  bucket {BUCKET!r} ya está OK (privado, 50 MB)")

# ---------------- Base ----------------
def db_estado(cur):
    cur.execute("SELECT to_regclass(%s)", (f"public.{TABLA}",))
    existe = cur.fetchone()[0] is not None
    est = {"tabla": existe, "columnas": [], "indices": [], "rls": None, "policies": 0, "publicada": False}
    if existe:
        cur.execute("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", (TABLA,))
        est["columnas"] = [(c[0], c[1], c[2]) for c in cur.fetchall()]
        cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public' AND tablename=%s", (TABLA,))
        est["indices"] = sorted(r[0] for r in cur.fetchall())
        cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(%s)", (f"public.{TABLA}",))
        est["rls"] = bool(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename=%s", (TABLA,))
        est["policies"] = cur.fetchone()[0]
    cur.execute("SELECT 1 FROM pg_publication_tables WHERE pubname='supabase_realtime' AND schemaname='public' AND tablename=%s", (TABLA,))
    est["publicada"] = cur.fetchone() is not None
    return est

def db_ok(est):
    return est["tabla"] and est["rls"] is True and est["policies"] == 0 and est["publicada"] and all(i in est["indices"] for i in INDICES)

def db_aplicar(cur, est):
    if not est["tabla"]:
        cur.execute(DDL); print(f"  tabla {TABLA!r} creada (+2 índices, RLS on)")
    else:
        for nombre, sql in INDICES.items():
            if nombre not in est["indices"]: cur.execute(sql); print(f"  índice {nombre} creado")
        if est["rls"] is not True: cur.execute(f"ALTER TABLE public.{TABLA} ENABLE ROW LEVEL SECURITY"); print("  RLS habilitado")
        print(f"  tabla {TABLA!r} ya existía ({len(est['columnas'])} columnas)")
    if est["policies"]:
        print(f"  ⚠️ la tabla tiene {est['policies']} policies RLS — el resto del v3 no tiene ninguna; revisar a mano (no se tocan)")
    if not est["publicada"]:
        cur.execute(f"ALTER PUBLICATION supabase_realtime ADD TABLE public.{TABLA}"); print("  agregada a la publicación supabase_realtime")
    else:
        print("  ya estaba en la publicación supabase_realtime")

def mostrar(best, dest):
    print(f"bucket {BUCKET!r}: {json.dumps(best)}  -> {'OK' if bucket_ok(best) else 'FALTA/AJUSTAR'}")
    print(f"tabla {TABLA!r}: existe={dest['tabla']} columnas={len(dest['columnas'])} indices={dest['indices']} rls={dest['rls']} policies={dest['policies']} realtime={dest['publicada']}"
          f"  -> {'OK' if db_ok(dest) else 'FALTA/AJUSTAR'}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--estado", action="store_true")
    args = ap.parse_args()
    sb_url, key, fuente = storage_creds()
    print(f"Storage: {sb_url} (service key desde {fuente}) · Base: SUPABASE_DB_* del .env")
    best = bucket_estado(sb_url, key)
    conn = db_conn(); cur = conn.cursor()
    dest = db_estado(cur)
    mostrar(best, dest)
    if args.estado:
        ok = bucket_ok(best) and db_ok(dest)
        print("ESTADO:", "todo OK" if ok else "falta algo (correr --apply)")
        cur.close(); conn.close(); return 0 if ok else 1
    if not args.apply:
        print("\n(preview — no se creó nada). Haría:")
        if not bucket_ok(best): print(f"  - {'crear' if not best['existe'] else 'ajustar'} bucket privado {BUCKET!r} (50 MB, cualquier mime)")
        if not dest["tabla"]: print("  - DDL:" + DDL)
        else:
            for nombre in INDICES:
                if nombre not in dest["indices"]: print(f"  - crear índice {nombre}")
            if dest["rls"] is not True: print("  - habilitar RLS")
        if not dest["publicada"]: print(f"  - ALTER PUBLICATION supabase_realtime ADD TABLE public.{TABLA}")
        if bucket_ok(best) and db_ok(dest): print("  - nada: ya está todo")
        print("Para aplicar: --apply"); cur.close(); conn.close(); return 0
    print("\nAplicando:")
    bucket_aplicar(sb_url, key, best)
    db_aplicar(cur, dest)
    best2, dest2 = bucket_estado(sb_url, key), db_estado(cur)
    print("\nDespués:"); mostrar(best2, dest2)
    ok = bucket_ok(best2) and db_ok(dest2)
    print("✅ media_entrantes listo" if ok else "❌ revisar: algo no quedó como se esperaba")
    cur.close(); conn.close()
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
