# -*- coding: utf-8 -*-
"""
apply_arreglos_espejo.py — 2026-11-12 · lleva al bot VIVO dos arreglos encontrados comparando con mensajes reales (espejo del Cerebro Agente):
  1. "No veo turnos vigentes con este número de celular." salía DEBAJO de los horarios libres a pacientes que pedían turno ("Quería saber si tiene
     turno para el viernes"): el sub-agente Turnos a veces lo entiende como "¿tengo turno?". Con horarios ofrecidos y sin turnos propios, ya no va.
     (v7/orquestador_core.js · salidaTurnos; test T6b–T6d en tests/test_orquestador_core.mjs)
  2. (11/11, commit 8da9c9d) chequeo de salida: "jueves 8:00" es horario de atención, no "el jueves 8" (frenaba respuestas correctas de Información).

Workflows que toca (los dos VIVOS): "v7 Cerebro" y "v7 Agente Turnos". No toca la entrada, las herramientas, Recordatorios ni el v6.

USO:  python scripts/apply_arreglos_espejo.py            # simulación: diff contra lo vivo
      python scripts/apply_arreglos_espejo.py --apply    # check_triaje + backup PRE + PUT + verificación + backup POST
Regla del proyecto: --apply solo con OK ("desplegá") de Lucas. Vuelta atrás: scripts/restaurar_workflow.py con el backup PRE.
"""
import argparse, difflib, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crear_v7_en_n8n as D
import build_v7_workflows as B

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = D.ROOT
HIST = ROOT / "workflows" / "history"
CLAVES = ["cerebro", "agente_turnos"]


def generado(clave, ids):
    txt = json.dumps(B.WORKFLOWS[clave](), ensure_ascii=False)
    for k, v in ids.items():
        txt = txt.replace(f"@@ID:{k}@@", v)
    assert "@@ID:" not in txt, f"{clave}: quedaron marcadores sin resolver"
    return json.loads(txt)


def diff(vivo, nuevo):
    nv = {n["name"]: n for n in vivo["nodes"]}
    nn = {n["name"]: n for n in nuevo["nodes"]}
    cambios = 0
    for k in sorted(set(nn) ^ set(nv)):
        print(f"   {'+ nodo nuevo' if k in nn else '- nodo que se va'}: {k}"); cambios += 1
    for k in sorted(set(nv) & set(nn)):
        a = (nv[k].get("parameters") or {}).get("jsCode")
        b = (nn[k].get("parameters") or {}).get("jsCode")
        if a is not None and b is not None and a != b:
            cambios += 1
            print(f"   ~ código de «{k}»:")
            for l in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0):
                if not l.startswith(("---", "+++", "@@")):
                    print("      " + l[:200])
    if json.dumps(vivo["connections"], sort_keys=True) != json.dumps(nuevo["connections"], sort_keys=True):
        print("   ~ conexiones cambian"); cambios += 1
    return cambios


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
        nuevo = generado(k, ids)
        assert nuevo["name"] == vivo["name"], f"{k}: el nombre no coincide ({nuevo['name']} vs {vivo['name']})"
        print(f"== {vivo['name']} ({wid}) activo={vivo.get('active')}")
        if not diff(vivo, nuevo):
            print("   (sin cambios: no se toca)"); continue
        if not apply:
            continue
        (HIST / f"{wid}_PRE_arreglos_espejo_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
        D.api(f"/workflows/{wid}", "PUT", {"name": nuevo["name"], "nodes": nuevo["nodes"], "connections": nuevo["connections"],
                                            "settings": {k2: v for k2, v in (vivo.get("settings") or {}).items() if k2 in D.SETTINGS_OK}})
        post = D.api(f"/workflows/{wid}")
        (HIST / f"{wid}_POST_arreglos_espejo_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
        cod = lambda w: {n["name"]: (n.get("parameters") or {}).get("jsCode") for n in w["nodes"]}
        ok = cod(post) == cod(nuevo) and post.get("active") == vivo.get("active")
        print(f"   {'ok' if ok else '¡NO COINCIDE!'} · activo={post.get('active')} · backups en workflows/history (*_{ts}.json)")
        if not ok:
            sys.exit("verificación falló: restaurar con el backup PRE")
    if not apply:
        print("\n(simulación: nada se cambió. --apply con OK de Lucas)")


if __name__ == "__main__":
    main()
