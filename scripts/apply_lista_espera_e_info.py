# -*- coding: utf-8 -*-
"""
apply_lista_espera_e_info.py — 2026-11-12 · dos arreglos del espejo con mensajes reales (casos r017 y r007), pedidos por Lucas ("sí", 12/11):
  1. Lista de espera SIN turno (r017: "no se olviden de mí, si hace falta agendo una consulta"): el agente lo anotaba como "quiere adelantar su turno" y al
     grupo le iba un FYI falso. Ahora, sin turno vigente y sin haber visto horarios, el código no anota nada y le pide al agente buscar_horarios. Si ya vio
     horarios (o Asiri le ofreció anotarlo porque no había lugar), se anota con texto y FYI que no hablan de "su turno".
     (v7/clinica_core.js; tests C4b–C4g en tests/test_historial_clinica_core.mjs; la herramienta lista_espera de Turnos ahora le pasa turnos_json y ultimo_asiri)
  2. Información (r007: "esta tarde hasta qué hora está la doctora", jueves): aclara que en ese día o franja no hay atención. Probado con el modelo real
     (gpt-5-mini, entrada exacta de la ejecución 338823), 8 corridas por caso: "a la tarde" 16/16 vs 9/16 del prompt anterior; horarios generales, sábados,
     "¿hasta qué hora hoy?", "mañana a la mañana" y precio sin cambios. Dos redacciones anteriores se descartaron (repetían la fecha y la hora, o copiaban
     "en este momento no hay atención" con el consultorio abierto).

Workflows que toca (VIVOS): "v7 Tool - clinica", "v7 Agente Turnos" (descripción y campos de lista_espera) y "v7 Agente Informacion" (prompt).
No toca el cerebro, la entrada, Recordatorios ni el v6. Diff COMPLETO (scripts/diff_vivo.py) y cada PUT pasa por scripts/guarda_vivo.py.

USO:  python scripts/apply_lista_espera_e_info.py            # simulación: diff contra lo vivo
      python scripts/apply_lista_espera_e_info.py --apply    # check_triaje + backup PRE + PUT + verificación + backup POST
Vuelta atrás: scripts/restaurar_workflow.py con el backup PRE.
"""
import argparse, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crear_v7_en_n8n as D
import diff_vivo as V

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = D.ROOT
HIST = ROOT / "workflows" / "history"
CLAVES = ["clinica", "agente_turnos", "agente_informacion"]


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
        (HIST / f"{wid}_PRE_lista_espera_info_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
        D.api(f"/workflows/{wid}", "PUT", {"name": nuevo["name"], "nodes": nuevo["nodes"], "connections": nuevo["connections"],
                                            "settings": {k2: v for k2, v in (vivo.get("settings") or {}).items() if k2 in D.SETTINGS_OK}})
        post = D.api(f"/workflows/{wid}")
        (HIST / f"{wid}_POST_lista_espera_info_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
        ok = V.comparar(post, nuevo)[0] == 0 and post.get("active") == vivo.get("active")
        print(f"   {'ok' if ok else '¡NO COINCIDE!'} · activo={post.get('active')} · backups en workflows/history (*_{ts}.json)")
        if not ok:
            sys.exit("verificación falló: restaurar con el backup PRE")
    if not apply:
        print("\n(simulación: nada se cambió. --apply con OK de Lucas)")


if __name__ == "__main__":
    main()
