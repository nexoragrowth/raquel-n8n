# -*- coding: utf-8 -*-
"""
upload_urgencia_video_supabase.py — Sube un video de triaje de urgencias al bucket
público `urgencias-videos` de Supabase Storage (v3) y devuelve la URL pública.
Opcionalmente manda ese video por Evolution GO (POST /send/media con `url` https)
a un número de prueba, para verificar el path REAL de producción de punta a punta.

Decisión de hosting (2026-09-02): Supabase Storage público, n8n solo pasa la URL.
`/send/media` acepta base64 y URL https (ambos verificados en vivo); URL evita leer
y codificar 4-5MB dentro de n8n en cada envío.

Uso:
  python scripts/upload_urgencia_video_supabase.py "<ruta mp4>" "<path en bucket>" [--send <numero>] [--caption "<texto>"]
Ej:
  python scripts/upload_urgencia_video_supabase.py "C:/.../video.mp4" "alambre_pincha/opcion1.mp4" --send 5491161461034
"""
import json, os, sys, argparse, urllib.request, urllib.error
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

def load_env(path):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env(".env")
load_env("panel/.env.local")

SB_URL = (os.environ.get("V3_SUPABASE_URL") or "").rstrip("/")
SB_KEY = os.environ.get("V3_SUPABASE_SERVICE_KEY") or ""
BUCKET = "urgencias-videos"

ap = argparse.ArgumentParser()
ap.add_argument("video")
ap.add_argument("dest_path")
ap.add_argument("--send", default=None)
ap.add_argument("--caption", default="[TEST] video servido desde Supabase Storage")
args = ap.parse_args()

if not SB_URL or not SB_KEY:
    print("Faltan V3_SUPABASE_URL / V3_SUPABASE_SERVICE_KEY (no se imprimen valores)")
    sys.exit(1)

H = {"Authorization": f"Bearer {SB_KEY}", "apikey": SB_KEY}

def req(method, url, data=None, headers=None, timeout=60):
    h = dict(H)
    if headers:
        h.update(headers)
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

# 1) bucket público (idempotente)
st, body = req("GET", f"{SB_URL}/storage/v1/bucket/{BUCKET}")
if st == 200:
    print(f"bucket '{BUCKET}' ya existe (public={json.loads(body).get('public')})")
else:
    st, body = req("POST", f"{SB_URL}/storage/v1/bucket",
                   data=json.dumps({"id": BUCKET, "name": BUCKET, "public": True}).encode(),
                   headers={"Content-Type": "application/json"})
    print(f"crear bucket -> HTTP {st}: {body[:200]}")
    if st not in (200, 201):
        sys.exit(1)

# 2) upload (upsert)
video = Path(args.video)
data = video.read_bytes()
st, body = req("POST", f"{SB_URL}/storage/v1/object/{BUCKET}/{args.dest_path}", data=data,
               headers={"Content-Type": "video/mp4", "x-upsert": "true"}, timeout=180)
print(f"upload {video.name} ({len(data)} bytes) -> {args.dest_path}: HTTP {st}: {body[:200]}")
if st not in (200, 201):
    sys.exit(1)

public_url = f"{SB_URL}/storage/v1/object/public/{BUCKET}/{args.dest_path}"
print("URL pública:", public_url)

# 3) verificar que la URL sirve el archivo (HEAD)
r = urllib.request.Request(public_url, method="HEAD")
with urllib.request.urlopen(r, timeout=30) as resp:
    print(f"HEAD URL pública -> {resp.status}, content-type={resp.headers.get('Content-Type')}, len={resp.headers.get('Content-Length')}")

# 4) opcional: enviar por Evolution GO usando la URL (path real de producción)
if args.send:
    N8N_BASE = (os.environ.get("N8N_API_BASE") or os.environ.get("N8N_BASE_URL") or "").rstrip("/")
    N8N_KEY = os.environ.get("N8N_API_KEY") or ""
    r = urllib.request.Request(f"{N8N_BASE}/api/v1/workflows/O155MqHgOSaNZ9ye", headers={"X-N8N-API-KEY": N8N_KEY})
    with urllib.request.urlopen(r, timeout=20) as resp:
        wf = json.loads(resp.read().decode())
    node = next(n for n in wf["nodes"] if n.get("name") == "Evolution API - Enviar Mensaje")
    params = node["parameters"]
    apikey = next(h["value"] for h in params["headerParameters"]["parameters"] if h["name"].lower() == "apikey")
    evo_base = params["url"].split("/send/")[0]
    payload = {"number": args.send, "type": "video", "url": public_url,
               "caption": args.caption, "filename": video.name}
    r = urllib.request.Request(f"{evo_base}/send/media", data=json.dumps(payload).encode(), method="POST",
                               headers={"apikey": apikey, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            out = json.loads(resp.read().decode())
            print(f"send/media -> HTTP {resp.status}, Type={out.get('data', {}).get('Info', {}).get('Type')}, ID={out.get('data', {}).get('Info', {}).get('ID')}")
    except urllib.error.HTTPError as e:
        print(f"send/media FAILED HTTP {e.code}: {e.read().decode()[:300]}")
