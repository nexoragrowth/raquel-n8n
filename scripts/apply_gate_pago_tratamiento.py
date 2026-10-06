# -*- coding: utf-8 -*-
"""
apply_gate_pago_tratamiento.py — 2026-09-03

PEDIDO REAL de la Dra. Raquel (3/9, WhatsApp a Lucas): "pago de consulta no es lo
mismo que pago de tratamiento. Cuando consulten por lo último, derivamelo a mi."

CASO REAL QUE LO DISPARO (exec 269717, confirmado con `conversaciones` id=5944-5945,
tel 5493885864407, "Carla y Tadeo Gordillo"): la mama pregunto "si puedo ese lunes
abonar el tratamiento de Tadeo?" y el bot respondio con el canned de "pago el dia de
la consulta" (agregado 21/8, `apply_fix_pago_dia_consulta.py`) — que habla del valor
FIJO de la consulta ($50.000), sin relacion con el tratamiento de ortodoncia en curso
de Tadeo (que se paga en cuotas negociadas, "Quiere realizar el pago en 1, 3 o 5
pagos?" fue la respuesta REAL de la Dra. cuando tuvo que corregir a mano el error del
bot 2 minutos despues). Causa raiz: ese canned dispara con cualquier "puedo pagar tal
dia" sin chequear si el sustantivo es CONSULTA (su alcance real) o TRATAMIENTO. Misma
familia de confusion que ya tuvo un fix el 7/8 (consulta/cuota/control,
REGLA DESAMBIGUACION CUOTA) — la leccion de esa vez es que un carve-out solo-de-prompt
para este tipo de casi-sinonimos ya reincidio una vez, por eso se agrega tambien una
capa deterministica (regla dura del proyecto #5: cada regla critica en >=2 capas).

FIX EN 2 CAPAS:

  Capa 1 (prompt) — Sub-Agent General, bloque INFO CANNED "puedo pagar el dia de la
  consulta": se antepone un carve-out explicito — si la pregunta menciona
  "tratamiento" (o un tratamiento con nombre), NO usar ese canned, escalar directo.
  Mismo estilo que la REGLA DESAMBIGUACION CUOTA del 7/8.

  Capa 2 (gate deterministico) — nodo Code nuevo `Gate Pago Tratamiento`, insertado
  DESPUES del `Canned Sidecar` (2/9) y ANTES de `Banlist Validator`:
  Fallback Output -> Canned Sidecar -> Gate Pago Tratamiento -> Banlist Validator
  Lee el texto REAL del paciente (mismo patron que Sidecar/Banlist), detecta por
  regex "tratamiento" + palabra de pago en la MISMA oracion, y si la respuesta actual
  NO menciona ya "tratamiento" (senal de que el sub-agent no reconocio el tema),
  la REEMPLAZA por escalacion — a diferencia del Sidecar (que solo ANEXA, nunca
  corrige), este gate SI reemplaza, porque el bug es una respuesta activamente
  incorrecta, no informacion faltante. Dispara `escalar_a_secretaria` via el mismo
  webhook `notify-grupo` (POST simple, confirmado leyendo la tool real — mismo
  patron que ya usa `Gate Error Tecnico` para su propia escalacion).

  Por que el gate corre DESPUES del Sidecar y no antes: si el mensaje trae ademas un
  pedido de alias/precio, el Sidecar los anexa primero, pero esta regla de negocio es
  mas critica (pedido EXPLICITO y reciente de la Dra) y tiene la ULTIMA palabra —
  descarta cualquier anexo del Sidecar y fuerza la escalacion completa.

USO:
    python scripts/apply_gate_pago_tratamiento.py            # preview + diff
    python scripts/apply_gate_pago_tratamiento.py --apply    # aplica (backup PRE/POST)

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

# =============================================================================
# CAPA 1 — prompt de Sub-Agent General. OLD extraido byte-a-byte del prompt vivo
# (ver scratchpad de la sesion) — si no matchea EXACTO 1 vez, el script frena solo.
# =============================================================================
GENERAL_OLD = (
    '- **¿Puedo pagar el día de la consulta / al llegar / en el momento?** (NUEVO 2026-08-21, '
    'pedido Dra — evita que el paciente crea que puede pagar recien al llegar y despues falte '
    'sin avisar): si el paciente pregunta ESPECIFICAMENTE si puede pagar el mismo día, al '
    'llegar, o en el momento de la consulta (ANTES de tener turno reservado, o como pregunta '
    'suelta) -> responder LITERAL, SIN mencionar el alias todavia en esta respuesta:\n'
    '"Nosotros le enviamos un recordatorio de su turno dos días hábiles antes, y para confirmar '
    'su asistencia le solicitaremos abonar el valor de la consulta. Puede acercarse al '
    'consultorio a abonar en efectivo o hacer una transferencia, cómo le resulte más cómodo 😊."\n'
    'Esta respuesta reemplaza el canned generico de alias en este caso puntual — el alias/CBU '
    'se dan recien cuando el paciente ya tiene turno reservado o los pide explicitamente (ver '
    'bullet siguiente).\n\n'
)

GENERAL_NEW = (
    '- **¿Puedo pagar el día de la consulta / al llegar / en el momento?** (NUEVO 2026-08-21, '
    'pedido Dra — evita que el paciente crea que puede pagar recien al llegar y despues falte '
    'sin avisar; ACTUALIZADO 2026-09-03 pedido Dra, caso real Carla/Tadeo — pago de CONSULTA y '
    'pago de TRATAMIENTO NO son lo mismo):\n'
    '  - **Si la pregunta menciona "tratamiento", "cuota" (los pacientes confunden ambas '
    'palabras, ver REGLA DESAMBIGUACIÓN CUOTA arriba), o un tratamiento con nombre: brackets, '
    'ortodoncia, alineadores, aparato -> NO uses este canned.** El pago de tratamiento es una '
    'negociación personalizada (monto, cuotas) que maneja SOLO la Dra. Raquel — nunca un canned '
    'fijo. Llamá `escalar_a_secretaria` con resumen tipo "Paciente <nombre> pregunta si puede '
    'abonar el TRATAMIENTO el <día mencionado>. Coordinar forma de pago/cuotas con la Dra." y '
    'responder: "El pago del tratamiento lo coordina directamente la Dra. Raquel. Le paso su '
    'consulta para que se comunique con usted."\n'
    '  - Si la pregunta es sobre pagar la CONSULTA (sin mencionar tratamiento) y el paciente '
    'pregunta ESPECIFICAMENTE si puede pagar el mismo día, al llegar, o en el momento de la '
    'consulta (ANTES de tener turno reservado, o como pregunta suelta) -> responder LITERAL, '
    'SIN mencionar el alias todavia en esta respuesta:\n'
    '"Nosotros le enviamos un recordatorio de su turno dos días hábiles antes, y para confirmar '
    'su asistencia le solicitaremos abonar el valor de la consulta. Puede acercarse al '
    'consultorio a abonar en efectivo o hacer una transferencia, cómo le resulte más cómodo 😊."\n'
    'Esta respuesta reemplaza el canned generico de alias en este caso puntual — el alias/CBU '
    'se dan recien cuando el paciente ya tiene turno reservado o los pide explicitamente (ver '
    'bullet siguiente).\n\n'
)

# =============================================================================
# CAPA 2 — gate deterministico. Fuente unica: tests/test_gate_pago_tratamiento.py
# importa GATE_JS de aca y lo corre con node, no puede haber drift.
# =============================================================================
NODE_NAME = "Gate Pago Tratamiento"
UPSTREAM = "Canned Sidecar"
DOWNSTREAM = "Banlist Validator"

GATE_JS = r"""// Gate Pago Tratamiento - 2026-09-03
// Pedido explicito de la Dra. Raquel (3/9): pago de CONSULTA != pago de TRATAMIENTO.
// El de tratamiento es negociacion personalizada (monto, cuotas) -- SIEMPRE ella.
//
// Capa 2 (deterministica) del fix de Sub-Agent General: si el LLM igual responde con
// el canned generico de "pago el dia de la consulta" a una pregunta sobre pagar el
// TRATAMIENTO (caso real: exec 269717, Carla/Tadeo, 3/9), este gate lo detecta por el
// TEXTO REAL del paciente y REEMPLAZA la respuesta por escalacion -- a diferencia del
// Canned Sidecar (que solo ANEXA, nunca corrige), este gate SI reemplaza: el bug acá
// es una respuesta activamente incorrecta, no informacion faltante.

