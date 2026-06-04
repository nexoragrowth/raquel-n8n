"""FASE 4a REDISEÑO MEMORIA - Limpiar el INPUT de los 5 sub-agents.

PROBLEMA: hoy el text input de cada sub-agent incluye:
  [CONTEXTO DEL PACIENTE QUE ESCRIBE]
  phone: ...
  pushName: ...
  resumen historial: ...

  [MENSAJE]
  <msg paciente>

Y LangChain auto-save guarda TODO eso como human message en memoria.
La basura "[CONTEXTO DEL PACIENTE QUE ESCRIBE]..." llena la ventana del LLM.

FIX:
1. El contexto del paciente ahora va al systemMessage (via partial nuevo
   paciente_context_runtime.md que ya se concateno en las recetas — ese rebuild
   se hace con build_prompts_v6.py --apply).
2. El text input queda con SOLO el mensaje raw del paciente.

Resultado: LangChain guarda como human SOLO el mensaje del paciente.

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

SUB_AGENTS = ["Sub-Agent Confirmar", "Sub-Agent Cancelar", "Sub-Agent Agendar", "Sub-Agent Urgencia", "Sub-Agent General"]
NEW_TEXT = "={{ $('Preparar Mensaje Final').first().json.text }}"


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
    nodes_by_name = {n["name"]: n for n in wf["nodes"]}

    changes = []
    for name in SUB_AGENTS:
        n = nodes_by_name.get(name)
        if not n: print(f"!! {name} no encontrado"); sys.exit(2)
        old_text = n["parameters"].get("text", "")
        if old_text == NEW_TEXT:
            print(f"  [{name}] ya aplicado (text = NEW_TEXT)")
            continue
        if "[CONTEXTO DEL PACIENTE QUE ESCRIBE]" not in old_text:
            print(f"  [{name}] text input NO tiene el patron esperado: {old_text[:80]!r}")
            sys.exit(2)
        changes.append((name, old_text))

    if not changes:
        print("\n!! nada que cambiar (probable ya aplicado)"); return

    print(f"\n=== {len(changes)} sub-agents a cambiar ===")
    for name, old in changes:
        print(f"\n--- {name} ---")
        print(f"  ANTES: {old[:150]!r}...")
        print(f"  DESPUES: {NEW_TEXT!r}")

    if args.dry or not args.apply:
        print("\n[dry] no aplicado."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_fase4a_clean_input_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(get_wf(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup pre -> {pre}")

    for name, _ in changes:
        nodes_by_name[name]["parameters"]["text"] = NEW_TEXT

    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")

    wf2 = get_wf()
    nm2 = {n["name"]: n for n in wf2["nodes"]}
    all_ok = True
    for name, _ in changes:
        if nm2[name]["parameters"]["text"] != NEW_TEXT:
            print(f"[verify] FAIL {name}"); all_ok = False
        else:
            print(f"[verify] OK   {name}")
    sys.exit(0 if all_ok else 3)


if __name__ == "__main__":
    main()
