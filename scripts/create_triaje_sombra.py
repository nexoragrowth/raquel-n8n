# -*- coding: utf-8 -*-
"""
create_triaje_sombra.py — crea el workflow "Áurea — Triaje Urgencias (sombra)".

FASE 1 del triaje de urgencias con video (diseño y decisiones: memory/decisions.md 2/9).
Es un SATÉLITE: NO toca el v6. Cada 15 min (o vía webhook manual) lee de `escalaciones_log`
las urgencias reales que el bot ya escaló (mismo pre-filtro por tema que el panel y la
sombra retrospectiva), junta los mensajes crudos del paciente desde `conversaciones`,
corre el gate determinístico de red flags (triaje/gate_red_flags.js, embebido tal cual),
clasifica con gpt-5-mini en los tipos del triaje y guarda TODO en `triaje_urgencias_log`
con modo='sombra', accion='escalado'. No manda nada a nadie: el paciente sigue recibiendo
exactamente la escalación de siempre.

Para qué sirve: medir en vivo (a) cuántas urgencias caen en cada tipo, (b) cuántas veces
dispara el gate y por qué flag, (c) qué confianza tiene el clasificador con SOLO el primer
mensaje (sin preguntas guiadas). Con eso se decide el piloto (Fase 2).

Nace INACTIVO. Activar con --activate <id> después de revisar (el webhook manual necesita
el workflow activo para responder).

USO:
    python scripts/create_triaje_sombra.py              # preview
    python scripts/create_triaje_sombra.py --apply      # crea (POST)
    python scripts/create_triaje_sombra.py --activate <id>
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

POSTGRES_CRED = {"id": "TpYhZX4UT61xAKSV", "name": "Postgres Supabase Nexora v3"}
OPENAI_CRED = {"id": "nYujqfon7GGDnJUO", "name": "OpenAi account"}
MODELO = "gpt-5-mini"

GATE_JS = Path("triaje/gate_red_flags.js").read_text(encoding="utf-8")

# Pre-filtro: mismas regex que lib/escalaciones.ts (panel) y analisis_retrospectivo_urgencias.py.
# Postgres ARE: \m = inicio de palabra, \y = límite de palabra. ~* = case-insensitive.
QUERY_NUEVAS = r"""
SELECT
  e.id          AS escalacion_id,
  e.telefono,
  e.motivo      AS motivo_bot,
  e.exec_id,
  e.created_at  AS escalacion_created_at,
  COALESCE((
    SELECT string_agg(c.mensaje, E'\n' ORDER BY c.ts)
    FROM (
      SELECT c2.mensaje, c2."timestamp" AS ts
      FROM conversaciones c2
      WHERE c2.telefono = e.telefono
        AND lower(c2.rol) IN ('user','human','paciente','usuario')
        AND c2."timestamp" BETWEEN e.created_at - INTERVAL '20 minutes' AND e.created_at + INTERVAL '1 minute'
      ORDER BY c2."timestamp" DESC
      LIMIT 4
    ) c
  ), '') AS mensaje_paciente
FROM escalaciones_log e
WHERE e.created_at BETWEEN NOW() - INTERVAL '{{ $json.horas }} hours' AND NOW() - INTERVAL '{{ $json.min_edad }} minutes'
  AND e.motivo !~* 'el bot detect[oó] que ya est[aá]s atendiendo'
  AND e.motivo NOT LIKE '[TRIAJE%'
  AND e.motivo !~* 'comprobante\s+(de\s+pago|por|de\s+\$)|envi[oó]\s+comprobante|verificar que el pago'
  AND (e.motivo ~* '\mdolor|molesti|urgen|sangr|hinch|fiebre|inflam'
       OR e.motivo ~* 'bracket|topecito|alambre|\mtubo\y|aparatolog|se le sali')
  AND NOT EXISTS (SELECT 1 FROM triaje_urgencias_log t WHERE t.escalacion_id = e.id)
ORDER BY e.created_at
"""

SYSTEM_PROMPT = """Sos un clasificador de urgencias de ORTODONCIA para un triaje automático de una clínica (Dra. Raquel, Jujuy).
Recibís el resumen que hizo el bot al escalar + los últimos mensajes crudos del paciente. Clasificá en UNA categoría:

- "red_flag": hay señal que SIEMPRE debe ir a la doctora: golpe/caída/accidente/trauma, sangrado abundante o que no para, pieza o parte del aparato tragada, hinchazón de cara/cuello, dificultad para respirar o tragar, fiebre, dolor intenso que no cede. Si hay red flag, gana sobre cualquier otra categoría.
- "alambre_pincha": el alambre principal (arco) se salió del tubo/bracket o sobresale y pincha mejilla/encía, sin red flags.
- "bracket_suelto": un bracket se despegó del diente (se mueve, "se salió el cuadradito/topecito", "se me soltó un bracket"), sin red flags. NO incluye attachments de Invisalign.
- "alambre_girado": el arco se corrió hacia un costado (sobra de un lado, quedó corto del otro), sin red flags.
- "ligadura_pincha": una ligadura (alambrecito finito o gomita de un solo bracket) pincha, sin red flags.
- "otra_urgencia": urgencia/molestia real de ortodoncia que NO cae en los 4 tipos anteriores (contención rota, alineadores/attachments de Invisalign, microimplantes, dolor por ajuste, bracket que irrita sin estar suelto, "me duele" sin más detalle).
- "no_urgencia": la escalación no era una urgencia clínica (turnos, pagos, dudas generales, cancelación por enfermedad, etc.).

