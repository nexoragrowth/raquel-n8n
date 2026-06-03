"""Router: agregar EMOJIS REACCIONES (pulgar arriba 👍, check ✅, OK 👌, manos oracion 🙏, corazon ❤️, etc.) como senales afirmativas en contexto post-recordatorio.

La Dra el 03/06/2026 escribió: "El pulgar arriba también es válido como confirmación, no lo está confirmando a esos."

Modo: --dry / --apply
"""
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

OLD_LINE = '- Afirmaciones generales (en contexto post-recordatorio): "si", "sí", "siii", "si si", "sisi", "si dale", "si claro", "ok", "okey", "dale", "claro", "claro que si", "obvio", "obviamente", "perfecto", "joya", "genial", "listo", "todo bien", "todo ok".'

NEW_LINES = (
    '- Afirmaciones generales (en contexto post-recordatorio): "si", "sí", "siii", "si si", "sisi", "si dale", "si claro", "ok", "okey", "dale", "claro", "claro que si", "obvio", "obviamente", "perfecto", "joya", "genial", "listo", "todo bien", "todo ok".\n'
    '- EMOJIS REACCIONES (NUEVO 2026-06-03 pedido Dra): si el paciente responde SOLO con un emoji afirmativo (sin texto adicional) en contexto post-recordatorio, ES confirmacion. Incluye: 👍 (pulgar arriba), 👌 (OK), ✅ ☑️ (check), 🙏 (manos oracion), ❤️ 💙 💚 🧡 💛 (corazones), 🤝 (apreton de manos), 😊 ☺️ 🙂 (sonrisas), 💯 (cien). Estos emojis SOLOS post-recordatorio = confirmar_post_recordatorio (NO los confundas con CIERRES_CONVERSACIONALES del header — los cierres aplican solo cuando NO hay accion pendiente; en contexto post-recordatorio HAY accion pendiente = confirmar el turno).'
)


def get_wf():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=60); r.raise_for_status(); return r.json()


def put_wf(wf):
    allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution",
               "executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": settings, "staticData": wf.get("staticData")}
    r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, json=body, timeout=40)
    if not r.ok: print("PUT FAIL", r.status_code, r.text[:500], file=sys.stderr); r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    wf = get_wf()
    n = next((x for x in wf["nodes"] if x["name"] == "Router - Clasificar Intent"), None)
    if not n: print("!! Router no encontrado"); sys.exit(2)
    sm = n["parameters"]["options"]["systemMessage"]
    if "EMOJIS REACCIONES" in sm:
        print("!! ya aplicado"); sys.exit(3)
    cnt = sm.count(OLD_LINE)
    if cnt != 1:
        print(f"!! anchor no match: count={cnt}"); sys.exit(2)
    new_sm = sm.replace(OLD_LINE, NEW_LINES)
    print(f"Router systemMessage: {len(sm)} -> {len(new_sm)} chars (delta {len(new_sm)-len(sm):+d})")
    if args.dry or not args.apply: print("[dry] no aplicado."); return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_router_pulgar_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(get_wf(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup pre -> {pre}")
    n["parameters"]["options"]["systemMessage"] = new_sm
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")
    wf2 = get_wf()
    n2 = next(x for x in wf2["nodes"] if x["name"] == "Router - Clasificar Intent")
    ok = "EMOJIS REACCIONES" in n2["parameters"]["options"]["systemMessage"]
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
