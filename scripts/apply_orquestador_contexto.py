# -*- coding: utf-8 -*-
"""
apply_orquestador_contexto.py — 2026-11-19 · caso real: paciente NUEVA dio nombre y DNI para reservar y el orquestador mandó el pedido a Turnos Y a la
secretaria ("Pasar a gestionar_turno con datos"). Turnos ya tenía el "¿Procedo con la reserva?"; el paciente recibió "Le paso con la secretaria…" pegado a esa
pregunta y la secretaria intervino. Pasó 1 vez en 75 mensajes reales (13–19/11), siempre con paciente nuevo.
Causas: (1) el contexto del orquestador traía instrucciones de herramientas que él no tiene ("pasalos a gestionar_turno") — venían del v7 de un solo agente;
(2) el único ejemplo de formato del prompt emparejaba turnos con derivar_secretaria.
Arreglo (cada regla en más de una capa):
  - historial_core.identidad/mensajeAgente(solo_hechos): el ORQUESTADOR recibe los mismos datos SIN instrucciones de herramientas (contexto_orq); los agentes
    siguen con el contexto de siempre (idéntico, OR9b/OR10b).
  - prompt_orquestador.md: ejemplo de un solo paso + formato de la derivación aparte (tamaño 3.542 < 3.550).
  - orquestador_core.despachar: si hay paso de Turnos y la derivación es por lo MISMO (turno/reserva/horario) sin nada que Asiri no atienda, se descarta;
    un nombre de herramienta nunca llega como motivo a la secretaria. componer: con un read-back, "Lo demás se lo paso a la secretaria…" y la pregunta al final.
Tests: test_orquestador_core.mjs OR1–OR10 (249/249), test_v7_cerebro.py Z18d (91/91), barrido offline verde. Sombra con el modelo real (clon en el espacio de
pruebas, restaurado): la conversación real con datos inventados ×3 → read-back limpio, sin derivación; queja + turno → la derivación se mantiene.

Workflows que toca (VIVOS): los 4 agentes (orquestador_core embebido), "v7 Cerebro", "v7 Cerebro Agente" (inactivo) y "v7 Panel - probar Información".
NO toca la entrada O155, Recordatorios, el v6 ni "v6 Orquestador (sombra)". Diff COMPLETO (scripts/diff_vivo.py); cada PUT pasa por scripts/guarda_vivo.py.

USO:  python scripts/apply_orquestador_contexto.py            # simulación: diffs contra lo vivo
      python scripts/apply_orquestador_contexto.py --apply    # check_triaje + backup PRE + PUT + verificación + backup POST + humo del probador
Vuelta atrás: scripts/restaurar_workflow.py con los backups PRE (workflows/history/*_PRE_orquestador_contexto_<ts>.json).
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
ETIQUETA = "orquestador_contexto"


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
        (HIST / f"{wid}_PRE_{ETIQUETA}_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
        D.api(f"/workflows/{wid}", "PUT", {"name": nuevo["name"], "nodes": nuevo["nodes"], "connections": nuevo["connections"],
                                            "settings": {k2: v for k2, v in (vivo.get("settings") or {}).items() if k2 in D.SETTINGS_OK}})
        post = D.api(f"/workflows/{wid}")
        (HIST / f"{wid}_POST_{ETIQUETA}_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
        ok = V.comparar(post, nuevo)[0] == 0 and post.get("active") == vivo.get("active")
        print(f"   {'ok' if ok else '¡NO COINCIDE!'} · activo={post.get('active')} · backups en workflows/history (*_{ts}.json)")
        if not ok:
            sys.exit("verificación falló: restaurar con el backup PRE")
    if not a.apply:
        print("\n(simulación: nada se cambió. --apply con \"desplegá\" de Lucas)")
        return
    if not PP.prueba_de_humo(secreto):
        sys.exit("la prueba de humo del probador falló: revisar la ejecución en n8n")
    print("\nListo. Commit + push de workflows/vivo_huellas.json. Después: sombra de los 4 mensajes reales (tests/comparativa) y limpieza.")


if __name__ == "__main__":
    main()
