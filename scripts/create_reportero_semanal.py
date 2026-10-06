# -*- coding: utf-8 -*-
"""
create_reportero_semanal.py — crea el workflow "Áurea — Reportero Semanal" (P1 del
backlog desde el 18/7, diseño pactado con Lucas, nunca construido).

QUÉ HACE: cada lunes (o vía webhook manual para probar) lee `escalaciones_log` de los
últimos 7 días, la clasifica con EL MISMO criterio que ya usa el panel en
`/aprendizaje` (lib/escalaciones.ts: señal/ruido/operativo + temas — las regex están
copiadas 1:1 acá, mantener sincronizadas si se edita un lado), le pide a un LLM chico
(gpt-5-nano, mismo modelo que "Banlist Shadow", misma credencial OpenAI ya existente)
una sugerencia concreta por tema de qué cargar en Conocimiento, arma el mensaje y lo
manda por WhatsApp.

SEGURIDAD: nace con TEST_MODE=true en el nodo "Prep Envio" -- el primer reporte real
llega a Lucas, NO al grupo, hasta que él lo revise y confirme (tal como decía el diseño
original: "mostrar el primer reporte a Lucas antes"). Pasar TEST_MODE a false recién
después de esa validación.

Nace INACTIVA. Se activa en un segundo paso explícito después de armar el grafo, para
poder probar el trigger manual antes de confiar en el cron.

USO:
    python scripts/create_reportero_semanal.py            # preview (arma el JSON, no lo manda)
    python scripts/create_reportero_semanal.py --apply     # crea el workflow (POST)

Regla del proyecto: NUNCA --apply sin OK explicito de Lucas (ya lo dio: "dale el
reportero semanal").
"""
import argparse
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = (os.environ.get("N8N_API_BASE") or "").rstrip("/")
KEY = os.environ.get("N8N_API_KEY") or ""

POSTGRES_CRED = {"id": "TpYhZX4UT61xAKSV", "name": "Postgres Supabase Nexora v3"}
OPENAI_CRED = {"id": "nYujqfon7GGDnJUO", "name": "OpenAi account"}
EVO_TOKEN = "fe27778f-6608-4a71-9385-e5c5c1eebf14"

CLASIFICAR_CODE = """// Mismo criterio que lib/escalaciones.ts del panel (senal/ruido/operativo + temas).
// Si se edita un lado, editar el otro tambien -- son la misma logica en 2 lenguajes.
const RE_RUIDO = /el bot detect[o\\u00f3] que ya est[a\\u00e1]s atendiendo/i;
const RE_OPERATIVO = /comprobante\\s+(de\\s+pago|por|de\\s+\\$)|envi[o\\u00f3]\\s+comprobante|verificar que el pago/i;
const TEMAS = [
  { tema: "Urgencias y dolor", re: /\\bdolor|molesti|urgen|sangr|hinch|fiebre|inflam/i },
  { tema: "Aparatolog\\u00eda", re: /bracket|topecito|alambre|\\btubo\\b|aparatolog|se le sali/i },
  { tema: "\\u00d3rdenes y estudios", re: /\\borden(es)?\\b|estudio|informe|radiograf|\\brx\\b|extracci/i },
  { tema: "Turnos y agenda", re: /turno|reprogram|cancel|lista de espera|agenda|horario|viaj/i },
  { tema: "Pagos", re: /comprobante|\\bpago\\b|transferenc|abon/i },
  { tema: "Datos que faltan", re: /no hay historial|sin historial|no encuentro|no figura/i },
];

function tipoEscalacion(motivo) {
  const t = motivo || '';
  if (RE_RUIDO.test(t)) return 'ruido';
  if (RE_OPERATIVO.test(t)) return 'operativo';
  return 'senal';
}
function temaEscalacion(motivo) {
  const t = motivo || '';
  for (const { tema, re } of TEMAS) if (re.test(t)) return tema;
  return 'Otros';
}
function limpiarMotivo(motivo) {
  let t = (motivo || '').trim();
  if (!t) return 'Sin motivo registrado';
  t = t.replace(/^\\[[^\\]]{0,40}\\]\\s*:?\\s*/, '');
  t = t.replace(/\\b(phone|tel\\.?|tel[e\\u00e9]fono)\\s*:?\\s*\\+?\\d[\\d\\s-]{5,}/gi, ' ');
  t = t.replace(/\\(\\s*(phone|tel\\.?|tel[e\\u00e9]fono)[^)]*\\)/gi, ' ');
  t = t.replace(/\\s{2,}/g, ' ').replace(/^[\\s,;:.\\u2013\\u2014-]+/, '').trim();
  if (!t) return 'Sin motivo registrado';
  return t.charAt(0).toUpperCase() + t.slice(1);
}

const rows = $input.all().map(i => i.json);
let senal = 0, ruido = 0, operativo = 0;
const porTema = new Map();
for (const r of rows) {
  const tipo = tipoEscalacion(r.motivo);
  if (tipo === 'ruido') { ruido++; continue; }
  if (tipo === 'operativo') { operativo++; continue; }
  senal++;
  const tema = temaEscalacion(r.motivo);
  const lista = porTema.get(tema) || [];
  lista.push(limpiarMotivo(r.motivo));
  porTema.set(tema, lista);
}
const temas = [...porTema.entries()].sort((a, b) => b[1].length - a[1].length);

const temasTextoLLM = temas.map(([tema, casos]) =>
  `Tema: ${tema} (${casos.length} casos)\\n` + casos.slice(0, 8).map(c => '- ' + c).join('\\n')
).join('\\n\\n');

return [{ json: {
  total: rows.length,
  senal, ruido, operativo,
  hay_senal: senal > 0,
  temas: temas.map(([tema, casos]) => ({ tema, count: casos.length })),
  temas_texto_llm: temasTextoLLM,
}}];
"""