const items = $input.all();

let pacienteMsg = '';
try {
  pacienteMsg = ($('Preparar Mensaje Final').first().json.text || '').toString();
} catch (e) {
  pacienteMsg = '';
}
if (!pacienteMsg.trim()) return items;

let intent = '';
try { intent = ($('Parse Intent').first().json.intent || '').toString(); } catch (e) { intent = ''; }
if (intent === 'urgencia_dolor') return items;

const stripAccents = s => s.normalize('NFD').replace(/\p{Diacritic}/gu, '');
const norm = s => stripAccents(s).toLowerCase();

const oraciones = [];
for (const bloque of pacienteMsg.split(/\n+/)) {
  const trozos = bloque.match(/[^.!?]+[.!?]*/g) || [bloque];
  for (const t of trozos) if (t.trim()) oraciones.push(norm(t));
}

// "cuotas?" NO va en PAGO: es la palabra que los pacientes confunden con "tratamiento"
// (misma ambiguedad ya documentada en REGLA DESAMBIGUACION CUOTA del 7/8: "los
// pacientes confunden consulta, cuota y control") -- va en TEMA, junto con nombres de
// tratamiento especificos, para que "puedo pagar la cuota el lunes?" dispare igual que
// "puedo pagar el tratamiento el lunes?". Sin esto, ese fraseo se hubiera colado igual
// que el caso real (Carla dijo "tratamiento", pero cualquier paciente que diga "cuota"
// en su lugar pasaba de largo).
const PAGO = /\b(abon(ar|o|e|amos)?|pag(ar|o|u[eé]|amos)?|transfer(ir|encia|encias)?|deposit(ar|o)?|planes? de pago|se[ñn]a)\b/;
const TEMA_TRATAMIENTO = /\btratamientos?\b|\bcuotas?\b|\bbrackets?\b|\bortodoncia\b|\balineadores?\b|\binvisalign\b|\baparatos?\b|\bfrenillos?\b/;

