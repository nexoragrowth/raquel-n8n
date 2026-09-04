# -*- coding: utf-8 -*-
"""
create_test_triaje_webhook.py — crea "Áurea — TEST Triaje (webhook aislado)".

Herramienta de prueba para Lucas/Raquel: NO es parte del v6, no lo toca, no crea
escalaciones reales ni interactúa con pacientes. Simula "qué haría el triaje" con un
mensaje de texto suelto (no una conversación real de n8n_chat_histories):

  POST /webhook/test-triaje  {"mensaje": "se me salió el alambre y me pincha", "numero": "5491161461034"}

Flujo: Gate Red Flags (triaje/gate_red_flags.js) -> si escala, responde JSON sin mandar
nada -> si no, clasifica con gpt-5-mini -> si tipo=alambre_pincha, manda la Opción 1 real
(desde el bucket de Supabase) por Evolution GO al número indicado -> si es otro tipo,
responde JSON indicando que ese video todavía no existe (solo alambre_pincha tiene los 2
videos reales al 3/9).

Uso:
    python scripts/create_test_triaje_webhook.py            # preview
    python scripts/create_test_triaje_webhook.py --apply
    python scripts/create_test_triaje_webhook.py --activate <id>
"""
import argparse, json, os, sys, urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
for p in [".env", "panel/.env.local"]:
    ep = Path(p)
    if ep.exists():
        for line in ep.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

BASE = (os.environ.get("N8N_API_BASE") or os.environ.get("N8N_BASE_URL") or "").rstrip("/")
KEY = os.environ.get("N8N_API_KEY") or ""
OPENAI_CRED = {"id": "nYujqfon7GGDnJUO", "name": "OpenAi account"}
MODELO = "gpt-5-mini"
GATE_JS = Path("triaje/gate_red_flags.js").read_text(encoding="utf-8")

SYSTEM_PROMPT = """Sos un clasificador de urgencias de ORTODONCIA para un triaje automático de una clínica (Dra. Raquel, Jujuy).
Recibís UN mensaje de un paciente (sin historial previo, es una prueba). Clasificá en UNA categoría:

- "red_flag": trauma/golpe/caída, sangrado abundante, pieza tragada, hinchazón/dificultad para respirar-tragar, fiebre, dolor intenso que no cede.
- "alambre_pincha": el alambre principal (arco) se salió del tubo/bracket o sobresale y pincha mejilla/encía.
- "bracket_suelto": un bracket se despegó del diente.
- "alambre_girado": el arco se corrió hacia un costado (sobra de un lado, corto del otro).
- "ligadura_pincha": una ligadura (alambrecito finito o gomita de un solo bracket) pincha.
- "otra_urgencia": urgencia real que no cae en los 4 tipos (contención rota, Invisalign, etc.).
- "no_urgencia": no es una urgencia clínica.

Respondé SOLO JSON: {"tipo": "...", "confianza": "alta|media|baja", "razon": "una oración"}"""

GATE_NODE_CODE = GATE_JS + """

const SYSTEM_PROMPT = """ + json.dumps(SYSTEM_PROMPT, ensure_ascii=False) + """;
const MODELO = """ + json.dumps(MODELO) + """;
const body = $input.first().json.body || {};
const mensaje = String(body.mensaje || '').trim();
const numero = String(body.numero || '5491161461034').trim();
if (!mensaje) {
  return [{ json: { error: true, respuesta: 'Falta "mensaje" en el body.' } }];
}
const gate = gateRedFlags(mensaje);
const llm_body = JSON.stringify({
  model: MODELO,
  messages: [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: 'MENSAJE DEL PACIENTE (prueba, sin historial):\\n' + mensaje },
  ],
  response_format: { type: 'json_object' },
});
return [{ json: { mensaje, numero, gate_escala: gate.escala, gate_flags: gate.flags, llm_body } }];
"""