PREP_LLM_CODE = """const j = $json;
const systemPrompt = `Sos un asistente que ayuda a una clinica de ortodoncia a mejorar su bot de WhatsApp (Asiri).
Te paso los casos de esta semana que el bot escalo a un humano porque no supo resolverlos, agrupados por tema.
Para CADA tema, en UNA sola linea, sugeri de forma concreta y breve que cargar en la Base de Conocimiento
del bot o que ajustar en su comportamiento para que la proxima vez lo resuelva solo.
No repitas el tema literal como titulo del caso, anda directo a la sugerencia.
Formato de salida EXACTO, una linea por tema, nada mas (sin intro, sin cierre, sin numerarlas):
<Tema>: <sugerencia concreta y accionable>`;

const body = {
  model: "gpt-5-nano",
  messages: [
    { role: "system", content: systemPrompt },
    { role: "user", content: j.temas_texto_llm }
  ],
  temperature: 0.3,
};
return [{ json: { ...j, llm_body: JSON.stringify(body) } }];
"""

BUILD_CON_SENAL_CODE = """const stats = $('Clasificar y Agrupar').first().json;
const llmResp = $json;
let sugerencias = '';
try {
  sugerencias = (llmResp.choices && llmResp.choices[0] && llmResp.choices[0].message && llmResp.choices[0].message.content || '').trim();
} catch (e) {}
if (!sugerencias) sugerencias = '(no se pudo generar sugerencias automaticas esta semana -- revisar los temas manualmente en /aprendizaje)';

const ruidoTotal = stats.ruido + stats.operativo;
const lines = [
  '\\ud83d\\udcda *\\u00c1urea \\u2014 Reportero semanal*',
  '',
  `Esta semana: ${stats.senal} caso(s) que Asiri no supo resolver sola` +
    (ruidoTotal > 0 ? ` (+ ${ruidoTotal} avisos automaticos de rutina, no listados).` : '.'),
  '',
  '*Temas y que cargar:*',
  sugerencias,
  '',
  'Detalle completo en /aprendizaje del panel.'
];
return [{ json: { mensaje_final: lines.join('\\n') } }];
"""

BUILD_SIN_SENAL_CODE = """const stats = $json;
const ruidoTotal = stats.ruido + stats.operativo;
const lines = [
  '\\ud83d\\udcda *\\u00c1urea \\u2014 Reportero semanal*',
  '',
  'Sin casos para revisar esta semana -- Asiri resolvio todo sola \\ud83c\\udf89',
  ruidoTotal > 0 ? `(${ruidoTotal} avisos automaticos de rutina, nada que aprender ahi).` : '',
].filter(l => l !== '');
return [{ json: { mensaje_final: lines.join('\\n') } }];
"""

PREP_ENVIO_CODE = """// TEST_MODE=true: el reporte llega a Lucas, NO al grupo, hasta validar el primer real.
// Pasar a false recien despues de que Lucas confirme el contenido de un reporte real.
const TEST_MODE = true;
const TEST_PHONE = "5491161461034";
const GRUPO_JID = "120363407321448469@g.us";
return [{ json: {
  mensaje_final: $json.mensaje_final,
  numero_destino: TEST_MODE ? TEST_PHONE : GRUPO_JID,
}}];
"""

