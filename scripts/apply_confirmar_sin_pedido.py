# -*- coding: utf-8 -*-
"""
apply_confirmar_sin_pedido.py — 2026-11-13 · 2 conversaciones reales de hoy en las que Asiri CONFIRMÓ sin que nadie lo pidiera:
  1) "Y <hermano> tb" (la mamá acababa de avisar que a la hermana se le salió un alambrito): el orquestador dijo "responde a la confirmación pendiente" sin
     que hubiera ninguna; Turnos, siguiendo la nota de confirmar_turno ("si tiene un turno vigente… llamá con su fecha"), confirmó el turno del hermano.
  2) Paciente que se atendió a las 11 h: a las 15 h "Muchas gracias / No hay problema" → "Su turno vigente es el viernes 13/11 a las 11:00"; "Es el de
     hoy" → lo mismo; "Ya asistí" → "Perfecto, su turno … está confirmado" y en Dentalink pisó "Atendido" con "Confirmado por WhatsApp".
Arreglo (código; cada regla en más de una capa):
  - orquestador_core.despachar: "responde a la confirmación pendiente" sin recordatorio abierto, sin read-back visto y sin propuesta de la clínica → no
    va a Turnos (silencio si no hay otra cosa). El cerebro pasa recordatorio_abierto (hay recordatorios abiertos, aunque después escribiera el staff).
  - confirmar_core.elegir: por la agenda, un turno ya pasado o Atendido no se confirma (motivo turno_pasado); la nota sin_recordatorio ya no invita a
    confirmar por su cuenta. confirmar_core.verificar: si Dentalink dice Atendido (2), no se pisa.
  - orquestador_core.salidaTurnos: turno_pasado → silencio (ni "su turno vigente es…" ni "¿cuál de estos turnos?").
  - ficha_core.visibles + ver_turnos: lo que se le muestra a Asiri como vigente no incluye los de hoy ya pasados ni los Atendidos.
Tests: tests/test_orquestador_core.mjs SC1–SC20 (233/233) y barrido offline completo.

Workflows que toca (VIVOS): los 4 agentes, "v7 Cerebro", "v7 Cerebro Agente" (inactivo), "v7 Panel - probar Información" y las herramientas ver_turnos,
elegir_ficha, confirmar_una y confirmar_turno. Primero los que entienden "turno_pasado", después las herramientas que lo devuelven. NO toca la entrada
O155, Recordatorios, el v6 ni "v6 Orquestador (sombra)". Diff COMPLETO (scripts/diff_vivo.py); cada PUT pasa por scripts/guarda_vivo.py.

USO:  python scripts/apply_confirmar_sin_pedido.py            # simulación: diffs contra lo vivo
      python scripts/apply_confirmar_sin_pedido.py --apply    # check_triaje + backup PRE + PUT + verificación + backup POST + humo del probador
Vuelta atrás: scripts/restaurar_workflow.py con los backups PRE (workflows/history/*_PRE_confirmar_sin_pedido_<ts>.json).
Datos: las 2 citas confirmadas por error vuelven a su estado con scripts/restaurar_estado_cita.py (9492 → 2 Atendido, 9309 → 15 Notificado).
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
CLAVES = ["agente_turnos", "agente_pagos", "agente_informacion", "agente_urgencias", "cerebro", "cerebro_agente", "panel_probar",
          "ver_turnos", "elegir_ficha", "confirmar_una", "confirmar_turno"]
ETIQUETA = "confirmar_sin_pedido"


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
