# -*- coding: utf-8 -*-
"""
test_evo_go_send_video.py — Prueba de envío de VIDEO saliente por Evolution GO
(POST /send/media). Primera vez que se prueba envío de media saliente en este
proyecto (05/08 solo se resolvió recepción). Verificado 2026-09-02: funciona con
el video en BASE64 CRUDO (sin prefijo data:) en el campo `url`, `type: "video"`.

No hardcodea el apikey (el de scripts viejos de julio/agosto ya está vencido) —
lo extrae en caliente del nodo real "Evolution API - Enviar Mensaje" del v6 vivo,
vía la API de n8n. Nunca imprime el valor de la clave.

Uso: python scripts/test_evo_go_send_video.py "<ruta al mp4>" "<numero destino>" ["<caption>"]
"""
import json, base64, os, sys, urllib.request, urllib.error
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

for p in [".env", "panel/.env.local"]:
    ep = Path(p)
    if ep.exists():
        for line in ep.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

N8N_BASE = (os.environ.get("N8N_API_BASE") or os.environ.get("N8N_BASE_URL") or "").rstrip("/")
N8N_KEY = os.environ.get("N8N_API_KEY") or ""
V6_WORKFLOW_ID = "O155MqHgOSaNZ9ye"

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)

VIDEO_PATH = Path(sys.argv[1])
DEST_PHONE = sys.argv[2] if len(sys.argv) > 2 else "5491161461034"
CAPTION = sys.argv[3] if len(sys.argv) > 3 else "[TEST] Envío de video de prueba."

req = urllib.request.Request(
    f"{N8N_BASE}/api/v1/workflows/{V6_WORKFLOW_ID}",
    headers={"X-N8N-API-KEY": N8N_KEY},
)
with urllib.request.urlopen(req, timeout=20) as r:
    wf = json.loads(r.read().decode())

target = next((n for n in wf.get("nodes", []) if n.get("name") == "Evolution API - Enviar Mensaje"), None)
if not target:
    print('No encontré el nodo "Evolution API - Enviar Mensaje" en el v6 vivo.')
    sys.exit(1)

params = target.get("parameters", {})
apikey = next(
    (h.get("value") for h in params.get("headerParameters", {}).get("parameters", [])
     if h.get("name", "").lower() == "apikey"),
    None,
)
url_field = params.get("url", "")
base_url = url_field.split("/send/")[0].split("/message/")[0] if url_field else None

if not apikey or not base_url:
    print("No pude extraer apikey/base_url del nodo. Abortando sin exponer nada.")
    sys.exit(1)

video_bytes = VIDEO_PATH.read_bytes()
b64 = base64.b64encode(video_bytes).decode()
print(f"Video: {VIDEO_PATH.name} ({len(video_bytes)} bytes) -> {DEST_PHONE}")

body = {
    "number": DEST_PHONE,
    "type": "video",
    "url": b64,  # base64 crudo, SIN prefijo "data:video/mp4;base64,"
    "caption": CAPTION,
    "filename": VIDEO_PATH.name,
}
req = urllib.request.Request(
    f"{base_url}/send/media",
    data=json.dumps(body).encode(),
    method="POST",
    headers={"apikey": apikey, "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=40) as r:
        print(f"EXITO ({r.status}):", r.read().decode()[:500])
except urllib.error.HTTPError as e:
    print(f"FAILED HTTP {e.code}:", e.read().decode()[:500])
except Exception as e:
    print(f"FAILED: {e}")
