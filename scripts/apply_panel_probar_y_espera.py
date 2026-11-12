# -*- coding: utf-8 -*-
"""
apply_panel_probar_y_espera.py — 2026-11-12 · Opción A del panel (Lucas: "si", 12/11: "que se puedan ajustar desde el panel"):
  1. Mensajes fijos: los dos textos de la lista de espera (ESPERA, ESPERA_SIN_TURNO) pasan a ser editables desde el panel (v7/orquestador_core.js:
     TEXTOS + MENSAJES_EDITABLES; los arma clinica_core y el cerebro los reemplaza con aplicarMensajes). Test: tests/test_mensajes_panel_sync.mjs
     (mismos textos en clinica_core, orquestador_core y el panel).
  2. "v7 Panel - probar Información" (NUEVO, scripts/v7_workflow_panel_probar.py): el panel prueba el borrador de "Tono y estilo de las respuestas"
     contra el agente de Información real, en sombra, antes de guardar. Secreto = el de "Panel — acciones staff" (se lee de ese nodo vivo y no se imprime).
     Tests: tests/test_v7_panel_probar.py (27/27).
  Incluye lo de apply_info_datos.py (Información: horas y montos solo de los DATOS) porque agente_informacion se vuelve a desplegar acá.

Workflows que toca (VIVOS): los que llevan copia de orquestador_core — "v7 Cerebro", "v7 Cerebro Agente" (inactivo), los 4 agentes — y crea/activa
"v7 Panel - probar Información". NO toca la entrada O155, Recordatorios, el v6 ni "v6 Orquestador (sombra)" (inactivo; difiere del repo a propósito).
Diff COMPLETO por workflow (scripts/diff_vivo.py, con el secreto enmascarado) y cada PUT pasa por scripts/guarda_vivo.py.

USO:  python scripts/apply_panel_probar_y_espera.py                    # simulación: diffs contra lo vivo
      python scripts/apply_panel_probar_y_espera.py --apply            # check_triaje + backup PRE + PUT/crear + activar + verificación + backup POST + prueba de humo
      python scripts/apply_panel_probar_y_espera.py --probar           # solo la prueba de humo del webhook (secreto bueno → 200; malo → 401)
Vuelta atrás: scripts/restaurar_workflow.py con los backups PRE; el probador se apaga con POST /workflows/<id>/deactivate.
"""
import argparse, json, re, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crear_v7_en_n8n as D
import diff_vivo as V
import v7_workflow_panel_probar as P
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = D.ROOT
HIST = ROOT / "workflows" / "history"
CLAVES = ["agente_turnos", "agente_pagos", "agente_informacion", "agente_urgencias", "cerebro", "cerebro_agente"]
PANEL_STAFF = "jzxb5zUKCaJcvCgp"   # "Panel — acciones staff (send-human / toggle-bot)": su nodo "Validar secreto" tiene el secreto que usa el panel
CLAVE_PROBAR = "panel_probar"


def secreto_panel():
    wf = D.api(f"/workflows/{PANEL_STAFF}")
    nodo = next((n for n in wf["nodes"] if n["name"] == "Validar secreto"), None)
    m = re.search(r'const SECRET = "([^"]+)"', (nodo or {}).get("parameters", {}).get("jsCode", ""))
    if not m or m.group(1) in ("", P.SECRETO_PH):
        sys.exit("no encontré el secreto del panel en el nodo vivo 'Validar secreto' de " + PANEL_STAFF)
    return m.group(1)


def probador(ids, secreto):
    wf = V.generado(CLAVE_PROBAR, {**ids, CLAVE_PROBAR: ids.get(CLAVE_PROBAR, "")})
    for n in wf["nodes"]:
        if n["name"] == "Validar":
            assert n["parameters"]["jsCode"].count(f'const SECRET = "{P.SECRETO_PH}";') == 1
            n["parameters"]["jsCode"] = n["parameters"]["jsCode"].replace(f'const SECRET = "{P.SECRETO_PH}";', f'const SECRET = "{secreto}";')
    return wf


