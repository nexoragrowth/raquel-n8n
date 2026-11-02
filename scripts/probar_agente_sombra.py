# -*- coding: utf-8 -*-
"""
probar_agente_sombra.py — corre la batería en SOMBRA contra "v7 Cerebro Agente" con el modelo real y el número de Lucas, sin molestar a nadie:
  1. quita el aviso automático de errores (errorWorkflow) del workflow nuevo y del webhook de prueba mientras dura (si no, un fallo manda "[FALLO TECNICO]" al grupo de la clínica);
  2. ENCIENDE el agente solo durante la batería (n8n no ejecuta sub-workflows apagados) y el webhook de prueba;
  3. al terminar, SIEMPRE: apaga el agente y el webhook, y restaura la configuración original del webhook de prueba.
No toca el cerebro vivo, la entrada ni los sub-agentes. Todo en modo sombra: no manda WhatsApp ni escribe en la agenda.

USO:  python scripts/probar_agente_sombra.py <ruta_batería.py>
"""
import json, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crear_v7_en_n8n as D

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = D.ROOT
IDS = json.loads(D.IDS.read_text(encoding="utf-8"))
AGENTE, TEST = IDS["cerebro_agente"], IDS["test"]


def put_settings(wid, quitar_error_wf):
    w = D.api(f"/workflows/{wid}")
    s = {k: v for k, v in (w.get("settings") or {}).items() if k in D.SETTINGS_OK}
    if quitar_error_wf:
        s.pop("errorWorkflow", None)
    D.api(f"/workflows/{wid}", "PUT", {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"], "settings": s})
    return w


def main():
    bateria = sys.argv[1]
    test_original = D.api(f"/workflows/{TEST}")
    try:
        put_settings(AGENTE, True)
        put_settings(TEST, True)
        D.api(f"/workflows/{AGENTE}/activate", "POST")
        print("agente ENCENDIDO (solo durante la prueba), sin aviso de errores al grupo")
        r = subprocess.run([sys.executable, bateria, "cerebro_agente"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(r.stdout)
        if r.returncode != 0:
            print(r.stderr[-1500:])
    finally:
        for wid in (AGENTE, TEST):
            try:
                D.api(f"/workflows/{wid}/deactivate", "POST")
            except Exception as e:  # ya estaba apagado
                print("deactivate", wid, "->", str(e)[:80])
        s = {k: v for k, v in (test_original.get("settings") or {}).items() if k in D.SETTINGS_OK}
        D.api(f"/workflows/{TEST}", "PUT", {"name": test_original["name"], "nodes": test_original["nodes"], "connections": test_original["connections"], "settings": s})
        estado = {n: D.api(f"/workflows/{w}").get("active") for n, w in (("agente", AGENTE), ("test", TEST), ("cerebro vivo", "NBHzj8ar2XuSvyIY"))}
        print("estado final (active):", estado, "· webhook de prueba restaurado")


if __name__ == "__main__":
    main()