nodes = [
    {
        "id": "cron-semanal",
        "name": "Lunes 10AM Arg (cron hora Berlin)",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [180, 260],
        "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 15 * * 1"}]}},
    },
    {
        "id": "webhook-manual",
        "name": "Webhook Manual Reportero",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [180, 420],
        "webhookId": "trigger-reportero-manual",
        "parameters": {
            "httpMethod": "POST",
            "path": "trigger-reportero-manual",
            "responseMode": "onReceived",
            "options": {},
        },
    },
    {
        "id": "query-escalaciones",
        "name": "Query Escalaciones Semana",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [440, 340],
        "parameters": {
            "operation": "executeQuery",
            "query": "SELECT motivo, created_at FROM escalaciones_log WHERE created_at >= NOW() - INTERVAL '7 days' ORDER BY created_at DESC",
            "options": {},
        },
        "credentials": {"postgres": POSTGRES_CRED},
    },
    {
        "id": "clasificar",
        "name": "Clasificar y Agrupar",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [700, 340],
        "parameters": {"mode": "runOnceForAllItems", "jsCode": CLASIFICAR_CODE},
    },
    {
        "id": "hay-senal",
        "name": "¿Hay señal?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [960, 340],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                "conditions": [
                    {
                        "id": "cond-hay-senal",
                        "leftValue": "={{ $json.hay_senal }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
    },
    {
        "id": "prep-llm",
        "name": "Prep LLM Body",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1220, 220],
        "parameters": {"mode": "runOnceForAllItems", "jsCode": PREP_LLM_CODE},
    },
    {
        "id": "llm-sintesis",
        "name": "LLM Síntesis",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1460, 220],
        "parameters": {
            "method": "POST",
            "url": "https://api.openai.com/v1/chat/completions",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "openAiApi",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.llm_body }}",
            "options": {"response": {"response": {"neverError": True}}},
        },
        "credentials": {"openAiApi": OPENAI_CRED},
    },
    {
        "id": "build-con-senal",
        "name": "Build Mensaje Con Señal",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1700, 220],
        "parameters": {"mode": "runOnceForAllItems", "jsCode": BUILD_CON_SENAL_CODE},
    },
    {
        "id": "build-sin-senal",
        "name": "Build Mensaje Sin Señal",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1220, 460],
        "parameters": {"mode": "runOnceForAllItems", "jsCode": BUILD_SIN_SENAL_CODE},
    },
    {
        "id": "prep-envio",
        "name": "Prep Envío (test mode)",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1940, 340],
        "parameters": {"mode": "runOnceForAllItems", "jsCode": PREP_ENVIO_CODE},
    },
    {
        "id": "enviar-wa",
        "name": "Enviar WA",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2180, 340],
        "parameters": {
            "method": "POST",
            "url": "https://evo.raquelrodriguez.com.ar/send/text",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "apikey", "value": EVO_TOKEN},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": (
                '={\n'
                '  "number": {{ JSON.stringify($json.numero_destino) }},\n'
                '  "text": {{ JSON.stringify($json.mensaje_final) }}\n'
                '}'
            ),
        },
    },
]

connections = {
    "Lunes 10AM Arg (cron hora Berlin)": {"main": [[{"node": "Query Escalaciones Semana", "type": "main", "index": 0}]]},
    "Webhook Manual Reportero": {"main": [[{"node": "Query Escalaciones Semana", "type": "main", "index": 0}]]},
    "Query Escalaciones Semana": {"main": [[{"node": "Clasificar y Agrupar", "type": "main", "index": 0}]]},
    "Clasificar y Agrupar": {"main": [[{"node": "¿Hay señal?", "type": "main", "index": 0}]]},
    "¿Hay señal?": {
        "main": [
            [{"node": "Prep LLM Body", "type": "main", "index": 0}],
            [{"node": "Build Mensaje Sin Señal", "type": "main", "index": 0}],
        ]
    },
    "Prep LLM Body": {"main": [[{"node": "LLM Síntesis", "type": "main", "index": 0}]]},
    "LLM Síntesis": {"main": [[{"node": "Build Mensaje Con Señal", "type": "main", "index": 0}]]},
    "Build Mensaje Con Señal": {"main": [[{"node": "Prep Envío (test mode)", "type": "main", "index": 0}]]},
    "Build Mensaje Sin Señal": {"main": [[{"node": "Prep Envío (test mode)", "type": "main", "index": 0}]]},
    "Prep Envío (test mode)": {"main": [[{"node": "Enviar WA", "type": "main", "index": 0}]]},
}

WORKFLOW = {
    "name": "Áurea — Reportero Semanal",
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1"},
}


def api(method, path, body=None):
    if not BASE or not KEY:
        sys.exit("!! Faltan N8N_API_BASE / N8N_API_KEY en el entorno.")
    req = urllib.request.Request(
        f"{BASE}/api/v1{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json", "accept": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    print(f"Workflow a crear: '{WORKFLOW['name']}' — {len(nodes)} nodos")
    for n in nodes:
        print("  -", n["name"], "|", n["type"])

    if not args.apply:
        print("\n(preview — no se creó nada). Para aplicar: --apply")
        return

    creado = api("POST", "/workflows", WORKFLOW)
    wf_id = creado["id"]
    print(f"\nCreado OK -> id={wf_id}")

    os.makedirs("workflows/history", exist_ok=True)
    out = f"workflows/history/reportero_semanal_CREADO_{wf_id}.json"
    json.dump(creado, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"snapshot -> {out}")
    print(f"\nID del workflow: {wf_id}  (activo={creado.get('active')})")
    print("Siguiente paso: activar con --activate (script aparte) antes de poder probar el webhook.")


if __name__ == "__main__":
    main()
