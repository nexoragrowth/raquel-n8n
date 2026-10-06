# -*- coding: utf-8 -*-
"""
probar_v7.py — prueba el v7 DENTRO de n8n (ejecución real de los nodos), siempre en MODO SOMBRA salvo que se pida otra cosa a mano:
las lecturas a la agenda son reales; las escrituras, avisos y la memoria están simulados por código. No manda nada por WhatsApp.

  python scripts/probar_v7.py --activar                       # activa SOLO el webhook de prueba (ruta secreta en data/)
  python scripts/probar_v7.py --destino cerebro --campo phone=5491161461034 --campo texto="Hola" --campo modo=sombra
  python scripts/probar_v7.py --destino ver_turnos --campo tel=5491161461034 --campo exec_id_actual=t1
  python scripts/probar_v7.py --desactivar                    # lo apaga (hacelo siempre al terminar)
  python scripts/probar_v7.py --estado
"""
import argparse, json, sys, time, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
IDS = json.loads((ROOT / "v7" / "ids.json").read_text(encoding="utf-8"))
RUTA = (ROOT / "data" / "v7_test_ruta.txt").read_text(encoding="utf-8").strip()


def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method, headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--activar-subs", action="store_true"); ap.add_argument("--activar", action="store_true"); ap.add_argument("--desactivar", action="store_true"); ap.add_argument("--estado", action="store_true")
    ap.add_argument("--destino"); ap.add_argument("--campo", action="append", default=[]); ap.add_argument("--archivo")
    a = ap.parse_args()
    wid = IDS["test"]
    if a.activar_subs:
        for k, v in IDS.items():
            if k != "test":
                api(f"/workflows/{v}/activate", "POST")
        print("herramientas y cerebro ACTIVOS (n8n lo exige para ejecutarlos; no tienen ningún disparador externo)"); return
    if a.activar:
        api(f"/workflows/{wid}/activate", "POST"); print("webhook de prueba ACTIVO (acordate de --desactivar)"); return
    if a.desactivar:
        api(f"/workflows/{wid}/deactivate", "POST"); print("webhook de prueba INACTIVO"); return
    if a.estado:
        print({k: api(f"/workflows/{v}").get("active") for k, v in IDS.items()}); return
    body = json.loads(Path(a.archivo).read_text(encoding="utf-8")) if a.archivo else {}
    for kv in a.campo:
        k, v = kv.split("=", 1); body[k] = v
    if a.destino:
        body["destino"] = a.destino
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    req = urllib.request.Request(f"{base}/webhook/{RUTA}", data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=170) as r:
            txt = r.read().decode()
    except urllib.error.HTTPError as e:
        txt = f"HTTP {e.code}: " + e.read().decode()[:1500]
    print(f"({time.time() - t0:.1f} s)")
    try:
        print(json.dumps(json.loads(txt), ensure_ascii=False, indent=1))
    except Exception:
        print(txt[:3000])


if __name__ == "__main__":
    main()