Sé conservador: si la información no alcanza para elegir uno de los 4 tipos con confianza, usá "otra_urgencia".
Respondé SOLO JSON: {"tipo": "...", "red_flags": ["..."], "confianza": "alta|media|baja", "razon": "una oración"}"""

GATE_NODE_CODE = GATE_JS + """

// ---- n8n: aplicar el gate a cada urgencia y armar el body del clasificador ----
const SYSTEM_PROMPT = """ + json.dumps(SYSTEM_PROMPT, ensure_ascii=False) + """;
const MODELO = """ + json.dumps(MODELO) + """;
return $input.all().map(item => {
  const j = item.json;
  const textoPaciente = (j.mensaje_paciente || '').trim();
  const textoGate = textoPaciente + '\\n' + (j.motivo_bot || '');
  const gate = gateRedFlags(textoGate);
  const user = 'RESUMEN DEL BOT AL ESCALAR:\\n' + (j.motivo_bot || '') +
    '\\n\\nMENSAJES CRUDOS DEL PACIENTE (previos, más viejo primero):\\n' +
    (textoPaciente ? textoPaciente.split('\\n').map(m => '- ' + m).join('\\n') : '(no se encontraron mensajes crudos en la ventana)');
  const llm_body = JSON.stringify({
    model: MODELO,
    messages: [{ role: 'system', content: SYSTEM_PROMPT }, { role: 'user', content: user }],
    response_format: { type: 'json_object' },
  });
  return { json: { ...j, gate_escala: gate.escala, gate_red_flags: gate.flags, llm_body } };
});
"""

PARAMS_CODE = r"""// Ventana de búsqueda. Cron: defaults (últimas 3h, escalaciones de >10 min para que el
// Logger ya haya sincronizado los mensajes crudos a `conversaciones`).
// Webhook manual: POST {"horas": 72, "min_edad": 10} para reprocesar una ventana mayor
// (la tabla dedupe por escalacion_id, así que reprocesar nunca duplica).
const b = ($input.first().json.body) || {};
const horas = Number(b.horas) > 0 ? Number(b.horas) : 3;
const min_edad = Number.isFinite(Number(b.min_edad)) ? Number(b.min_edad) : 10;
return [{ json: { horas, min_edad } }];
"""

INSERT_CODE = r"""// Une la respuesta del LLM (item i) con la fila del gate (item i, cadena lineal) y arma el INSERT.
const gates = $('Gate Red Flags').all();
const esc = (v) => v === null || v === undefined ? 'NULL' : "'" + String(v).replace(/'/g, "''") + "'";
const out = [];
$input.all().forEach((item, i) => {
  const g = gates[i].json;
  let tipo = 'error_llm', confianza = 'baja', razon = '', flagsLLM = [];
  try {
    const content = item.json.choices[0].message.content;
    const parsed = JSON.parse(content.replace(/^```(json)?|```$/gm, '').trim());
    tipo = parsed.tipo || 'error_llm';
    confianza = parsed.confianza || 'baja';
    razon = parsed.razon || '';
    flagsLLM = Array.isArray(parsed.red_flags) ? parsed.red_flags : [];
  } catch (e) {
    razon = 'error parseando LLM: ' + String(e).slice(0, 200) + ' | ' + JSON.stringify(item.json).slice(0, 300);
  }
  // red flags: unión de las del gate (determinístico) y las que vio el LLM, marcadas por origen
  const flags = [...g.gate_red_flags.map(f => 'gate:' + f), ...flagsLLM.map(f => 'llm:' + f)];
  const sql = `INSERT INTO triaje_urgencias_log
    (escalacion_id, telefono, exec_id, escalacion_created_at, motivo_bot, mensaje_paciente,
     gate_red_flags, gate_escala, tipo, confianza, razon, modelo, modo, accion)
    VALUES (${esc(g.escalacion_id)}, ${esc(g.telefono)}, ${esc(g.exec_id)}, ${esc(g.escalacion_created_at)},
     ${esc(g.motivo_bot)}, ${esc(g.mensaje_paciente)}, ${esc(JSON.stringify(flags))}::jsonb, ${g.gate_escala ? 'TRUE' : 'FALSE'},
     ${esc(tipo)}, ${esc(confianza)}, ${esc(razon)}, ${esc('""" + MODELO + r"""')}, 'sombra', 'escalado')
    ON CONFLICT (escalacion_id) DO NOTHING`;
  out.push({ json: { sql, escalacion_id: g.escalacion_id, tipo, confianza, gate_escala: g.gate_escala, flags } });
});
return out;
"""

nodes = [
    {
        "id": "cron-15min",
        "name": "Cada 15 min",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [180, 260],
        "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "*/15 * * * *"}]}},
    },
    {
        "id": "webhook-manual",
        "name": "Webhook Manual Sombra",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [180, 420],
        "webhookId": "trigger-triaje-sombra-manual",
        "parameters": {"httpMethod": "POST", "path": "trigger-triaje-sombra-manual", "responseMode": "onReceived", "options": {}},
    },
    {
        "id": "params",
        "name": "Params (ventana)",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [400, 340],
        "parameters": {"mode": "runOnceForAllItems", "jsCode": PARAMS_CODE},
    },
    {
        "id": "query-nuevas",
        "name": "Query Urgencias Nuevas",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [620, 340],
        # Expresión: solo {{ $json.horas }} / {{ $json.min_edad }} se evalúan; el resto (incl. los
        # "$" de las regex) es texto literal.
        "parameters": {"operation": "executeQuery", "query": "=" + QUERY_NUEVAS.strip(), "options": {}},
        "credentials": {"postgres": POSTGRES_CRED},
    },
    {
        "id": "gate",
        "name": "Gate Red Flags",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [700, 340],
        "parameters": {"mode": "runOnceForAllItems", "jsCode": GATE_NODE_CODE},
    },
    {
        "id": "clasificar",
        "name": "Clasificar (gpt-5-mini)",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [960, 340],
        "parameters": {
            "method": "POST",
            "url": "https://api.openai.com/v1/chat/completions",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "openAiApi",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.llm_body }}",
            "options": {"response": {"response": {"neverError": True}}, "timeout": 60000},
        },
        "credentials": {"openAiApi": OPENAI_CRED},
    },
    {
        "id": "armar-insert",
        "name": "Armar INSERT",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1220, 340],
        "parameters": {"mode": "runOnceForAllItems", "jsCode": INSERT_CODE},
    },
    {
        "id": "insert-log",
        "name": "Insert triaje_urgencias_log",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [1480, 340],
        "parameters": {"operation": "executeQuery", "query": "={{ $json.sql }}", "options": {}},
        "credentials": {"postgres": POSTGRES_CRED},
    },
]

connections = {
    "Cada 15 min": {"main": [[{"node": "Params (ventana)", "type": "main", "index": 0}]]},
    "Webhook Manual Sombra": {"main": [[{"node": "Params (ventana)", "type": "main", "index": 0}]]},
    "Params (ventana)": {"main": [[{"node": "Query Urgencias Nuevas", "type": "main", "index": 0}]]},
    "Query Urgencias Nuevas": {"main": [[{"node": "Gate Red Flags", "type": "main", "index": 0}]]},
    "Gate Red Flags": {"main": [[{"node": "Clasificar (gpt-5-mini)", "type": "main", "index": 0}]]},
    "Clasificar (gpt-5-mini)": {"main": [[{"node": "Armar INSERT", "type": "main", "index": 0}]]},
    "Armar INSERT": {"main": [[{"node": "Insert triaje_urgencias_log", "type": "main", "index": 0}]]},
}

WORKFLOW = {
    "name": "Áurea — Triaje Urgencias (sombra)",
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1"},
}


def api(method, path, body=None):
    if not BASE or not KEY:
        sys.exit("!! Faltan N8N_API_BASE / N8N_API_KEY (.env).")
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
    ap.add_argument("--activate", metavar="WF_ID")
    ap.add_argument("--update", metavar="WF_ID", help="PUT sobre el workflow existente (mismo id/webhook)")
    args = ap.parse_args()

    if args.activate:
        r = api("POST", f"/workflows/{args.activate}/activate")
        print(f"activado: id={r.get('id')} active={r.get('active')}")
        return

    if args.update:
        r = api("PUT", f"/workflows/{args.update}", {"name": WORKFLOW["name"], "nodes": nodes, "connections": connections, "settings": WORKFLOW["settings"]})
        print(f"actualizado: id={r.get('id')} active={r.get('active')} nodos={len(r.get('nodes', []))}")
        return

    print(f"Workflow: '{WORKFLOW['name']}' — {len(nodes)} nodos")
    for n in nodes:
        print("  -", n["name"], "|", n["type"])
    Path("workflows/history").mkdir(parents=True, exist_ok=True)
    preview = "workflows/history/triaje_sombra_PREVIEW.json"
    json.dump(WORKFLOW, open(preview, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"preview JSON -> {preview}")

    if not args.apply:
        print("\n(preview — no se creó nada). Para aplicar: --apply")
        return

    creado = api("POST", "/workflows", WORKFLOW)
    wf_id = creado["id"]
    out = f"workflows/history/triaje_sombra_CREADO_{wf_id}.json"
    json.dump(creado, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nCreado OK -> id={wf_id} (activo={creado.get('active')}) | snapshot -> {out}")
    print(f"Siguiente: python scripts/create_triaje_sombra.py --activate {wf_id}")


if __name__ == "__main__":
    main()
