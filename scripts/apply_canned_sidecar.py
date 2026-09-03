# -*- coding: utf-8 -*-
"""
apply_canned_sidecar.py — 2026-09-02

BUG REAL QUE ARREGLA (reportado por las secretarias el 2/9, con captura):
  Paulina Villanueva respondio al recordatorio 72h con DOS burbujas seguidas en el
  mismo minuto: "Confirmo" + "Por favor pasame el alias para que te transfiera el
  costo de la primera consulta". El buffer de mensajes las mergeo en UN solo turno
  (fila real en `conversaciones` id=5747: "Confirmo\\nPor favor pasame el alias...").
  Sub-Agent Confirmar confirmo el turno en Dentalink (bien) y respondio SOLO el canned
  de confirmacion — el pedido del alias quedo sin responder. La Dra. lo contesto a mano
  1h38 despues. Segundo caso identico el 28-29/8 (tel 5493885170679).

CAUSA RAIZ (contradiccion entre 2 capas vivas, no "el LLM se olvido"):
  - Router (fix 21/8, caso Salvador Mayans) dice: "manten el intent operativo
    (agendar/cancelar/confirmar_post_recordatorio) — el sub-agent operativo ya sabe
    responder la info canned ADEMAS de ejecutar la accion, en la misma respuesta".
  - Sub-Agent Confirmar dice lo contrario: "si despues de confirmar pregunta otra cosa
    (precio, horario, etc.) -> dejar que el flow lo enrute en el proximo turno" +
    "SOLO responder el canned y FIN".
  Cada capa cree que la otra es duena de la info canned. Cuando el buffer mergea los
  mensajes NO HAY "proximo turno": el pedido se pierde en silencio.

DECISION ESTRUCTURAL (ver memory/decisions.md 2026-09-02):
  En vez de parchear el prompt de Confirmar (whack-a-mole: es exactamente lo que se
  hizo el 21/8 para Agendar y por eso Confirmar quedo afuera), se agrega una CAPA
  DETERMINISTICA TRANSVERSAL en el punto de convergencia de los 7 caminos de salida:

      Fallback Output --> [Canned Sidecar] --> Banlist Validator

  El sidecar lee el texto REAL del paciente (mismo patron que ya usa Banlist Validator
  para la excepcion de direccion), detecta por regex si pidio alias/datos de pago o
  precio, y si la respuesta del sub-agent NO lo contiene ya, lo ANEXA. Nunca modifica
  lo que el sub-agent dijo: solo agrega. Ningun sub-agent necesita saber de canned.

POR QUE ANTES DEL BANLIST (y no despues):
  1. `Split en Mensajes` ya tiene un guard determinista ("si el original traia CBU y el
     formateado lo perdio, usa el original") que lee de `$('Banlist Validator')`. Al
     insertar ANTES, ese guard protege gratis el bloque de alias anexado si el
     Formatting Agent (LLM) lo descarta.
  2. El Banlist inspecciona tambien el texto anexado (defensa en profundidad, regla 5).
  3. `Gate Humano Final` lee de `$('Banlist Validator')` para avisar al grupo que tenia
     listo — asi el aviso incluye lo anexado.

GUARDRAILS (leccion del "blindaje tarde" del 18/8: heuristica sobre datos que NO son
lo que dijo el paciente = falsos positivos peores que el bug):
  1. Inspecciona el TEXTO REAL del paciente, no datos derivados.
  2. Solo dispara con PEDIDO explicito (interrogativo o imperativo), no con menciones
     ("el alias sigue siendo ese" NO dispara).
  3. Evaluacion POR ORACION (mismo patron que arreglo el guard de precios del panel el
     24/8) — un mensaje multilinea con el pedido en la linea 3 igual dispara.
  4. Dedup: si la respuesta ya trae el alias/CBU o un monto, no duplica.
  5. `[NO_REPLY]` y urgencias -> passthrough intacto.
  6. Falso positivo = un bloque de alias de mas (inofensivo). No cambia NUNCA el texto
     que el sub-agent genero.
  7. Los valores (precio) salen del nodo dinamico ya existente `Extraer Horarios y
     Precio` (KB id=21, editable en /servicios). El bloque de datos de cuenta queda
     hardcodeado EXACTAMENTE igual que en el prompt vivo de Sub-Agent General — a
     proposito: dinamizar solo uno de los dos crearia inconsistencia (Raquel edita
     /servicios, el sidecar cambia y General no). Migrar AMBOS a KB id=24 es P2 aparte.

USO:
    python scripts/apply_canned_sidecar.py            # preview + diff (NO toca nada)
    python scripts/apply_canned_sidecar.py --apply    # aplica (backup PRE/POST)

Regla del proyecto: NUNCA --apply sin OK explicito de Lucas + backup previo.
"""
import argparse
import copy
import datetime
import difflib
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import env, require  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

