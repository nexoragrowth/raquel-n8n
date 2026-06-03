"""Fix dia de semana en el sub-WF Buscar Horarios Validado (GuDQ9VmKWZvQnerV).
El nodo 'Format Slots' ahora calcula el dia de la semana en JS (deterministico)
y le pasa al LLM la fecha ya armada "Jueves 18 de Junio 10:30 hs" para que solo la copie.

Modos: --dry (muestra) / --apply (backup + PUT + verify)."""
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
WF_ID = "GuDQ9VmKWZvQnerV"; H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
NODE = "Format Slots"

NEW_CODE = r"""// Formatea slots de Dentalink. Distingue fecha EXACTA pedida vs proximos.
// El DIA DE LA SEMANA se calcula ACA (deterministico). El LLM NO debe calcularlo.
const resp = $input.first().json;
const fechaPedida = $('Validar fecha').first().json.fecha; // YYYY-MM-DD
let slots = [];
try {
  const data = resp.data ?? resp;
  slots = Array.isArray(data) ? data : (data.data ?? []);
} catch (e) { slots = []; }

if (!slots.length) {
  return [{ json: { resultado: `No hay turnos disponibles desde el ${fechaPedida} en adelante. Ofrecele al paciente buscar otra fecha mas adelante o escalar a la secretaria. NO inventes turnos.` } }];
}

const DIAS = ['Domingo','Lunes','Martes','Miercoles','Jueves','Viernes','Sabado'];
const MESES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
function fmt(fechaDMY, horaInicio) {
  const [dd, mm, yy] = String(fechaDMY).split('/').map(Number);
  const d = new Date(yy, mm - 1, dd); // componentes locales: el dia de semana de una fecha no depende de TZ
  const dia = DIAS[d.getDay()];
  const hhmm = String(horaInicio).slice(0, 5);
  return `${dia} ${dd} de ${MESES[mm - 1]} ${hhmm} hs`;
}

// Dentalink devuelve fecha en DD/MM/YYYY. Convertir la pedida para comparar.
const [yy, mm, dd] = fechaPedida.split('-');
const fechaPedidaDMY = `${dd}/${mm}/${yy}`;

const enFechaPedida = slots.filter(s => s.fecha === fechaPedidaDMY).map(s => fmt(s.fecha, s.hora_inicio));
const proximos = slots.slice(0, 6).map(s => fmt(s.fecha, s.hora_inicio));

let resultado;
if (enFechaPedida.length) {
  resultado = `Turnos disponibles (el dia de la semana YA esta calculado y es correcto - copialos EXACTO, NO recalcules el dia): ${JSON.stringify(enFechaPedida)}. Ofrecele estos horarios directamente. NO le pidas que proponga otra fecha.`;
} else {
  resultado = `El ${fechaPedidaDMY} NO tiene turnos disponibles. Los proximos turnos reales (el dia de la semana YA esta calculado y es correcto - copialos EXACTO, NO recalcules el dia): ${JSON.stringify(proximos)}. Ofrecele 2-3 directamente. NO afirmes que son del ${fechaPedidaDMY}. NO le pidas al paciente que proponga otra fecha: ofrecele vos estos.`;
}
return [{ json: { resultado, total: slots.length } }];
"""


def get_wf():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=40); r.raise_for_status(); return r.json()


def put_wf(wf):
    allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution",
               "executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": settings, "staticData": wf.get("staticData")}
    r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, json=body, timeout=40)
    if not r.ok: print("PUT FAIL", r.status_code, r.text[:400], file=sys.stderr); r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    wf = get_wf()
    node = next((n for n in wf["nodes"] if n["name"] == NODE), None)
    if not node: print(f"!! no existe nodo {NODE!r}"); sys.exit(2)
    old = node["parameters"].get("jsCode", "")
    print(f"=== {NODE}: jsCode {len(old)} -> {len(NEW_CODE)} chars ===")
    if args.dry or not args.apply:
        print(NEW_CODE); print("\n[dry] no aplicado."); return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"buscar_horarios_PRE_fix_dia_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup pre -> {pre}")
    node["parameters"]["jsCode"] = NEW_CODE
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")
    wf2 = get_wf()
    n2 = next(n for n in wf2["nodes"] if n["name"] == NODE)
    print("[verify]", "OK" if n2["parameters"]["jsCode"] == NEW_CODE else "FAIL")


if __name__ == "__main__":
    main()