DECIDIR_CODE = r"""const g = $('Gate Red Flags').first().json;
if (g.error) return [{ json: { respuesta: g.respuesta, accion: 'error' } }];
if (g.gate_escala) {
  return [{ json: {
    accion: 'escalaria',
    respuesta: `ESCALARÍA directo (gate de red flags, sin llamar al LLM). Flags: ${g.gate_flags.join(', ')}`,
    numero: g.numero, mensaje: g.mensaje, gate_flags: g.gate_flags,
  }}];
}
let tipo = 'error_llm', confianza = 'baja', razon = '';
try {
  const content = $input.first().json.choices[0].message.content;
  const parsed = JSON.parse(content.replace(/^```(json)?|```$/gm, '').trim());
  tipo = parsed.tipo; confianza = parsed.confianza; razon = parsed.razon;
} catch (e) {
  return [{ json: { accion: 'error', respuesta: 'Error parseando LLM: ' + String(e) } }];
}
const VIDEOS = {
  alambre_pincha: 'https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion1.mp4',
};
if (tipo === 'red_flag') {
  return [{ json: { accion: 'escalaria', respuesta: `ESCALARÍA (LLM detectó red_flag). Razón: ${razon}`, tipo, confianza, numero: g.numero, mensaje: g.mensaje } }];
}
if (VIDEOS[tipo]) {
  const caption = 'Situación en el que un alambre se salió y está pinchando.\n\nOpción 1: colocate cera de ortodoncia en la punta del alambre para aliviar la molestia hasta coordinar un control.\n\n[PRUEBA — respondé "no funcionó" para ver la Opción 2]';
  return [{ json: { accion: 'video', tipo, confianza, razon, numero: g.numero, mensaje: g.mensaje, video_url: VIDEOS[tipo], caption } }];
}
return [{ json: { accion: 'sin_video', respuesta: `Clasificó "${tipo}" (confianza ${confianza}) — todavía no hay video para ese tipo (solo alambre_pincha tiene los 2 videos reales). En vivo esto ESCALARÍA. Razón: ${razon}`, tipo, confianza } }];
"""

RESPONDER_CODE = r"""const j = $json;
return [{ json: { ok: true, ...j } }];
"""

nodes = [
    {
        "id": "webhook-test",
        "name": "Webhook Test Triaje",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [180, 300],
        "webhookId": "test-triaje",
        "parameters": {"httpMethod": "POST", "path": "test-triaje", "responseMode": "responseNode", "options": {}},
    },
    {
        "id": "gate",
        "name": "Gate Red Flags",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [420, 300],
        "parameters": {"mode": "runOnceForAllItems", "jsCode": GATE_NODE_CODE},
    },
    {
        "id": "if-escala",
        "name": "¿Escala el gate?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [660, 300],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                "conditions": [{"id": "c1", "leftValue": "={{ $json.gate_escala }}", "rightValue": True,
                                "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                "combinator": "and",
            },
            "options": {},
        },
    },
    {
        "id": "clasificar",
        "name": "Clasificar (gpt-5-mini)",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [900, 420],
        "parameters": {
            "method": "POST", "url": "https://api.openai.com/v1/chat/completions",
            "authentication": "predefinedCredentialType", "nodeCredentialType": "openAiApi",
            "sendBody": True, "specifyBody": "json", "jsonBody": "={{ $json.llm_body }}",
            "options": {"response": {"response": {"neverError": True}}, "timeout": 60000},
        },
        "credentials": {"openAiApi": OPENAI_CRED},
    },
    {
        "id": "decidir",
        "name": "Decidir",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1140, 420],
        "parameters": {"mode": "runOnceForAllItems", "jsCode": DECIDIR_CODE},
    },
    {
        "id": "decidir-escala-directo",
        "name": "Decidir (escala directo)",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [900, 180],
        "parameters": {"mode": "runOnceForAllItems", "jsCode":
            "const g = $json; return [{ json: { accion: 'escalaria', "
            "respuesta: `ESCALARÍA directo (gate de red flags, sin llamar al LLM). Flags: ${g.gate_flags.join(', ')}`, "
            "gate_flags: g.gate_flags } }];"},
    },
    {
        "id": "if-video",
        "name": "¿Hay video?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [1380, 420],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                "conditions": [{"id": "c2", "leftValue": "={{ $json.accion }}", "rightValue": "video",
                                "operator": {"type": "string", "operation": "equals"}}],
                "combinator": "and",
            },
            "options": {},
        },
    },
    {
        "id": "enviar-video",
        "name": "Enviar Video Real",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1620, 340],
        "parameters": {
            "method": "POST", "url": "https://evo.raquelrodriguez.com.ar/send/media",
            "sendHeaders": True,
            # apikey real inyectado en caliente en main() antes de crear el workflow — nunca hardcodeado acá.
            "headerParameters": {"parameters": []},
            "sendBody": True, "specifyBody": "json",
            # Mismo patron probado en produccion (Evolution API - Enviar Mensaje / reportero semanal):
            # JSON.stringify POR CAMPO dentro de un template JSON armado a mano, no un solo
            # JSON.stringify({...}) del objeto entero -- ese patron corrompia tildes (Ã³ en vez de ó).
            "jsonBody": (
                "={\n"
                '  "number": {{ JSON.stringify($json.numero) }},\n'
                '  "type": "video",\n'
                '  "url": {{ JSON.stringify($json.video_url) }},\n'
                '  "caption": {{ JSON.stringify($json.caption) }},\n'
                '  "filename": "test_triaje.mp4"\n'
                "}"
            ),
            "options": {"response": {"response": {"neverError": True}}},
        },
    },
    {
        "id": "responder",
        "name": "Responder JSON",
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.3,
        "position": [1860, 420],
        "parameters": {"respondWith": "json", "responseBody": "={{ $json }}"},
    },
]

