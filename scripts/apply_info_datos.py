# -*- coding: utf-8 -*-
"""
apply_info_datos.py — 2026-11-12 (tarde) · Información no puede decir horas ni montos que no estén en los DATOS del consultorio.
Caso: repetición en sombra de r007 ("esta tarde hasta qué hora está la doctora", jueves) DESPUÉS de desplegar apply_info_franja.py. El orquestador del cerebro
actual escribió en el PEDIDO una respuesta inventada ("por la tarde la Dra atiende hasta las 18:00. ¿Para quién es? nombre o DNI") e Información la copió
(ejecución 339154): los jueves a la tarde no se atiende. Es una falla de antes (el prompt del orquestador no cambió hoy); con la entrada exacta, 2 de 6 respuestas
repetían las 18:00.
Dos capas (regla 5):
  1. Prompt de Información: "Los horarios y los precios salen solo de los DATOS, nunca del PEDIDO ni del CONTEXTO." Modelo real (gpt-5-mini, razonamiento
     bajo), 6 corridas por caso, 12 casos: 70/72 vs 66/72; pedido con 18:00 inventado 6/6 vs 3/6; pedido con 20:00 inventado 6/6 vs 3/6; sin regresiones.
  2. Código (v7/info_core.js, nodo "Armar salida"): toda hora y todo monto del texto tiene que estar escrito en los DATOS; si no, la respuesta no sale y queda
     fuera de alcance (el cerebro deriva a la secretaria). Tests: tests/test_info_core.mjs 19/19. Sobre las 44 respuestas reales que guarda n8n (desde el 02/11)
     frena 1: la de las 18:00.

Workflow que toca (VIVO): "v7 Agente Informacion" (prompt + nodo "Armar salida"). Lo usan el cerebro actual y el Cerebro Agente; no toca el cerebro,
la entrada, Recordatorios ni el v6. Diff COMPLETO (scripts/diff_vivo.py); el PUT pasa por scripts/guarda_vivo.py.

USO:  python scripts/apply_info_datos.py            # simulación: diff contra lo vivo
      python scripts/apply_info_datos.py --apply    # check_triaje + backup PRE + PUT + verificación + backup POST
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
CLAVES = ["agente_informacion"]


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
        (HIST / f"{wid}_PRE_info_datos_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
        D.api(f"/workflows/{wid}", "PUT", {"name": nuevo["name"], "nodes": nuevo["nodes"], "connections": nuevo["connections"],
                                            "settings": {k2: v for k2, v in (vivo.get("settings") or {}).items() if k2 in D.SETTINGS_OK}})
        post = D.api(f"/workflows/{wid}")
        (HIST / f"{wid}_POST_info_datos_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
        ok = V.comparar(post, nuevo)[0] == 0 and post.get("active") == vivo.get("active")
        print(f"   {'ok' if ok else '¡NO COINCIDE!'} · activo={post.get('active')} · backups en workflows/history (*_{ts}.json)")
        if not ok:
            sys.exit("verificación falló: restaurar con el backup PRE")
    if not apply:
        print("\n(simulación: nada se cambió. --apply con OK de Lucas)")


if __name__ == "__main__":
    main()
