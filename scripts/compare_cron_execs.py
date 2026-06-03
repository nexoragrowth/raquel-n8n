"""
Compara ejecucion del cron Recordatorios real anterior (33625, 25/5 11AM UTC,
pre-cambios) vs dry-run actual (36124, 26/5 03:35 UTC).

Objetivos:
- Validar que la estructura de los nodos comunes es la misma
- Chequear si el warning 'Token undefined' del Postgres - Insert Memory ya
  existia en el cron original (probable bug pre-existente)
- Ver cuantos items procesaba el cron real anterior
"""
import json
import sys
import io
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json"}

EXECS = [
    ("33625 — cron real 25/5 11:00 UTC (pre-cambios)", 33625),
    ("36124 — dry-run 26/5 03:35 UTC (post-cambios, send disabled)", 36124),
]

for label, eid in EXECS:
    print(f"\n{'='*80}\nEXEC {label}\n{'='*80}")
    d = requests.get(f"{N8N}/api/v1/executions/{eid}?includeData=true",
                     headers=H, timeout=30).json()
    rd = d.get("data", {}).get("resultData", {}).get("runData", {})
    print(f"status: {d.get('status')}")
    print(f"last_node: {d.get('data', {}).get('resultData', {}).get('lastNodeExecuted')}")
    print(f"nodos ejecutados ({len(rd)}):")
    for nname, runs in rd.items():
        n_items = 0
        n_errors = 0
        for run in runs:
            main = run.get("data", {}).get("main", [])
            if main:
                for branch in main:
                    if branch:
                        n_items += len(branch)
            if run.get("error"):
                n_errors += 1
        print(f"  - {nname}: {len(runs)} run(s), {n_items} items total, errors: {n_errors}")

    # Detalle de Postgres - Insert Memory en ambos
    pim = rd.get("Postgres - Insert Memory", [])
    if pim:
        print(f"\n  Postgres - Insert Memory detalle:")
        for i, run in enumerate(pim[:3]):
            err = run.get("error", {})
            if err:
                print(f"    run {i} ERROR:")
                print(f"      message: {err.get('message', '')[:200]}")
                print(f"      description: {err.get('description', '')[:200]}")
            else:
                main = run.get("data", {}).get("main", [])
                if main and main[0]:
                    item = main[0][0].get("json", {})
                    print(f"    run {i} OK: keys={list(item.keys())[:10]}")

    # Insert recordatorios_enviados (solo en 36124)
    ire = rd.get("Insert recordatorios_enviados", [])
    if ire:
        print(f"\n  Insert recordatorios_enviados runs: {len(ire)}")
        for i, run in enumerate(ire[:3]):
            err = run.get("error", {})
            main = run.get("data", {}).get("main", [])
            if err:
                print(f"    run {i} ERROR: {err.get('message', '')[:200]}")
            elif main and main[0]:
                item = main[0][0].get("json", {})
                print(f"    run {i} OK: id={item.get('id')} cita={item.get('id_cita_dentalink')} pac={item.get('nombre_paciente')}")
