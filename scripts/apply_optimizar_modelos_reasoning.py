"""Optimizacion v6 main (2026-06-04):
1. reasoning_effort=minimal en los 7 LM nodes (incluye Router, Formatting y 5 sub-agents)
2. Degradar Router LM, LM Sub-Agent General, LM Sub-Agent Urgencia -> gpt-5-mini
3. Mantener gpt-5 en LM Sub-Agent Confirmar, Cancelar, Agendar (tools Dentalink)
4. Mantener gpt-5 en OpenAI Chat Model1 (Formatting) - se probara nano de madrugada
5. Remover connection ai_tool: buscar_horarios -> Sub-Agent General

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

# Mapeo modelo objetivo por nodo LM
MODEL_BY_NODE = {
    "Router LM": "gpt-5-mini",
    "LM Sub-Agent Urgencia": "gpt-5-mini",
    "LM Sub-Agent General": "gpt-5-mini",
    # Estos mantienen gpt-5 (tools Dentalink criticas)
    "LM Sub-Agent Confirmar": "gpt-5",
    "LM Sub-Agent Cancelar": "gpt-5",
    "LM Sub-Agent Agendar": "gpt-5",
    # Formatting se queda gpt-5 (probaremos nano madrugada)
    "OpenAI Chat Model1": "gpt-5",
}


def get_wf():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=60); r.raise_for_status(); return r.json()


def put_wf(wf):
    allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution",
               "executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": settings, "staticData": wf.get("staticData")}
    r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, json=body, timeout=40)
    if not r.ok:
        print("PUT FAIL", r.status_code, r.text[:1000], file=sys.stderr); r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    wf = get_wf()

    changes = []

    # === 1+2. reasoning_effort=minimal + cambio de modelo en los 7 LM nodes ===
    for n in wf["nodes"]:
        if n["name"] not in MODEL_BY_NODE: continue
        target_model = MODEL_BY_NODE[n["name"]]
        params = n["parameters"]
        # modelo actual
        m = params.get("model", {})
        if isinstance(m, dict):
            current_model = m.get("value", "?")
        else:
            current_model = str(m)
        # set modelo
        params["model"] = {
            "__rl": True,
            "value": target_model,
            "mode": "list",
            "cachedResultName": target_model,
        }
        # options.reasoningEffort = "minimal"
        opts = params.get("options", {}) or {}
        prev_re = opts.get("reasoningEffort", "(unset)")
        opts["reasoningEffort"] = "minimal"
        params["options"] = opts
        changes.append(f"  {n['name']}: model {current_model} -> {target_model}, reasoning_effort {prev_re} -> minimal")

    # === 5. Remover connection ai_tool: buscar_horarios -> Sub-Agent General ===
    conns = wf["connections"]
    if "buscar_horarios" in conns and "ai_tool" in conns["buscar_horarios"]:
        before = conns["buscar_horarios"]["ai_tool"]
        new_outer = []
        removed = 0
        for arr in before:
            new_arr = [c for c in arr if c.get("node") != "Sub-Agent General"]
            if len(new_arr) != len(arr): removed += (len(arr) - len(new_arr))
            new_outer.append(new_arr)
        conns["buscar_horarios"]["ai_tool"] = new_outer
        changes.append(f"  CONN: buscar_horarios -> Sub-Agent General REMOVED ({removed} link)")
    else:
        changes.append("  CONN: buscar_horarios no tiene ai_tool conexiones?? skip")

    print("CAMBIOS:\n" + "\n".join(changes))

    if args.dry or not args.apply:
        print("\n[dry] no aplicado."); return

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_OPTIMIZAR_MODELOS_REASONING_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(get_wf(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup pre -> {pre}")

    res = put_wf(wf); print(f"\nPUT OK updatedAt={res.get('updatedAt')}")

    # Verify
    wf2 = get_wf()
    ok_all = True
    print("\n[verify]")
    for n in wf2["nodes"]:
        if n["name"] not in MODEL_BY_NODE: continue
        m = n["parameters"].get("model", {})
        cm = m.get("value", "?") if isinstance(m, dict) else str(m)
        opts = n["parameters"].get("options", {}) or {}
        re_v = opts.get("reasoningEffort", "(unset)")
        exp = MODEL_BY_NODE[n["name"]]
        ok = (cm == exp and re_v == "minimal")
        print(f"  {'OK' if ok else 'FAIL'} {n['name']}: model={cm} reasoning_effort={re_v}")
        if not ok: ok_all = False
    # verify connection removed
    conns2 = wf2["connections"].get("buscar_horarios", {}).get("ai_tool", [])
    has_general = any(c.get("node") == "Sub-Agent General" for arr in conns2 for c in arr)
    print(f"  {'OK' if not has_general else 'FAIL'} buscar_horarios sin link a General: {not has_general}")
    if has_general: ok_all = False
    if not ok_all: sys.exit(3)


if __name__ == "__main__":
    main()
