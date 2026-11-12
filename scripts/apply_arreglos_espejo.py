# -*- coding: utf-8 -*-
"""
apply_arreglos_espejo.py — 2026-11-12 · lleva al bot VIVO dos arreglos encontrados comparando con mensajes reales (espejo del Cerebro Agente):
  1. "No veo turnos vigentes con este número de celular." salía DEBAJO de los horarios libres a pacientes que pedían turno ("Quería saber si tiene
     turno para el viernes"): el sub-agente Turnos a veces lo entiende como "¿tengo turno?". Con horarios ofrecidos y sin turnos propios, ya no va.
     (v7/orquestador_core.js · salidaTurnos; test T6b–T6d en tests/test_orquestador_core.mjs)
  2. (11/11, commit 8da9c9d) chequeo de salida: "jueves 8:00" es horario de atención, no "el jueves 8" (frenaba respuestas correctas de Información).

Workflows que toca (VIVOS): "v7 Cerebro" y los 4 agentes (Turnos, Pagos, Informacion, Urgencias): todos llevan una copia de orquestador_core.js
(los 3 últimos no usan salidaTurnos, pero sin desplegarlos quedaban distintos del repo). No toca la entrada, las herramientas, Recordatorios ni el v6.
(12/11) El diff es COMPLETO (scripts/diff_vivo.py: código, prompts, descripciones, credenciales, conexiones) y cada PUT pasa por
scripts/guarda_vivo.py (frena si n8n cambió por fuera de este repo).

USO:  python scripts/apply_arreglos_espejo.py            # simulación: diff contra lo vivo
      python scripts/apply_arreglos_espejo.py --apply    # check_triaje + backup PRE + PUT + verificación + backup POST
Regla del proyecto: --apply solo con OK ("desplegá") de Lucas. Vuelta atrás: scripts/restaurar_workflow.py con el backup PRE.
"""
import argparse, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crear_v7_en_n8n as D
import diff_vivo as V

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = D.ROOT
HIST = ROOT / "workflows" / "history"
CLAVES = ["agente_turnos", "agente_pagos", "agente_informacion", "agente_urgencias", "cerebro"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    apply = ap.parse_args().apply
    ids = json.loads(D.IDS.read_text(encoding="utf-8"))
    if apply:
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
        if not apply:
            continue
        (HIST / f"{wid}_PRE_arreglos_espejo_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
        D.api(f"/workflows/{wid}", "PUT", {"name": nuevo["name"], "nodes": nuevo["nodes"], "connections": nuevo["connections"],
                                            "settings": {k2: v for k2, v in (vivo.get("settings") or {}).items() if k2 in D.SETTINGS_OK}})
        post = D.api(f"/workflows/{wid}")
        (HIST / f"{wid}_POST_arreglos_espejo_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
        ok = V.comparar(post, nuevo)[0] == 0 and post.get("active") == vivo.get("active")
        print(f"   {'ok' if ok else '¡NO COINCIDE!'} · activo={post.get('active')} · backups en workflows/history (*_{ts}.json)")
        if not ok:
            sys.exit("verificación falló: restaurar con el backup PRE")
    if not apply:
        print("\n(simulación: nada se cambió. --apply con OK de Lucas)")


if __name__ == "__main__":
    main()
