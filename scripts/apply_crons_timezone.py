# -*- coding: utf-8 -*-
"""
apply_crons_timezone.py — (2026-11-17) fija la zona horaria de los crons con hora fija.

Por qué: los crons no tenían `settings.timezone` y usaban la del servidor de n8n (Europa).
Con el horario de verano europeo (UTC+2) `0 13` caía 08:00 ART; desde el 25/10 (UTC+1)
cae 09:00 ART. El 17/11 la Dra. avisó que no habían salido los recordatorios a las 8 y la
secretaria los mandó a mano → doble mensaje a varios pacientes.

Qué cambia (SOLO esto; ningún otro nodo, conexión ni credencial):
  - settings.timezone = America/Argentina/Jujuy
  - expresión del cron, escrita en hora de Jujuy (la que corría con UTC+2):
      Recordatorios 48HS     0 13 * * 1-5  ->  0 8 * * 1-5   (08:00 lun-vie)
      Daily Summary          30 14 * * *   ->  30 9 * * *    (09:30 todos los días)
      Reportero Semanal      0 15 * * 1    ->  0 10 * * 1    (lunes 10:00)
Retención ya tiene timezone; los de cada 15/30 min no dependen de la hora.

USO:
    python scripts/apply_crons_timezone.py            # preview (no toca n8n)
    python scripts/apply_crons_timezone.py --apply    # backup PRE/POST + PUT + verificación
Regla del proyecto: NUNCA --apply sin OK explícito de Lucas.
"""
import argparse
import copy
import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import env, require  # noqa: E402

BASE = (env("N8N_BASE_URL") or "https://n8n.raquelrodriguez.com.ar").rstrip("/")
if BASE.endswith("/api/v1"):
    BASE = BASE[: -len("/api/v1")]
KEY = require("N8N_API_KEY")
TZ = "America/Argentina/Jujuy"

CAMBIOS = {
    # id: (cron actual esperado, cron nuevo)
    "7RqTApkvVavRmq3R": ("0 13 * * 1-5", "0 8 * * 1-5"),
    "QsGBGkZdGu5gTdBf": ("30 14 * * *", "30 9 * * *"),
    "MJ38kSTRZDPgPCCy": ("0 15 * * 1", "0 10 * * 1"),
}

PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}


def api(method, path, body=None):
    req = urllib.request.Request(
        f"{BASE}/api/v1{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json", "accept": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


import guarda_vivo  # noqa: E402  (12/11) freno: no pisar en n8n cambios que este repo no conoce
api = guarda_vivo.envolver(api)


def triggers(wf):
    return [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.scheduleTrigger" and not n.get("disabled")]


def preparar(wid, wf):
    viejo, nuevo = CAMBIOS[wid]
    ts = triggers(wf)
    if len(ts) != 1:
        sys.exit(f"!! {wf['name']}: esperaba 1 schedule trigger, hay {len(ts)}.")
    iv = ts[0]["parameters"]["rule"]["interval"]
    if len(iv) != 1 or iv[0].get("field") != "cronExpression":
        sys.exit(f"!! {wf['name']}: la regla no es un único cronExpression.")
    actual = iv[0]["expression"]
    tz_actual = (wf.get("settings") or {}).get("timezone")
    if actual == nuevo and tz_actual == TZ:
        return None
    if actual != viejo:
        sys.exit(f"!! {wf['name']}: cron vivo '{actual}' != esperado '{viejo}'. No toco nada.")
    iv[0]["expression"] = nuevo
    wf.setdefault("settings", {})["timezone"] = TZ
    return (ts[0]["name"], actual, nuevo, tz_actual)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    planes = []
    for wid in CAMBIOS:
        wf = api("GET", f"/workflows/{wid}")
        orig = copy.deepcopy(wf)
        cambio = preparar(wid, wf)
        print(f"\n== {wf['name']} ({wid}) activo={wf['active']}")
        if not cambio:
            print("   ya está aplicado, nada que hacer.")
            continue
        nodo, a, n, tz0 = cambio
        print(f"   nodo '{nodo}'")
        print(f"   - cron: {a}        (timezone: {tz0})")
        print(f"   + cron: {n}        (timezone: {TZ})")
        planes.append((wid, orig, wf))
    print("\nSin cambios de nodos, conexiones ni credenciales fuera de lo listado.")

    if not args.apply:
        print("\n(preview — no se tocó n8n). Para aplicar: --apply")
        return

    os.makedirs("workflows/history", exist_ok=True)
    sello = int(time.time())
    for wid, orig, wf in planes:
        pre = f"workflows/history/crons_tz_PRE_{wid}_{sello}.json"
        json.dump(orig, open(pre, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        body = {k: wf[k] for k in PUT_KEYS if k in wf}
        body["settings"] = {k: v for k, v in (wf.get("settings") or {}).items() if k in SETTINGS_OK}
        api("PUT", f"/workflows/{wid}", body)
        vivo = api("GET", f"/workflows/{wid}")
        post = f"workflows/history/crons_tz_POST_{wid}_{sello}.json"
        json.dump(vivo, open(post, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        expr = triggers(vivo)[0]["parameters"]["rule"]["interval"][0]["expression"]
        ok = expr == CAMBIOS[wid][1] and (vivo.get("settings") or {}).get("timezone") == TZ and vivo["active"] == orig["active"]
        print(f"   {vivo['name']}: cron={expr} tz={(vivo.get('settings') or {}).get('timezone')} activo={vivo['active']}  {'OK' if ok else '!! NO COINCIDE'}")
        print(f"      backups: {pre} / {post}")


if __name__ == "__main__":
    main()
