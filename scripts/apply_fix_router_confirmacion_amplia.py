"""Fix Router regla #2: ampliar señales de confirmar_post_recordatorio.
Caso real (exec 64397, 2/6 8:57 AM): paciente respondio 'Bueno dias, si si asistiremos' al recordatorio,
Router clasifico como cancelar_o_reprogramar -> Sub-WF Cancelar -> Step 4 detecto familia -> escalo.
Lista vieja: solo 'confirmo, si confirmo, ahi estare, voy, asisto al turno, tengo turno con raquel'.

Modos: --dry / --apply"""
from __future__ import annotations
import argparse, json, os, sys, io
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
WF_ID = "O155MqHgOSaNZ9ye"; H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
NODE = "Router - Clasificar Intent"

OLD = '''**2. confirmar_post_recordatorio**
- "confirmo", "si confirmo", "ahi estare", "voy", "asisto al turno", "tengo turno con raquel".'''

NEW = '''**2. confirmar_post_recordatorio**
AFIRMACION DE ASISTENCIA: si el ultimo AI fue un recordatorio (empieza con "AUREA" o contiene "Le recordamos su turno con la Dra. Rodriguez Raquel") Y el paciente responde con CUALQUIER expresion afirmativa de que va a ir al turno, intent = `confirmar_post_recordatorio`. La lista de senales es ABIERTA — usa criterio: cualquier dicho que indique afirmacion o asistencia entra aca.

Senales explicitas (ejemplos, NO limitativos):
- Confirmacion directa: "confirmo", "si confirmo", "confirmado", "confirmamos", "le confirmo", "te confirmo".
- Verbos de asistir: "asisto", "asisto al turno", "asistire", "asistiré", "asistimos", "asistiremos", "voy a asistir", "vamos a asistir".
- Verbos de ir / presencia: "voy", "vamos", "alli voy", "alli vamos", "ahi voy", "ahi vamos", "ahi estare", "ahi estoy", "ahi estamos", "ahi vamos a estar", "presente", "presentes".
- Afirmaciones generales (en contexto post-recordatorio): "si", "sí", "siii", "si si", "sisi", "si dale", "si claro", "ok", "okey", "dale", "claro", "claro que si", "obvio", "obviamente", "perfecto", "joya", "genial", "listo", "todo bien", "todo ok".
- Verbos de tener turno: "tengo turno con raquel", "tengo el turno", "tengo turno", "tenemos turno".
- Negaciones que son afirmacion: "no falto", "no faltamos", "no nos perdemos", "seguro que si".

REGLA DE ORO en contexto post-recordatorio: ante DUDA entre confirmar y otra cosa, elegi `confirmar_post_recordatorio` (el bot lo va a confirmar si el turno existe; si no, escala). NUNCA clasifiques como `cancelar_o_reprogramar` salvo que haya senal CLARA de cancelar/reprogramar/no poder ir.'''


def get_wf():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=60); r.raise_for_status(); return r.json()

def put_wf(wf):
    allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution",
               "executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": settings, "staticData": wf.get("staticData")}
    r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, json=body, timeout=40)
    if not r.ok: print("PUT FAIL", r.status_code, r.text[:300], file=sys.stderr); r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    wf = get_wf()
    n = next((x for x in wf["nodes"] if x["name"] == NODE), None)
    if not n: print("!! no encontre Router"); sys.exit(2)
    msg = n["parameters"]["options"]["systemMessage"]
    if OLD not in msg: print("!! anchor no encontrado"); sys.exit(3)
    if "AFIRMACION DE ASISTENCIA" in msg: print("!! ya aplicado"); sys.exit(4)
    new_msg = msg.replace(OLD, NEW, 1)
    print(f"Router: {len(msg)} -> {len(new_msg)} chars (delta {len(new_msg)-len(msg):+d})")
    if args.dry or not args.apply: print("\n[dry] no aplicado."); return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_router_confirmacion_amplia_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup pre -> {pre}")
    n["parameters"]["options"]["systemMessage"] = new_msg
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")
    wf2 = get_wf()
    n2 = next(x for x in wf2["nodes"] if x["name"] == NODE)
    ok = "AFIRMACION DE ASISTENCIA" in n2["parameters"]["options"]["systemMessage"]
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