WF_ID = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}

NODE_NAME = "Canned Sidecar"
UPSTREAM = "Fallback Output"
DOWNSTREAM = "Banlist Validator"

# ---------------------------------------------------------------------------
# El codigo del nodo. FUENTE UNICA: tests/test_canned_sidecar.py lo importa de
# aca y lo corre con node real, para que test y produccion no puedan divergir.
# ---------------------------------------------------------------------------
SIDECAR_JS = r"""// Canned Sidecar - 2026-09-02
// Capa deterministica transversal: si el paciente PIDIO info canned (alias/datos de
// pago, precio) y la respuesta del sub-agent no la trae, la ANEXA. Nunca modifica lo
// que el sub-agent genero: solo agrega.
//
// Por que existe: los sub-agents operativos (Confirmar/Cancelar/Agendar) cortan
// despues de ejecutar su accion ("SOLO responder el canned y FIN") asumiendo que un
// pedido extra va a llegar en un TURNO NUEVO que el Router reclasifica. Cuando el
// buffer mergea 2 mensajes rapidos del paciente en una sola ejecucion, no hay proximo
// turno y el pedido se pierde en silencio. Caso real 2/9 (Paulina Villanueva:
// "Confirmo\nPor favor pasame el alias...") y 28/8 (tel ...170679).
//
// Guardrails: ver cabecera de scripts/apply_canned_sidecar.py

const items = $input.all();

// --- 1. texto REAL del paciente (mismo patron que Banlist Validator) ---
let pacienteMsg = '';
try {
  pacienteMsg = ($('Preparar Mensaje Final').first().json.text || '').toString();
} catch (e) {
  pacienteMsg = '';
}
if (!pacienteMsg.trim()) return items;

const stripAccents = s => s.normalize('NFD').replace(/\p{Diacritic}/gu, '');
const norm = s => stripAccents(s).toLowerCase();

// --- 2. partir en ORACIONES (el pedido puede venir en la linea 2 o 3 de un
//        mensaje mergeado; evaluar el texto entero de una da falsos negativos
//        y falsos positivos. Mismo patron que el fix del guard de precios 24/8) ---
const oraciones = [];
for (const bloque of pacienteMsg.split(/\n+/)) {
  const trozos = bloque.match(/[^.!?]+[.!?]*/g) || [bloque];
  for (const t of trozos) if (t.trim()) oraciones.push(norm(t));
}

// El paciente esta PIDIENDO (interrogativo o imperativo), no mencionando.
const PEDIDO = /\?|\bpasame\b|\bme pasas\b|\bme pasa\b|\bmandame\b|\bme manda(s)?\b|\benviame\b|\bme envia(s)?\b|\bdecime\b|\bme dice\b|\bme das\b|\bme da\b|\bnecesito\b|\bquisiera\b|\bquiero saber\b|\bme podes\b|\bme puede(s)?\b|\bpodrias\b|\bpodria\b|\bcual es\b|\bcuales son\b|\bdonde\b|\bcuanto\b|\bcomo hago\b|\bque alias\b|\bpor favor\b|\bme gustaria\b/;

// El paciente ya lo hizo / lo esta afirmando, no lo esta pidiendo.
const YA_HECHO = /\bya (transfer|pagu|abon|deposit|hice)|\bsigue siendo\b|\bes ese\b|\bese es\b|\bacabo de (transferir|pagar|abonar)|\brecien (transferi|pague)\b/;

// --- 3. reglas. `enabled:false` = mecanismo listo pero apagado a proposito:
//        se arranca con lo que fallo de verdad en produccion (plata), y se amplia
//        recien cuando el patron se pruebe en vivo. ---
const REGLAS = [
  {
    key: 'pago',
    enabled: true,
    tema: /\b(alias|cbu|cvu)\b|datos? (de |para )?(la )?(cuenta|transferencia|pago)|transferen|transferir|transfiera|deposit(ar|o)|(donde|adonde|a donde) (le |te |les )?(hago|pago|deposito|transfiero|abono)|como (le )?(pago|abono|puedo pagar|hago el pago)|a que cuenta|numero de cuenta|forma de pago|medios? de pago/,
    // si la respuesta ya trae el alias o el bloque de cuenta, no duplicar
    yaRespondido: /dra\.raquel\.aurea|\bCBU\b/i,
  },
  {
    key: 'precio',
    enabled: true,
    tema: /\b(precio|valor|costo|arancel)\b|cuanto (sale|cuesta|es|vale|debo|tengo que|hay que)/,
    yaRespondido: /\$\s?\d/,
    // el canned de pago ya declara el valor -> no mandar los dos
    supersededBy: 'pago',
  },
  {
    key: 'horarios',
    enabled: false,
    tema: /\bhorario|que dias atienden|a que hora (atienden|abren|cierran)/,
    yaRespondido: /\bhs\b/i,
  },
];

const pedidos = new Set();
for (const o of oraciones) {
  if (!PEDIDO.test(o) || YA_HECHO.test(o)) continue;
  for (const r of REGLAS) {
    if (r.enabled && r.tema.test(o)) pedidos.add(r.key);
  }
}
if (pedidos.size === 0) return items;

// 'pago' pisa a 'precio' (el canned de pago ya incluye el valor)
for (const r of REGLAS) {
  if (r.supersededBy && pedidos.has(r.supersededBy)) pedidos.delete(r.key);
}
if (pedidos.size === 0) return items;

// --- 4. urgencias: nunca meter info comercial en un flujo de dolor ---
let intent = '';
try { intent = ($('Parse Intent').first().json.intent || '').toString(); } catch (e) { intent = ''; }
if (intent === 'urgencia_dolor') return items;

// --- 5. valores. precio: dinamico desde KB id=21 (editable en /servicios).
//        datos de cuenta: identicos al prompt vivo de Sub-Agent General a proposito
//        (dinamizar solo uno de los dos crearia inconsistencia). ---
let precio = '$50.000';
try {
  const p = $('Extraer Horarios y Precio').first().json.precio_consulta;
  if (p && String(p).trim()) precio = String(p).trim();
} catch (e) { /* camino Set NO_REPLY: ese nodo no corrio. fallback. */ }

const TEXTOS = {
  pago: 'El valor de la consulta es de ' + precio + '. Si desea ir abonando, puede hacerlo al siguiente alias:\n---\ndra.raquel.aurea\n---\nTitular: Laura Raquel Rodríguez\nCUIT/CUIL: 27316870118\nCBU: 1430001713001112680016\nNRO. CUENTA: 1300111268001\nBanco: BRUBANK',
  precio: 'El valor de la consulta es de ' + precio + '.',
  horarios: '',
};

// --- 6. anexar por item (respetando dedup y [NO_REPLY]) ---
return items.map(it => {
  const output = (it.json.output || '').toString();
  if (!output.trim() || output.includes('[NO_REPLY]')) return it;

  const aAnexar = [];
  for (const r of REGLAS) {
    if (!pedidos.has(r.key)) continue;
    if (r.yaRespondido && r.yaRespondido.test(output)) continue;  // ya lo contesto el sub-agent
    const txt = TEXTOS[r.key];
    if (txt) aAnexar.push(txt);
  }
  if (aAnexar.length === 0) return it;

  const nuevo = output.trim() + '\n---\n' + aAnexar.join('\n---\n');
  console.log('[CANNED SIDECAR] anexado:', Array.from(pedidos).join(','), '| intent:', intent);
  return { json: { ...it.json, output: nuevo, canned_sidecar: Array.from(pedidos).join(',') } };
});
"""