def llamar(secreto, body):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    req = urllib.request.Request(f"{base}/webhook/{P.RUTA}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Panel-Secret": secreto})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def prueba_de_humo(secreto):
    t0 = time.time()
    c, r = llamar(secreto, {"mensaje": "¿Atienden los sábados?", "notas": None})
    print(f"   humo (secreto bueno): {c} {json.dumps(r, ensure_ascii=False)[:300]}  ({time.time() - t0:.1f} s)")
    c2, _ = llamar("secreto-equivocado", {"mensaje": "hola", "notas": None})
    print(f"   humo (secreto malo):  {c2}")
    return c == 200 and isinstance(r, dict) and r.get("resultado") in ("responde", "deriva", "nada") and c2 == 401


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--probar", action="store_true")
    a = ap.parse_args()
    ids = json.loads(D.IDS.read_text(encoding="utf-8"))
    if a.probar:
        sys.exit(0 if prueba_de_humo(secreto_panel()) else "la prueba de humo falló")
    if a.apply:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_triaje.py")], capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:])
        if r.returncode != 0:
            sys.exit("check_triaje falló: no se aplica nada")
    ts = int(time.time())
    for k in CLAVES:
        wid = ids[k]
        vivo = D.api(f"/workflows/{wid}")
        nuevo = V.conservar_webhooks(vivo, V.generado(k, ids))
        assert nuevo["name"] == vivo["name"], f"{k}: el nombre no coincide ({nuevo['name']} vs {vivo['name']})"
        print(f"== {vivo['name']} ({wid}) activo={vivo.get('active')}")
        cambios, lineas = V.comparar(vivo, nuevo)
        for l in lineas:
            print(l)
        if not cambios:
            print("   (sin cambios: no se toca)"); continue
        if not a.apply:
            continue
        (HIST / f"{wid}_PRE_panel_espera_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
        D.api(f"/workflows/{wid}", "PUT", {"name": nuevo["name"], "nodes": nuevo["nodes"], "connections": nuevo["connections"],
                                            "settings": {k2: v for k2, v in (vivo.get("settings") or {}).items() if k2 in D.SETTINGS_OK}})
        post = D.api(f"/workflows/{wid}")
        (HIST / f"{wid}_POST_panel_espera_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
        ok = V.comparar(post, nuevo)[0] == 0 and post.get("active") == vivo.get("active")
        print(f"   {'ok' if ok else '¡NO COINCIDE!'} · activo={post.get('active')} · backups en workflows/history (*_{ts}.json)")
        if not ok:
            sys.exit("verificación falló: restaurar con el backup PRE")

    # ---- el probador del panel
    existentes = {w["name"]: w["id"] for w in D.api("/workflows?limit=250")["data"]}
    wid = ids.get(CLAVE_PROBAR) or existentes.get(P.NOMBRE)
    secreto = secreto_panel() if a.apply else P.SECRETO_PH
    nuevo = probador(ids, secreto)
    print(f"== {P.NOMBRE} ({wid or 'NUEVO'})")
    if wid:
        vivo = D.api(f"/workflows/{wid}")
        nuevo = V.conservar_webhooks(vivo, nuevo)
        cambios, lineas = V.comparar(vivo, nuevo)
        for l in lineas:
            print(l)
    else:
        cambios = 1
        print(f"   + se crea: webhook POST /webhook/{P.RUTA} → Validar → Datos del consultorio → Armar → Información (sombra) → Responder → respuesta al panel")
    if not a.apply:
        print("\n(simulación: nada se cambió. --apply con \"desplegá\" de Lucas)")
        return
    cuerpo = {"name": nuevo["name"], "nodes": nuevo["nodes"], "connections": nuevo["connections"], "settings": {k2: v for k2, v in (nuevo.get("settings") or {}).items() if k2 in D.SETTINGS_OK}}
    if wid and cambios:
        (HIST / f"{wid}_PRE_panel_espera_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
        D.api(f"/workflows/{wid}", "PUT", cuerpo)
    elif not wid:
        wid = D.api("/workflows", "POST", cuerpo)["id"]
        ids[CLAVE_PROBAR] = wid
        D.IDS.write_text(json.dumps(ids, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"   creado {wid} (guardado en v7/ids.json)")
    if not D.api(f"/workflows/{wid}").get("active"):
        D.api(f"/workflows/{wid}/activate", "POST", {})
    post = D.api(f"/workflows/{wid}")
    (HIST / f"{wid}_POST_panel_espera_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
    val = next(n for n in post["nodes"] if n["name"] == "Validar")["parameters"]["jsCode"]
    ok = V.comparar(post, nuevo)[0] == 0 and post.get("active") is True and f'const SECRET = "{secreto}";' in val
    print(f"   {'ok' if ok else '¡NO COINCIDE!'} · activo={post.get('active')} · secreto del panel {'puesto' if f'const SECRET = \"{secreto}\";' in val else 'FALTA'}")
    if not ok:
        sys.exit("verificación del probador falló")
    if not prueba_de_humo(secreto):
        sys.exit("la prueba de humo del probador falló: revisar la ejecución en n8n")
    print("\nListo. Commit + push de workflows/vivo_huellas.json y v7/ids.json. Después, el panel: bash deploy/redeploy.sh (Lucas).")


if __name__ == "__main__":
    main()