const detectado = oraciones.some(o => TEMA_TRATAMIENTO.test(o) && PAGO.test(o));
if (!detectado) return items;

let phone = '';
try { phone = ($('Preparar Mensaje Final').first().json.phone || '').toString(); } catch (e) { phone = ''; }

const CANNED = 'El pago del tratamiento lo coordina directamente la Dra. Raquel. Le paso su consulta para que se comunique con usted.';

const resultados = [];
for (const it of items) {
  const output = (it.json.output || '').toString();
  if (!output.trim() || output.includes('[NO_REPLY]')) { resultados.push(it); continue; }
  // Dedup PRECISO: salta si el output ya CONTIENE el mismo canned que este gate
  // produciria (senal de que la Capa 1 -- el fix de prompt -- ya lo resolvio bien),
  // sin exigir coincidencia exacta -- el sub-agent suele anteponer el saludo
  // "Hola! Soy Asiri..." antes del canned (confirmado en produccion, exec 270379:
  // Capa 1 respondio perfecto con el saludo adelante, el gate lo overrideo igual por
  // exigir match EXACTO -- doble aviso al grupo + se perdio el saludo). `includes`
  // en vez de `===` cubre ese caso sin perder cobertura: el texto del canned NUNCA
  // aparece por accidente dentro de OTRA respuesta (es una frase especifica de esta
  // regla). Deliberadamente NO se intenta adivinar otras formas de "ya esta bien
  // resuelto" (p.ej. "no menciona la palabra tratamiento" -- se probo y fallaba: el
  // canned real de precio de tratamiento sustituye [tratamiento] por el nombre real,
  // ej. "brackets", nunca dice la palabra "tratamiento"). Ante la duda, el gate
  // SIEMPRE overridea: un aviso de mas al grupo es un costo menor que dejar pasar en
  // silencio un pedido real de pago de tratamiento -- que es exactamente lo que la
  // Dra. pidio evitar.
  if (output.includes(CANNED)) { resultados.push(it); continue; }

  console.log('[GATE PAGO TRATAMIENTO] override, original:', output.slice(0, 200));
  try {
    await this.helpers.httpRequest({
      method: 'POST',
      url: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo',
      qs: {
        phone: phone,
        resumen: 'Paciente pregunta si puede abonar TRATAMIENTO (no consulta). Coordinar forma de pago/cuotas con la Dra.',
      },
      json: true,
    });
  } catch (e) {
    console.log('[GATE PAGO TRATAMIENTO] escalation POST fallo:', e.message);
  }
  resultados.push({ json: { ...it.json, output: CANNED, gate_pago_tratamiento: true } });
}
return resultados;
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


def get_sm(node):
    opts = node["parameters"].get("options", {})
    return opts.get("systemMessage", node["parameters"].get("systemMessage", ""))


def set_sm(node, value):
    if "options" in node["parameters"]:
        node["parameters"]["options"]["systemMessage"] = value
    else:
        node["parameters"]["systemMessage"] = value


