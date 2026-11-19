# -*- coding: utf-8 -*-
"""
Devuelve una cita de Dentalink al estado que tenía ANTES de que Asiri la confirmara por error (13/11/2026: Asiri confirmó un turno que el
paciente no pidió confirmar y pisó "Atendido" de un turno de hoy ya pasado).

Freno: solo cambia la cita si HOY sigue en "Confirmado por WhatsApp" (18), que es lo que puso Asiri. Si la clínica ya la tocó, no hace nada.
USO: python scripts/restaurar_estado_cita.py --cita 9492 --estado 2            (solo muestra)
     python scripts/restaurar_estado_cita.py --cita 9492 --estado 2 --apply    (cambia y verifica)
Estados usados: 2 Atendido · 15 Notificado por WhatsApp · 18 Confirmado por WhatsApp.
"""
import argparse, json, sys
sys.stdout.reconfigure(encoding="utf-8")
import crear_cita_prueba_examen as C
from crear_cita_prueba_examen import ejecutar_una_vez, DENTALINK

CONFIRMADO_POR_ASIRI = 18


def _leer(metodo, url, body, ruta):
    # Igual que C.workflow_temporal pero sin cuerpo (un GET con cuerpo "null" lo rechaza Dentalink).
    if body is not None:
        return _orig(metodo, url, body, ruta)
    g = C.Grafo("TMP leer cita (se borra solo)")
    g._nodo("Webhook", "n8n-nodes-base.webhook", 2, {"httpMethod": "POST", "path": ruta, "responseMode": "lastNode", "options": {}}, 0, 0, {"webhookId": C.secrets.token_hex(8)})
    g.dentalink("Dentalink", metodo, f"'{url}'", None, 240, 0)
    g.conectar("Webhook", "Dentalink")
    wf = g.json()
    wf["settings"] = dict(C.SETTINGS_MIN)
    return wf


_orig = C.workflow_temporal
C.workflow_temporal = _leer


def estado(cita):
    r = ejecutar_una_vez("GET", f"{DENTALINK}/citas/{cita}/", None)
    d = (r or {}).get("data") or {}
    if not d:
        sys.exit(f"No pude leer la cita {cita}: {json.dumps(r, ensure_ascii=False)[:400]}")
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cita", type=int, required=True)
    ap.add_argument("--estado", type=int, required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    d = estado(a.cita)
    print(f"cita {a.cita}: {d.get('fecha')} {d.get('hora_inicio')} · estado {d.get('id_estado')} «{str(d.get('estado_cita')).strip()}»")
    if int(d.get("id_estado") or 0) != CONFIRMADO_POR_ASIRI:
        print("No está en «Confirmado por WhatsApp»: la clínica ya la cambió. No toco nada.")
        return
    if not a.apply:
        print(f"(simulación) PUT {{\"id_estado\": {a.estado}}} — corré con --apply")
        return
    r = ejecutar_una_vez("PUT", f"{DENTALINK}/citas/{a.cita}/", {"id_estado": a.estado})
    print("PUT:", json.dumps((r or {}).get("data", r), ensure_ascii=False)[:300])
    d = estado(a.cita)
    ok = int(d.get("id_estado") or 0) == a.estado
    print(f"verificado: estado {d.get('id_estado')} «{str(d.get('estado_cita')).strip()}» -> {'OK' if ok else 'NO QUEDÓ'}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
