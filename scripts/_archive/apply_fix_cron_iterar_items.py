"""URGENTE - Cron recordatorios nodo 'Guardar en Chat Memory': el codigo usa
$('Preparar mensaje').item.json que SOLO toma el primer item. Si el cron procesa
5 pacientes, solo el primero queda en n8n_chat_histories. Los otros 4 reciben
WhatsApp pero el bot pierde contexto.

Caso real 03/06: 5 recordatorios enviados, solo Evelina (primer item) en memoria.
Brenda/Samanta/Helena/Benjamin sin contexto -> Samanta respondio sin recordatorio
en memoria igual que Lautaro ayer.

Fix: reemplazar codigo por uno que itere sobre items[] y acumule en results.

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
WF_ID = "7RqTApkvVavRmq3R"; H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
NODE = "Guardar en Chat Memory"

NEW_CODE = r"""// FORMATO LANGCHAIN v0.3 (flat, sin wrapper 'data')
// FIX 2026-06-02: strings literales con \n sin escapar rompian el parse JS.
// FIX 2026-06-03: el codigo solo procesaba el primer item. Ahora itera items[].
const dias = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
const meses = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"];

const results = [];
for (const item of items) {
  const prep = item.json;
  const phone = prep.phone;
  const message = prep.message;
  if (!phone || !message) {
    results.push({ json: { saved: false, reason: 'no phone or message', skipped_phone: phone || null } });
    continue;
  }
  const cita_id = prep.cita_id || '';
  const fecha = prep.fecha || '';
  const hora = prep.hora || '';
  const tipo = prep.tipo_recordatorio || '';
  const nombre = prep.nombre || '';
  const dentista = prep.dentista || 'Rodríguez Raquel';
  const idPaciente = prep.id_paciente || '';

  let fechaNatural = fecha;
  if (fecha) {
    const f = new Date(fecha + 'T00:00:00');
    fechaNatural = dias[f.getDay()] + ' ' + f.getDate() + ' de ' + meses[f.getMonth()] + ' de ' + f.getFullYear();
  }

  // Mensaje 1: el recordatorio tal cual se envio al paciente, tageado como AI con source reminder_note
  const msgRecordatorio = JSON.stringify({
    type: 'ai',
    content: message,
    tool_calls: [],
    additional_kwargs: { source: 'reminder_note' },
    response_metadata: {},
    invalid_tool_calls: []
  });

  // Mensaje 2: NOTA INTERNA con datos estructurados del turno (para que el bot tenga contexto sin pedir)
  const internalNote = `[NOTA INTERNA - contexto del último recordatorio enviado, NO mencionar al paciente]
Acabo de enviar un recordatorio ${tipo} del siguiente turno:
- Cita Dentalink ID: ${cita_id}
- ID Paciente: ${idPaciente}
- Paciente: ${nombre}
- Fecha: ${fechaNatural}
- Hora: ${hora}
- Profesional: Dra. ${dentista}
Si el paciente responde sobre este turno, ya conocés todos los datos. NO le pidas que repita fecha/hora/profesional.`;

  const msgInternal = JSON.stringify({
    type: 'ai',
    content: internalNote,
    tool_calls: [],
    additional_kwargs: { source: 'reminder_note' },
    response_metadata: {},
    invalid_tool_calls: []
  });

  results.push({ json: { session_id: phone, message_json: msgRecordatorio, saved: true } });
  results.push({ json: { session_id: phone, message_json: msgInternal, saved: true } });
}
return results;
"""


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
    n = next((x for x in wf["nodes"] if x["name"] == NODE), None)
    if not n: print(f"!! '{NODE}' no encontrado"); sys.exit(2)
    js = n["parameters"].get("jsCode", "")
    if "FIX 2026-06-03: el codigo solo procesaba el primer item" in js:
        print("!! ya aplicado"); sys.exit(3)
    print(f"{NODE}: {len(js)} -> {len(NEW_CODE)} chars (delta {len(NEW_CODE)-len(js):+d})")
    if args.dry or not args.apply: print("[dry] no aplicado."); return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"cron_PRE_iterar_items_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(get_wf(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup pre -> {pre}")
    n["parameters"]["jsCode"] = NEW_CODE
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")
    wf2 = get_wf()
    n2 = next(x for x in wf2["nodes"] if x["name"] == NODE)
    ok = "FIX 2026-06-03" in n2["parameters"].get("jsCode", "")
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