connections = {
    "Webhook Test Triaje": {"main": [[{"node": "Gate Red Flags", "type": "main", "index": 0}]]},
    "Gate Red Flags": {"main": [[{"node": "¿Escala el gate?", "type": "main", "index": 0}]]},
    "¿Escala el gate?": {
        "main": [
            [{"node": "Decidir (escala directo)", "type": "main", "index": 0}],
            [{"node": "Clasificar (gpt-5-mini)", "type": "main", "index": 0}],
        ]
    },
    "Decidir (escala directo)": {"main": [[{"node": "Responder JSON", "type": "main", "index": 0}]]},
    "Clasificar (gpt-5-mini)": {"main": [[{"node": "Decidir", "type": "main", "index": 0}]]},
    "Decidir": {"main": [[{"node": "¿Hay video?", "type": "main", "index": 0}]]},
    "¿Hay video?": {
        "main": [
            [{"node": "Enviar Video Real", "type": "main", "index": 0}],
            [{"node": "Responder JSON", "type": "main", "index": 0}],
        ]
    },
    "Enviar Video Real": {"main": [[{"node": "Responder JSON", "type": "main", "index": 0}]]},
}

WORKFLOW = {"name": "Áurea — TEST Triaje (webhook aislado)", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}}


def api(method, path, body=None):
    if not BASE or not KEY:
        sys.exit("!! Faltan N8N_API_BASE / N8N_API_KEY.")
    req = urllib.request.Request(f"{BASE}/api/v1{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json", "accept": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def get_apikey_and_base():
    r = api("GET", "/workflows/O155MqHgOSaNZ9ye")
    node = next(n for n in r["nodes"] if n.get("name") == "Evolution API - Enviar Mensaje")
    params = node["parameters"]
    apikey = next(h["value"] for h in params["headerParameters"]["parameters"] if h["name"].lower() == "apikey")
    return apikey


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--activate", metavar="WF_ID")
    ap.add_argument("--update", metavar="WF_ID", help="PUT sobre un workflow existente (mismo id, mismo webhook path)")
    args = ap.parse_args()

    if args.activate:
        r = api("POST", f"/workflows/{args.activate}/activate")
        print(f"activado: id={r.get('id')} active={r.get('active')}")
        return

    if args.update:
        apikey = get_apikey_and_base()
        for n in nodes:
            if n["name"] == "Enviar Video Real":
                n["parameters"]["headerParameters"]["parameters"] = [
                    {"name": "apikey", "value": apikey},
                    {"name": "Content-Type", "value": "application/json"},
                ]
        body = {"name": WORKFLOW["name"], "nodes": nodes, "connections": connections, "settings": WORKFLOW["settings"]}
        r = api("PUT", f"/workflows/{args.update}", body)
        print(f"actualizado: id={r.get('id')} active={r.get('active')}")
        return

    # embebe el apikey REAL (extraído en caliente, nunca hardcodeado en este archivo fuente)
    apikey = get_apikey_and_base()
    for n in nodes:
        if n["name"] == "Enviar Video Real":
            n["parameters"]["headerParameters"]["parameters"] = [
                {"name": "apikey", "value": apikey},
                {"name": "Content-Type", "value": "application/json"},
            ]

    print(f"Workflow: '{WORKFLOW['name']}' — {len(nodes)} nodos")
    Path("workflows/history").mkdir(parents=True, exist_ok=True)
    if not args.apply:
        print("(preview — no se creó nada). Para aplicar: --apply")
        return
    creado = api("POST", "/workflows", WORKFLOW)
    wf_id = creado["id"]
    # snapshot SIN el apikey real (higiene: no dejar la clave en un JSON del repo)
    redacted = json.loads(json.dumps(creado))
    for n in redacted.get("nodes", []):
        if n.get("name") == "Enviar Video Real":
            for h in n.get("parameters", {}).get("headerParameters", {}).get("parameters", []):
                if h.get("name", "").lower() == "apikey":
                    h["value"] = "***REDACTED***"
    json.dump(redacted, open(f"workflows/history/test_triaje_CREADO_{wf_id}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nCreado OK -> id={wf_id} (activo={creado.get('active')})")
    print(f"Siguiente: python scripts/create_test_triaje_webhook.py --activate {wf_id}")
    print(f"Probar: curl -X POST https://n8n.raquelrodriguez.com.ar/webhook/test-triaje -H 'Content-Type: application/json' -d '{{\"mensaje\": \"se me salio el alambre y me pincha\", \"numero\": \"5491161461034\"}}'")


if __name__ == "__main__":
    main()