def build(wf):
    """Devuelve (nuevo_wf, resumen_cambios). No muta el original."""
    new = copy.deepcopy(wf)
    nodes = new["nodes"]
    names = [n["name"] for n in nodes]
    cambios = []

    # --- capa 1: prompt ---
    gnode = next((x for x in nodes if x["name"] == "Sub-Agent General"), None)
    if not gnode:
        sys.exit("ERROR: no encontre el nodo 'Sub-Agent General'")
    sm = get_sm(gnode)
    count = sm.count(GENERAL_OLD)
    if count == 0 and GENERAL_NEW in sm:
        cambios.append("Sub-Agent General: prompt ya tiene el fix (sin cambios)")
    elif count != 1:
        sys.exit(f"ERROR: el texto viejo del canned aparece {count} veces en Sub-Agent General (esperaba 1) — revisar a mano, el prompt vivo pudo haber cambiado")
    else:
        set_sm(gnode, sm.replace(GENERAL_OLD, GENERAL_NEW, 1))
        cambios.append("Sub-Agent General: agrega carve-out 'tratamiento' antes del canned de pago-dia-consulta")

    # --- capa 2: nodo + wiring ---
    if UPSTREAM not in names or DOWNSTREAM not in names:
        sys.exit(f"ERROR: falta {UPSTREAM!r} o {DOWNSTREAM!r} en el workflow")
    up = next(n for n in nodes if n["name"] == UPSTREAM)
    down = next(n for n in nodes if n["name"] == DOWNSTREAM)

    node = {
        "parameters": {"jsCode": GATE_JS},
        "id": "gate-pago-tratamiento-v1",
        "name": NODE_NAME,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [
            int((up["position"][0] + down["position"][0]) / 2),
            int(down["position"][1]) - 180,
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

    print("\n=== DIFF: Sub-Agent General (systemMessage) ===")
    old_sm = get_sm(next(x for x in wf["nodes"] if x["name"] == "Sub-Agent General"))
    new_sm = get_sm(next(x for x in new["nodes"] if x["name"] == "Sub-Agent General"))
    for line in difflib.unified_diff(old_sm.splitlines(), new_sm.splitlines(), "ANTES", "DESPUES", lineterm=""):
        print(" ", line[:250])

    print("\n=== DIFF de conexiones ===")
    a = json.dumps({k: v for k, v in wf["connections"].items() if k in (UPSTREAM, NODE_NAME)}, indent=1, ensure_ascii=False).splitlines()
    b = json.dumps({k: v for k, v in new["connections"].items() if k in (UPSTREAM, NODE_NAME)}, indent=1, ensure_ascii=False).splitlines()
    for line in difflib.unified_diff(a, b, "ANTES", "DESPUES", lineterm="", n=2):
        print(" ", line)

    hist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workflows", "history")
    os.makedirs(hist, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if not args.apply:
        print("\n[DRY-RUN] no se toco nada. Para aplicar: --apply")
        return

    pre = os.path.join(hist, f"v6_PRE_gate_pago_tratamiento_{ts}.json")
    with open(pre, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"\nbackup PRE -> {pre}")

    payload = {k: new[k] for k in PUT_KEYS if k in new}
    if "settings" in payload:
        payload["settings"] = {k: v for k, v in payload["settings"].items() if k in SETTINGS_OK}

    print("PUT ...")
    api(f"/workflows/{WF_ID}", method="PUT", payload=payload)

    after = api(f"/workflows/{WF_ID}")
    post = os.path.join(hist, f"v6_POST_gate_pago_tratamiento_{ts}.json")
    with open(post, "w", encoding="utf-8") as f:
        json.dump(after, f, ensure_ascii=False, indent=2)
    print(f"backup POST -> {post}")

    ok_prompt = GENERAL_NEW in get_sm(next(x for x in after["nodes"] if x["name"] == "Sub-Agent General"))
    ok_node = any(n["name"] == NODE_NAME for n in after["nodes"])
    ok_wire_in = after["connections"].get(UPSTREAM, {}).get("main", [[{}]])[0][0].get("node") == NODE_NAME
    ok_wire_out = after["connections"].get(NODE_NAME, {}).get("main", [[{}]])[0][0].get("node") == DOWNSTREAM
    print(f"\nverificacion: prompt={ok_prompt} nodo={ok_node} wire_in={ok_wire_in} wire_out={ok_wire_out} nodos={len(after['nodes'])}")
    if not (ok_prompt and ok_node and ok_wire_in and ok_wire_out):
        sys.exit("ERROR: la verificacion post-PUT fallo — revisar en la UI")
    print("OK.")


if __name__ == "__main__":
    main()
