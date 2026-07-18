"""Cobertura total memoria v6 main: 4 cambios en un solo round.

CONTEXTO DEL DIAGNOSTICO (workflow w26h6ij0g, 03/06/2026 PM):
- Los 5 Sub-Agents (Confirmar/Cancelar/Agendar/Urgencia/General) SI escriben a memoria
  via LangChain Postgres Chat Memory (auto-save).
- Sub-WF Cancelar TIENE su propio writeback en Step 8c (descubierto post-fix matinal).
- GAPS CRITICOS:
  1) Banlist Validator reemplazo NO se guarda - memoria queda con output prohibido (escenario Mariela).
  2) Gate Error Tecnico canned NO se guarda - memoria queda con error string crudo.
  3) Path corto (<=80 chars) saltea Banlist - sin defensa.
  4) Router persiste tokens de intent como AI msg - contaminacion.
  5) Mi nodo "Save Sub-WF Output to Memory" de esta manana es DUPLICACION con Step 8c.

CAMBIOS:
A. REVERTIR nodo "Save Sub-WF Output to Memory" (de la manana 15:05 UTC) + restaurar edge
   Format Sub-WF Output -> Fallback Output.
B. AGREGAR nodo "Reconcile Memory Post-Banlist" despues de "Gate Error Tecnico", antes de
   "Tiene respuesta?". UPDATE ultima fila AI del session_id con el output efectivamente
   enviado (post-banlist post-gate post-formatting).
C. RE-WIREAR Banlist Validator para que cubra TAMBIEN el path corto. Nueva estructura:
   Fallback Output -> Banlist Validator -> Necesita Formatting? -> [Formatting | directo] -> Split.
D. DESCONECTAR ai_memory edge desde Postgres Chat Memory hacia Router - Clasificar Intent.
   El Router clasifica con el mensaje actual + system prompt, no necesita historia. Quita
   el ruido de tokens de intent en memoria.

Modo: --dry / --apply
"""
from __future__ import annotations
import argparse, json, os, sys, io, copy
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
WF_ID = "O155MqHgOSaNZ9ye"; H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}


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

    changes_summary = []
    nodes_by_name = {n["name"]: n for n in wf["nodes"]}
    conn = wf["connections"]

    # ============================================================
    # CAMBIO A: REVERTIR Save Sub-WF Output to Memory (es duplicacion)
    # ============================================================
    save_node = nodes_by_name.get("Save Sub-WF Output to Memory")
    if save_node:
        # Restaurar edge: Format Sub-WF Output -> Fallback Output (saltando Save Sub-WF)
        # Antes: Format Sub-WF Output -> Save Sub-WF Output to Memory -> Fallback Output
        save_targets = conn.get("Save Sub-WF Output to Memory", {}).get("main", [[]])[0]
        if save_targets:
            conn["Format Sub-WF Output"] = {"main": [save_targets]}
            print(f"[A] Edge restaurado: Format Sub-WF Output -> {[t['node'] for t in save_targets]}")
        # Eliminar el nodo
        wf["nodes"] = [n for n in wf["nodes"] if n["name"] != "Save Sub-WF Output to Memory"]
        # Eliminar conexiones del nodo
        if "Save Sub-WF Output to Memory" in conn:
            del conn["Save Sub-WF Output to Memory"]
        changes_summary.append("A: REVERTIDO nodo 'Save Sub-WF Output to Memory' (duplicacion con Sub-WF Step 8c)")
    else:
        print("[A] nodo 'Save Sub-WF Output to Memory' no existe, skip")

    # ============================================================
    # CAMBIO B: AGREGAR "Reconcile Memory Post-Banlist"
    # Entre "Gate Error Tecnico" y "Tiene respuesta?"
    # ============================================================
    reconcile_name = "Reconcile Memory Post-Banlist"
    if reconcile_name not in nodes_by_name:
        gate = nodes_by_name.get("Gate Error Tecnico")
        if not gate:
            print("[B] !! Gate Error Tecnico no encontrado, skip"); sys.exit(2)
        pg_ref = next((n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.postgres"), None)
        creds = pg_ref.get("credentials", {}) if pg_ref else {}

        # Query UPDATE: actualiza el content del ultimo AIMessage del session_id con el output efectivamente enviado
        # Tambien marca additional_kwargs.source='wa_outbound' y reconciled=true.
        # WHERE clause evita tocar filas que ya tienen source!=NULL (Step 8c del Sub-WF las marca source='wa_outbound')
        # para no pisar dobles writes.
        update_query = (
            "UPDATE n8n_chat_histories "
            "SET message = jsonb_set("
            "jsonb_set(message, '{content}', to_jsonb($1::text)), "
            "'{additional_kwargs}', '{\"source\":\"wa_outbound\",\"reconciled\":true}'::jsonb) "
            "WHERE id = ("
            "SELECT id FROM n8n_chat_histories "
            "WHERE session_id = $2 "
            "AND message->>'type' = 'ai' "
            "AND (message->'additional_kwargs'->>'source') IS NULL "
            "ORDER BY id DESC LIMIT 1"
            ")"
        )
        reconcile_node = {
            "id": "reconcile-mem-post-banlist",
            "name": reconcile_name,
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [gate["position"][0] + 220, gate["position"][1] + 100],
            "parameters": {
                "operation": "executeQuery",
                "query": update_query,
                "options": {
                    "queryReplacement": "={{ $json.message }}, ={{ $('Edit Fields - Extraer Datos').first().json.phone }}",
                },
            },
            "credentials": creds,
            "onError": "continueRegularOutput",  # importante: si UPDATE falla, NO frena el envio al paciente
        }
        wf["nodes"].append(reconcile_node)

        # Rewire: Gate Error Tecnico -> Reconcile -> Tiene respuesta?
        gate_outs = conn.get("Gate Error Tecnico", {}).get("main", [[]])
        # Gate puede tener multiples outputs; tomamos el principal (output 0)
        if gate_outs and gate_outs[0]:
            original_targets = list(gate_outs[0])
            conn["Gate Error Tecnico"]["main"][0] = [{"node": reconcile_name, "type": "main", "index": 0}]
            conn[reconcile_name] = {"main": [original_targets]}
            print(f"[B] Agregado '{reconcile_name}' entre Gate Error Tecnico y {[t['node'] for t in original_targets]}")
            changes_summary.append(f"B: AGREGADO '{reconcile_name}' (UPDATE memoria con output post-banlist/gate)")
        else:
            print("[B] !! Gate Error Tecnico sin outputs main, skip")
    else:
        print(f"[B] '{reconcile_name}' ya existe, skip")

    # ============================================================
    # CAMBIO C: Mover Banlist Validator antes de Necesita Formatting?
    # Hoy:    Fallback Output -> Necesita Formatting? -> [Formatting Agent -> Banlist Validator -> Split | Split]
    # Quiero: Fallback Output -> Banlist Validator -> Necesita Formatting? -> [Formatting Agent -> Split | Split]
    # ============================================================
    banlist = nodes_by_name.get("Banlist Validator")
    necesita = nodes_by_name.get("Necesita Formatting?")
    fallback = nodes_by_name.get("Fallback Output")
    fmt_agent = nodes_by_name.get("Formatting Agent - WhatsApp")
    if all([banlist, necesita, fallback, fmt_agent]):
        # 1. Fallback Output -> Banlist Validator (en vez de -> Necesita Formatting?)
        # 2. Banlist Validator -> Necesita Formatting?
        # 3. Formatting Agent - WhatsApp -> Split en Mensajes (en vez de -> Banlist Validator)
        old_fallback_outs = conn.get("Fallback Output", {}).get("main", [[]])[0]
        if any(t["node"] == "Necesita Formatting?" for t in old_fallback_outs):
            conn["Fallback Output"]["main"][0] = [{"node": "Banlist Validator", "type": "main", "index": 0}]
            conn["Banlist Validator"] = {"main": [[{"node": "Necesita Formatting?", "type": "main", "index": 0}]]}
            # Formatting Agent ahora va a Split en Mensajes directo
            conn["Formatting Agent - WhatsApp"] = {"main": [[{"node": "Split en Mensajes", "type": "main", "index": 0}]]}
            print("[C] Rewire Banlist: Fallback -> Banlist -> Necesita Formatting? -> [Formatting Agent | Split]")
            changes_summary.append("C: MOVIDO Banlist Validator antes de Formatting (cubre path corto)")
        else:
            print("[C] Fallback Output ya no apunta a Necesita Formatting? (capaz ya aplicado), skip")
    else:
        missing = [n for n,v in [("Banlist Validator",banlist),("Necesita Formatting?",necesita),("Fallback Output",fallback),("Formatting Agent - WhatsApp",fmt_agent)] if not v]
        print(f"[C] !! nodos faltantes: {missing}, skip")

    # ============================================================
    # CAMBIO D: Desconectar Router del Postgres Chat Memory (ai_memory edge)
    # Hoy: Postgres Chat Memory -> ai_memory -> Router - Clasificar Intent
    # Quiero: eliminar esa connection
    # ============================================================
    pcm_outs = conn.get("Postgres Chat Memory", {})
    ai_mem = pcm_outs.get("ai_memory", [])
    new_ai_mem = []
    removed = []
    for grp in ai_mem:
        new_grp = []
        for c in grp:
            if c["node"] == "Router - Clasificar Intent":
                removed.append(c)
            else:
                new_grp.append(c)
        if new_grp:
            new_ai_mem.append(new_grp)
    if removed:
        pcm_outs["ai_memory"] = new_ai_mem
        print(f"[D] Desconectado ai_memory: Postgres Chat Memory -X-> Router")
        changes_summary.append("D: DESCONECTADO Router del Postgres Chat Memory (frena ruido tokens intent)")
    else:
        print("[D] Router no estaba conectado a ai_memory (capaz ya aplicado), skip")

    # ============================================================
    # Summary + apply
    # ============================================================
    print("\n=== RESUMEN CAMBIOS ===")
    for s in changes_summary:
        print(f"  - {s}")
    if not changes_summary:
        print("  !! nada que cambiar (probable ya aplicado)"); return

    if args.dry or not args.apply:
        print(f"\n[dry] {len(changes_summary)} cambios listos. No aplicado."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_memoria_coverage_total_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(get_wf(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup pre -> {pre}")
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")

    # Verify
    wf2 = get_wf()
    nm2 = {n["name"]: n for n in wf2["nodes"]}
    cn2 = wf2["connections"]
    ok_A = "Save Sub-WF Output to Memory" not in nm2
    ok_B = "Reconcile Memory Post-Banlist" in nm2
    ok_C = "Banlist Validator" in [t["node"] for t in cn2.get("Fallback Output", {}).get("main", [[]])[0]]
    ok_D = "Router - Clasificar Intent" not in [c["node"] for grp in cn2.get("Postgres Chat Memory", {}).get("ai_memory", []) for c in grp]
    print(f"[verify] A revert Save Sub-WF: {'OK' if ok_A else 'FAIL'}")
    print(f"[verify] B nodo Reconcile creado: {'OK' if ok_B else 'FAIL'}")
    print(f"[verify] C Banlist antes Formatting: {'OK' if ok_C else 'FAIL'}")
    print(f"[verify] D Router desconectado: {'OK' if ok_D else 'FAIL'}")
    if not all([ok_A, ok_B, ok_C, ok_D]): sys.exit(3)


if __name__ == "__main__":
    main()
