# -*- coding: utf-8 -*-
"""
apply_info_franja.py — 2026-11-12 (tarde) · refuerzo del arreglo r007 en Información ("esta tarde hasta qué hora está la doctora", jueves).
La línea desplegada a la mañana (apply_lista_espera_e_info.py) daba 16/16 en el laboratorio, pero al repetir el caso real después de desplegar (12:58,
pedido del orquestador con otras palabras) aclaraba la tarde solo 3 de 12 veces: decía "hoy atiende de 8 a 12" y nada más.
Nueva línea: "empezá diciendo que ese día o esa franja no se atiende…". Modelo real (gpt-5-mini, razonamiento bajo), 6 corridas por caso, 9 casos
(7 de control + las 2 entradas exactas de la repetición): 52/54 vs 45/54 la línea anterior y 40/54 sin línea; con la entrada real 10/12 vs 3/12;
horarios generales, "¿hasta qué hora hoy?", "mañana a la mañana", sábados y precio sin cambios (nada dice "no se atiende" cuando sí se atiende).

Workflow que toca (VIVO): "v7 Agente Informacion" (solo el prompt). Diff COMPLETO (scripts/diff_vivo.py); el PUT pasa por scripts/guarda_vivo.py.

USO:  python scripts/apply_info_franja.py            # simulación: diff contra lo vivo
      python scripts/apply_info_franja.py --apply    # check_triaje + backup PRE + PUT + verificación + backup POST
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
        (HIST / f"{wid}_PRE_info_franja_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
        D.api(f"/workflows/{wid}", "PUT", {"name": nuevo["name"], "nodes": nuevo["nodes"], "connections": nuevo["connections"],
                                            "settings": {k2: v for k2, v in (vivo.get("settings") or {}).items() if k2 in D.SETTINGS_OK}})
        post = D.api(f"/workflows/{wid}")
        (HIST / f"{wid}_POST_info_franja_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
        ok = V.comparar(post, nuevo)[0] == 0 and post.get("active") == vivo.get("active")
        print(f"   {'ok' if ok else '¡NO COINCIDE!'} · activo={post.get('active')} · backups en workflows/history (*_{ts}.json)")
        if not ok:
            sys.exit("verificación falló: restaurar con el backup PRE")
    if not apply:
        print("\n(simulación: nada se cambió. --apply con OK de Lucas)")


if __name__ == "__main__":
    main()
