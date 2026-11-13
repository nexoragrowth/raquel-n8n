# -*- coding: utf-8 -*-
"""
apply_mensaje_mixto.py — 2026-11-13 · Lucas aprobó el texto ("y si mandale", 13/11). Mensaje que va a la secretaria Y trae una parte de Turnos
(horarios, lista de espera): antes salía "Le paso con la secretaria para que lo atienda." ARRIBA y los horarios abajo (se leía contradictorio; 3 casos
reales del 02/11 al 13/11). Ahora: primero lo de Turnos y al final "Lo demás se lo paso a la secretaria, que le responde por acá." (TEXTOS.DERIVA_RESTO).
Con un read-back ("¿Procedo…?") queda como antes: la pregunta va al final. Si la derivación la pidió Turnos (turno a < 48 h) también queda como antes.
v7/orquestador_core.js (componer). Tests: tests/test_orquestador_core.mjs CU1b, MX1–MX5.

Workflows que toca (VIVOS): los que llevan copia de orquestador_core — "v7 Cerebro", "v7 Cerebro Agente" (inactivo), los 4 agentes y "v7 Panel - probar
Información" (con el secreto del panel, que se lee del nodo vivo y no se imprime). NO toca la entrada O155, Recordatorios, el v6 ni "v6 Orquestador
(sombra)". Diff COMPLETO por workflow (scripts/diff_vivo.py) y cada PUT pasa por scripts/guarda_vivo.py (vía crear_v7_en_n8n.api).

USO:  python scripts/apply_mensaje_mixto.py            # simulación: diffs contra lo vivo
      python scripts/apply_mensaje_mixto.py --apply    # check_triaje + backup PRE + PUT + verificación + backup POST + humo del probador
Vuelta atrás: scripts/restaurar_workflow.py con los backups PRE (workflows/history/*_PRE_mensaje_mixto_<ts>.json).
"""
import argparse, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crear_v7_en_n8n as D
import diff_vivo as V
import apply_panel_probar_y_espera as PP

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = D.ROOT
HIST = ROOT / "workflows" / "history"
CLAVES = ["agente_turnos", "agente_pagos", "agente_informacion", "agente_urgencias", "cerebro", "cerebro_agente", "panel_probar"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ids = json.loads(D.IDS.read_text(encoding="utf-8"))
    if a.apply:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_triaje.py")], capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:])
        if r.returncode != 0:
            sys.exit("check_triaje falló: no se aplica nada")
    secreto = PP.secreto_panel()   # se lee siempre (también en la simulación) para que el diff del probador sea solo el cambio buscado; nunca se imprime
    ts = int(time.time())
    for k in CLAVES:
        wid = ids[k]
        vivo = D.api(f"/workflows/{wid}")
        nuevo = V.conservar_webhooks(vivo, PP.probador(ids, secreto) if k == "panel_probar" else V.generado(k, ids))
        assert nuevo["name"] == vivo["name"], f"{k}: el nombre no coincide ({nuevo['name']} vs {vivo['name']})"
        print(f"== {vivo['name']} ({wid}) activo={vivo.get('active')}")
        cambios, lineas = V.comparar(vivo, nuevo)
        for l in lineas:
            print(l.replace(secreto, "«secreto»") if secreto else l)
        if not cambios:
            print("   (sin cambios: no se toca)"); continue
        if not a.apply:
            continue
        (HIST / f"{wid}_PRE_mensaje_mixto_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
        D.api(f"/workflows/{wid}", "PUT", {"name": nuevo["name"], "nodes": nuevo["nodes"], "connections": nuevo["connections"],
                                            "settings": {k2: v for k2, v in (vivo.get("settings") or {}).items() if k2 in D.SETTINGS_OK}})
        post = D.api(f"/workflows/{wid}")
        (HIST / f"{wid}_POST_mensaje_mixto_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
        ok = V.comparar(post, nuevo)[0] == 0 and post.get("active") == vivo.get("active")
        print(f"   {'ok' if ok else '¡NO COINCIDE!'} · activo={post.get('active')} · backups en workflows/history (*_{ts}.json)")
        if not ok:
            sys.exit("verificación falló: restaurar con el backup PRE")
    if not a.apply:
        print("\n(simulación: nada se cambió. --apply con \"desplegá\" de Lucas)")
        return
    if not PP.prueba_de_humo(secreto):
        sys.exit("la prueba de humo del probador falló: revisar la ejecución en n8n")
    print("\nListo. Commit + push de workflows/vivo_huellas.json. Después: sombra del caso mixto (tests/comparativa) y limpieza.")


if __name__ == "__main__":
    main()
