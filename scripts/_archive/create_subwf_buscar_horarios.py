"""
Crea el sub-workflow "Sub-WF - Buscar Horarios Validado".

Resuelve la alucinacion del caso 30/06: el toolHttpRequest buscar_horarios no
le exponia bien el param `fecha` al LLM (mandaba query vacio) -> Dentalink
devolvia slots genericos -> el LLM alucinaba "no hay para esa fecha".

Este sub-WF:
  1. Recibe `fecha` (input explicito del trigger, expuesto al LLM via toolWorkflow)
  2. Valida formato YYYY-MM-DD + que sea futura y dentro de 1 año
  3. Si invalida -> devuelve ERROR_FECHA legible (el LLM pide fecha al paciente)
  4. Si valida -> llama Dentalink con esa fecha -> devuelve slots o "sin turnos para [fecha]"

NO toca el v6 todavia (crear workflow nuevo no afecta produccion).
El cambio del tool en v6 se hace en un segundo script tras validar este aislado.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
HEADERS = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
DENTALINK_CRED_ID = "TwN6eBWsydjMdsCM"  # Header Auth account 3

VALIDAR_FECHA_JS = r"""// Valida la fecha recibida del LLM antes de pegarle a Dentalink.
const input = $input.first().json;
const fecha = String(input.fecha ?? input.query?.fecha ?? '').trim();
const formatoOk = /^\d{4}-\d{2}-\d{2}$/.test(fecha);
let esRazonable = false;
if (formatoOk) {
  const d = new Date(fecha + 'T00:00:00');
  const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
  const limite = new Date(hoy); limite.setFullYear(limite.getFullYear() + 1);
  esRazonable = !isNaN(d.getTime()) && d >= hoy && d <= limite;
}
return [{ json: { fecha, valida: (formatoOk && esRazonable), formatoOk, esRazonable } }];
"""

FORMAT_SLOTS_JS = r"""// Formatea los slots de Dentalink en algo legible para el LLM.
const resp = $input.first().json;
const fecha = $('Validar fecha').first().json.fecha;
let slots = [];
try {
  const data = resp.data ?? resp;
  slots = Array.isArray(data) ? data : (data.data ?? []);
} catch (e) { slots = []; }

if (!slots.length) {
  return [{ json: { resultado: `Sin turnos disponibles para el ${fecha}. Si el paciente necesita, ofrecele buscar otra fecha cercana (llamando esta tool de nuevo con esa otra fecha). NO inventes turnos.` } }];
}
const lista = slots
  .map(s => ({ fecha: s.fecha, hora_inicio: s.hora_inicio, hora_fin: s.hora_fin }))
  .slice(0, 20);
return [{ json: { resultado: `Turnos disponibles para ${fecha}: ` + JSON.stringify(lista), total: lista.length, fecha } }];
"""

OUTPUT_ERROR_JS = r"""// Fecha invalida: devolver instruccion clara al LLM. NO alucinar.
const v = $('Validar fecha').first().json;
return [{ json: { resultado: `ERROR_FECHA: el parametro 'fecha' es OBLIGATORIO y debe ser una fecha YYYY-MM-DD valida, futura y dentro de 1 año. Recibido: "${v.fecha}". NO afirmes que no hay turnos: pedile al paciente una fecha concreta (que dia prefiere) y volve a llamar esta tool con esa fecha en formato YYYY-MM-DD.` } }];
"""

DENTALINK_URL = (
    "={{ 'https://api.dentalink.healthatom.com/api/v1/agendas/?q={\"id_sucursal\":{\"eq\":1},"
    "\"fecha\":{\"eq\":\"' + $json.fecha + '\"},\"duracion\":{\"eq\":40},\"id_dentista\":{\"eq\":1}}' }}"
)


def build_workflow() -> dict:
    nodes = [
        {
            "parameters": {
                "inputSource": "jsonExample",
                "jsonExample": json.dumps({"fecha": "2026-06-30"}),
            },
            "id": "trigger",
            "name": "Cuando llama Agendar",
            "type": "n8n-nodes-base.executeWorkflowTrigger",
            "typeVersion": 1.1,
            "position": [0, 300],
        },
        {
            "parameters": {"jsCode": VALIDAR_FECHA_JS},
            "id": "validar",
            "name": "Validar fecha",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [220, 300],
        },
        {
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                    "conditions": [
                        {
                            "id": "cond1",
                            "leftValue": "={{ $json.valida }}",
                            "rightValue": True,
                            "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                        }
                    ],
                    "combinator": "and",
                },
                "options": {},
            },
            "id": "ifvalida",
            "name": "Fecha valida?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [440, 300],
        },
        {
            "parameters": {
                "url": DENTALINK_URL,
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "options": {},
            },
            "id": "getdent",
            "name": "GET Horarios Dentalink",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [660, 200],
            "alwaysOutputData": True,
            "continueOnFail": True,
            "credentials": {"httpHeaderAuth": {"id": DENTALINK_CRED_ID, "name": "Header Auth account 3"}},
        },
        {
            "parameters": {"jsCode": FORMAT_SLOTS_JS},
            "id": "format",
            "name": "Format Slots",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [880, 200],
        },
        {
            "parameters": {"jsCode": OUTPUT_ERROR_JS},
            "id": "outerr",
            "name": "Output Error",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [660, 420],
        },
    ]

    connections = {
        "Cuando llama Agendar": {"main": [[{"node": "Validar fecha", "type": "main", "index": 0}]]},
        "Validar fecha": {"main": [[{"node": "Fecha valida?", "type": "main", "index": 0}]]},
        "Fecha valida?": {
            "main": [
                [{"node": "GET Horarios Dentalink", "type": "main", "index": 0}],  # true
                [{"node": "Output Error", "type": "main", "index": 0}],  # false
            ]
        },
        "GET Horarios Dentalink": {"main": [[{"node": "Format Slots", "type": "main", "index": 0}]]},
    }

    return {
        "name": "Sub-WF - Buscar Horarios Validado",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
    }


def main():
    dry = "--dry" in sys.argv
    wf = build_workflow()

    if dry:
        print(json.dumps(wf, indent=2, ensure_ascii=False))
        return

    r = requests.post(f"{BASE}/api/v1/workflows", headers=HEADERS, json=wf, timeout=30)
    if not r.ok:
        print("CREATE failed:", r.status_code, r.text[:800], file=sys.stderr)
        r.raise_for_status()
    created = r.json()
    wf_id = created.get("id")
    print(f"Created workflow id={wf_id} name={created.get('name')!r}")
    print(f"\n>>> SUB_WF_BUSCAR_HORARIOS_ID = {wf_id} <<<")
    # Save id for next step
    (ROOT / "scripts" / ".buscar_horarios_subwf_id").write_text(wf_id, encoding="utf-8")


if __name__ == "__main__":
    main()
