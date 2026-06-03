"""Barrido final 'Iri'/'Irina' en CANNED VISIBLES AL PACIENTE.
Categoria A del analisis: 10 canned (2 en v6 main + 8 en Sub-WF Cancelar).
NO toca categorias B/C/D (admin mapping, comentarios, instrucciones LLM internas).

Modos: --dry / --apply"""
from __future__ import annotations
import argparse, json, os, sys, io, re
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

# patron principal: "la secretaria Iri" o "la secretaria Irina" -> "la secretaria"
PATTERNS = [
    (re.compile(r'\bla secretaria (Iri|Irina)\b'), 'la secretaria'),
    (re.compile(r'\ba la secretaria (Iri|Irina)\b'), 'a la secretaria'),
]

WFS = {
    'v6_main': ('O155MqHgOSaNZ9ye', ['Gate Error Tecnico', 'Format Sub-WF Output']),
    'cancelar': ('5cAWJxiWJ50hxEq3', None),  # None = todos los nodos con jsCode
}

def get_wf(wid):
    r = requests.get(f"{BASE}/api/v1/workflows/{wid}", headers=H, timeout=60); r.raise_for_status(); return r.json()

def put_wf(wid, wf):
    allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution",
               "executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": settings, "staticData": wf.get("staticData")}
    r = requests.put(f"{BASE}/api/v1/workflows/{wid}", headers=H, json=body, timeout=40)
    if not r.ok: print("PUT FAIL", r.status_code, r.text[:300], file=sys.stderr); r.raise_for_status()
    return r.json()


def apply_to_workflow(label, wid, target_nodes, dry=True):
    wf = get_wf(wid)
    changes = []
    for n in wf["nodes"]:
        if target_nodes is not None and n["name"] not in target_nodes:
            continue
        code = n.get("parameters", {}).get("jsCode", "")
        if not code:
            continue
        new_code = code
        for pat, repl in PATTERNS:
            new_code = pat.sub(repl, new_code)
        if new_code != code:
            # mostrar las lineas que cambiaron
            old_lines = code.splitlines()
            new_lines = new_code.splitlines()
            for i, (o, ne) in enumerate(zip(old_lines, new_lines), 1):
                if o != ne:
                    print(f'  [{n["name"]} L{i}]')
                    print(f'    - {o.strip()[:160]}')
                    print(f'    + {ne.strip()[:160]}')
            changes.append((n, new_code))

    if not changes:
        print(f"  [{label}] sin cambios"); return None

    if dry:
        print(f"\n  [{label}] {len(changes)} nodos modificados (dry)"); return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"{label}_PRE_barrido_iri_final_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  backup pre -> {pre}")
    for n, new_code in changes:
        n["parameters"]["jsCode"] = new_code
    res = put_wf(wid, wf); print(f"  PUT {label} OK updatedAt={res.get('updatedAt')}")
    # verify
    wf2 = get_wf(wid)
    remaining = 0
    for n in wf2["nodes"]:
        code = n.get("parameters", {}).get("jsCode", "")
        for pat, _ in PATTERNS:
            if pat.search(code):
                remaining += 1
                break
    print(f"  [verify {label}] {len(changes)} nodos cambiados, {remaining} con 'Iri/Irina' remanente en canned")
    return len(changes)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    for label, (wid, nodes) in WFS.items():
        print(f"\n=== {label} ({wid}) ===")
        apply_to_workflow(label, wid, nodes, dry=not args.apply)


if __name__ == "__main__":
    main()
