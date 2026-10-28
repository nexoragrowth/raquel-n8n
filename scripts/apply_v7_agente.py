# -*- coding: utf-8 -*-
"""
apply_v7_agente.py — 2026-10-28 · actualiza UN sub-agente del v7 (Turnos, Pagos, Informacion o Urgencias) desde el repo, con el mismo cuidado que
apply_cerebro_auditoria.py: simulación por defecto (qué nodos cambian), check_triaje, backup PRE, PUT solo de ese workflow, GET, backup POST y
verificación vivo == generado. No toca el cerebro, las herramientas, la entrada ni Recordatorios.

Primer uso (28/10): agente Información — "Respondé SOLO lo que pide el PEDIDO" (antes, un mensaje mixto como "cuánto sale la consulta y cuánto debo"
lo hacía contestar FUERA_DE_ALCANCE a todo y se perdía el precio; auditoría v6→v7, ejecución real 321598 y prueba en sombra del 28/10).

USO:  python scripts/apply_v7_agente.py informacion            # simulación
      python scripts/apply_v7_agente.py informacion --apply    # aplica
"""
import argparse, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crear_v7_en_n8n as D   # api(), SETTINGS_OK, IDS, ROOT (no ejecuta main)
from apply_cerebro_auditoria import diferencias

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = D.ROOT
HIST = ROOT / "workflows" / "history"
CLAVES = ("turnos", "pagos", "informacion", "urgencias")
ESPERADOS = {"Agente", "Armar salida"}   # el prompt (system message) y el núcleo embebido (orquestador_core.js)


def generado(clave):
    subprocess.run([sys.executable, "-W", "ignore", str(ROOT / "scripts" / "build_v7_workflows.py")], check=True, capture_output=True)
    txt = (ROOT / "v7" / "workflows" / f"agente_{clave}.json").read_text(encoding="utf-8")
    ids = json.loads(D.IDS.read_text(encoding="utf-8"))
    for k, v in ids.items():
        txt = txt.replace(f"@@ID:{k}@@", v)
    assert "@@ID:" not in txt, "quedaron marcadores sin resolver"
    return json.loads(txt), ids[f"agente_{clave}"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clave", choices=CLAVES)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    nuevo, wid = generado(a.clave)
    vivo = D.api(f"/workflows/{wid}")
    d = diferencias(vivo, nuevo)
    print(f"{vivo['name']} ({wid}) · vivo: {len(vivo['nodes'])} nodos · generado: {len(nuevo['nodes'])} nodos · activo={vivo.get('active')}")
    print("  nodos AGREGADOS :", d["agregados"] or "—")
    print("  nodos SACADOS   :", d["sacados"] or "—")
    print("  nodos CAMBIADOS :", d["cambiados"] or "—")
    print("  conexiones      :", "iguales" if d["conexiones_iguales"] else "DISTINTAS")
    raro = [n for n in d["cambiados"] if n not in ESPERADOS] or d["agregados"] or d["sacados"] or not d["conexiones_iguales"]
    if raro:
        print("\n  ATENCIÓN: cambia algo más de lo previsto:", raro)
    if not a.apply:
        print("\n[SIMULACIÓN] No se escribió nada. Correr con --apply.")
        return
    if raro:
        raise SystemExit("Aborto: el diff trae cambios no previstos. Revisar a mano.")
    if not d["cambiados"]:
        print("Nada que cambiar.")
        return
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_triaje.py")], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("check_triaje:", "OK" if r.returncode == 0 else "FALLÓ\n" + (r.stdout + r.stderr)[-800:])
    if r.returncode != 0:
        raise SystemExit("Aborto: check_triaje no pasa.")
    ts = time.strftime("%Y%m%d_%H%M%S")
    (HIST / f"v7_{wid}_PRE_agente_{a.clave}_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
    print("backup PRE:", f"v7_{wid}_PRE_agente_{a.clave}_{ts}.json")
    body = {"name": nuevo["name"], "nodes": nuevo["nodes"], "connections": nuevo["connections"], "settings": {k: v for k, v in (nuevo.get("settings") or D.SETTINGS).items() if k in D.SETTINGS_OK}}
    D.api(f"/workflows/{wid}", "PUT", body)
    post = D.api(f"/workflows/{wid}")
    (HIST / f"v7_{wid}_POST_agente_{a.clave}_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
    d2 = diferencias(post, nuevo)
    ok = not d2["cambiados"] and not d2["agregados"] and not d2["sacados"] and d2["conexiones_iguales"] and post.get("active") == vivo.get("active")
    print(f"verificación: vivo == generado → {'OK' if ok else 'DIFIERE ' + json.dumps(d2, ensure_ascii=False)} · activo={post.get('active')}")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
