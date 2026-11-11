# -*- coding: utf-8 -*-
"""
apply_escenario_prueba.py — 2026-11-11 · escenarios de PRUEBA para el cerebro (pedido de Lucas: "las pruebas manipulando todo el contexto, que no sea por fichas").

Qué cambia (dos herramientas VIVAS del v7, más el webhook de prueba que está inactivo):
  · "v7 Tool - ver_turnos": lee "escenario:<tel>" de Redis. Si existe Y el teléfono es el de Lucas o uno sintético (v7/escenario_core.js), las citas
    salen del escenario en vez de Dentalink. Con cualquier otro teléfono (todos los pacientes) el escenario se ignora: hace lo mismo que hoy.
  · "v7 Tool - confirmar_una": igual, solo en modo sombra: la verificación de la cita usa la del escenario. En vivo, nada cambia.
  · "v7 Test (sombra)" (inactivo): destino "escenario" que guarda el escenario (15 min) y la ficha; el reinicio lo borra.
El escenario solo lo puede cargar el webhook de prueba, que ya rechaza cualquier teléfono que no sea el de Lucas o sintético.

USO:  python scripts/apply_escenario_prueba.py            # simulación: muestra el diff contra lo vivo
      python scripts/apply_escenario_prueba.py --apply    # check_triaje + backup PRE + PUT + verificación + backup POST
Regla del proyecto: --apply solo con OK ("desplegá") de Lucas.
"""
import argparse, difflib, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crear_v7_en_n8n as D

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = D.ROOT
HIST = ROOT / "workflows" / "history"
HERRAMIENTAS = ["ver_turnos", "confirmar_una"]


def cuerpo(wf, settings_vivos):
    return {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": {k: v for k, v in (settings_vivos or {}).items() if k in D.SETTINGS_OK}}


def diff(vivo, nuevo):
    nv = {n["name"]: n for n in vivo["nodes"]}
    nn = {n["name"]: n for n in nuevo["nodes"]}
    for k in sorted(set(nn) - set(nv)):
        print(f"   + nodo nuevo: {k}")
    for k in sorted(set(nv) - set(nn)):
        print(f"   - nodo que se va: {k}")
    for k in sorted(set(nv) & set(nn)):
        a = (nv[k].get("parameters") or {}).get("jsCode")
        b = (nn[k].get("parameters") or {}).get("jsCode")
        if a is not None and b is not None and a != b:
            print(f"   ~ código de «{k}»:")
            for l in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0):
                if not l.startswith(("---", "+++", "@@")):
                    print("      " + l[:220])
        elif a is None and json.dumps(nv[k].get("parameters"), sort_keys=True) != json.dumps(nn[k].get("parameters"), sort_keys=True):
            print(f"   ~ parámetros de «{k}»")
    if json.dumps(vivo["connections"], sort_keys=True) != json.dumps(nuevo["connections"], sort_keys=True):
        print("   ~ conexiones cambian (entra «Redis GET escenario» al principio)")


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
    for k in HERRAMIENTAS:
        wid = ids[k]
        vivo = D.api(f"/workflows/{wid}")
        nuevo = json.loads((ROOT / "v7" / "workflows" / f"{k}.json").read_text(encoding="utf-8"))
        print(f"== {vivo['name']} ({wid}) activo={vivo.get('active')}")
        diff(vivo, nuevo)
        if not apply:
            continue
        (HIST / f"{wid}_PRE_escenario_prueba_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
        D.api(f"/workflows/{wid}", "PUT", cuerpo(nuevo, vivo.get("settings")))
        post = D.api(f"/workflows/{wid}")
        (HIST / f"{wid}_POST_escenario_prueba_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
        ok = sorted(n["name"] for n in post["nodes"]) == sorted(n["name"] for n in nuevo["nodes"]) and post.get("active") == vivo.get("active")
        print(f"   {'ok' if ok else '¡NO COINCIDE!'} · activo={post.get('active')} · backups en workflows/history (*_{ts}.json)")
        if not ok:
            sys.exit("verificación falló: restaurar con el backup PRE")
    if not apply:
        print("\n(simulación: nada se cambió. --apply con OK de Lucas)")


if __name__ == "__main__":
    main()