def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    key = require("N8N_API_KEY")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{base}/api/v1{path}",
        data=data,
        method=method,
        headers={"X-N8N-API-KEY": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def build(wf):
    """Devuelve (nuevo_wf, resumen_cambios). No muta el original."""
    new = copy.deepcopy(wf)
    nodes = new["nodes"]
    names = [n["name"] for n in nodes]
    cambios = []

    if UPSTREAM not in names or DOWNSTREAM not in names:
        sys.exit(f"ERROR: falta {UPSTREAM!r} o {DOWNSTREAM!r} en el workflow")

    up = next(n for n in nodes if n["name"] == UPSTREAM)
    down = next(n for n in nodes if n["name"] == DOWNSTREAM)

    node = {
        "parameters": {"jsCode": SIDECAR_JS},
        "id": "canned-sidecar-v1",
        "name": NODE_NAME,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [
            int((up["position"][0] + down["position"][0]) / 2),
            int(down["position"][1]) + 180,
        ],
    }

    if NODE_NAME in names:
        idx = names.index(NODE_NAME)
        prev = nodes[idx]
        node["position"] = prev.get("position", node["position"])
        node["id"] = prev.get("id", node["id"])
        nodes[idx] = node
        cambios.append(f"ACTUALIZA nodo existente {NODE_NAME!r} (solo el jsCode)")
    else:
        nodes.append(node)
        cambios.append(f"AGREGA nodo {NODE_NAME!r} (Code) en {node['position']}")

    conns = new["connections"]
    esperado = [{"node": DOWNSTREAM, "type": "main", "index": 0}]
    actual = conns.get(UPSTREAM, {}).get("main", [[]])[0]
    if [{"node": c["node"], "type": c["type"], "index": c["index"]} for c in actual] == esperado:
        conns[UPSTREAM]["main"][0] = [{"node": NODE_NAME, "type": "main", "index": 0}]
        conns[NODE_NAME] = {"main": [[{"node": DOWNSTREAM, "type": "main", "index": 0}]]}
        cambios.append(f"REWIRE {UPSTREAM} -> {NODE_NAME} -> {DOWNSTREAM}")
    elif conns.get(NODE_NAME):
        cambios.append("REWIRE ya estaba hecho (idempotente, no se toca)")
    else:
        sys.exit(f"ERROR: conexiones de {UPSTREAM!r} inesperadas: {actual!r}")

    return new, cambios


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="aplica el cambio (PUT)")
    args = ap.parse_args()

    print(f"GET workflow {WF_ID} ...")
    wf = api(f"/workflows/{WF_ID}")
    print(f"  name={wf['name']!r} nodos={len(wf['nodes'])} active={wf.get('active')} updatedAt={wf.get('updatedAt')}")

    new, cambios = build(wf)

    print("\n=== CAMBIOS ===")
    for c in cambios:
        print("  -", c)

    print("\n=== DIFF de conexiones ===")
    a = json.dumps({k: v for k, v in wf["connections"].items() if k in (UPSTREAM, NODE_NAME)}, indent=1, ensure_ascii=False).splitlines()
    b = json.dumps({k: v for k, v in new["connections"].items() if k in (UPSTREAM, NODE_NAME)}, indent=1, ensure_ascii=False).splitlines()
    for line in difflib.unified_diff(a, b, "ANTES", "DESPUES", lineterm="", n=2):
        print(" ", line)

    print(f"\n=== jsCode del nodo ({len(SIDECAR_JS.splitlines())} lineas) ===")
    print("  (ver scripts/apply_canned_sidecar.py :: SIDECAR_JS)")

    hist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workflows", "history")
    os.makedirs(hist, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if not args.apply:
        print("\n[DRY-RUN] no se toco nada. Para aplicar: --apply")
        return

    pre = os.path.join(hist, f"v6_PRE_canned_sidecar_{ts}.json")
    with open(pre, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"\nbackup PRE -> {pre}")

    payload = {k: new[k] for k in PUT_KEYS if k in new}
    if "settings" in payload:
        payload["settings"] = {k: v for k, v in payload["settings"].items() if k in SETTINGS_OK}

    print("PUT ...")
    api(f"/workflows/{WF_ID}", method="PUT", payload=payload)

    after = api(f"/workflows/{WF_ID}")
    post = os.path.join(hist, f"v6_POST_canned_sidecar_{ts}.json")
    with open(post, "w", encoding="utf-8") as f:
        json.dump(after, f, ensure_ascii=False, indent=2)
    print(f"backup POST -> {post}")

    ok_node = any(n["name"] == NODE_NAME for n in after["nodes"])
    ok_wire = after["connections"].get(UPSTREAM, {}).get("main", [[{}]])[0][0].get("node") == NODE_NAME
    ok_down = after["connections"].get(NODE_NAME, {}).get("main", [[{}]])[0][0].get("node") == DOWNSTREAM
    print(f"\nverificacion: nodo={ok_node} wire_in={ok_wire} wire_out={ok_down} nodos={len(after['nodes'])}")
    if not (ok_node and ok_wire and ok_down):
        sys.exit("ERROR: la verificacion post-PUT fallo — revisar en la UI")
    print("OK.")


if __name__ == "__main__":
    main()
