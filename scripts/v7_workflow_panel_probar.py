# -*- coding: utf-8 -*-
"""v7_workflow_panel_probar.py — genera "v7 Panel - probar Información": el panel prueba cómo contesta el agente de Información con las notas que la
secretaria está escribiendo (Asiri → "Tono y estilo de las respuestas", fila `notas_para_asiri`), ANTES de guardarlas. Pedido de Lucas del 12/11 (opción A:
"que se puedan ajustar desde el panel", con un botón para probar antes de guardar).

POST /webhook/panel-probar-informacion  ·  header X-Panel-Secret (el MISMO secreto que "Panel — acciones staff"; se inyecta al desplegar, nunca está en el repo)
  body  { mensaje: texto del paciente (1–500), notas: borrador de las notas (null = las guardadas) }
  200   { ok: true, resultado: 'responde'|'deriva'|'urgencia'|'nada'|'error', texto, detalle }
  401   secreto incorrecto · 400 pedido mal armado

Qué corre: los DATOS del consultorio con la MISMA consulta y el MISMO armado que el cerebro (los trozos se copian de JS_CONTEXTO al generar: si el cerebro
cambia, esto cambia con él; si el trozo no se encuentra, el generador falla), el agente "v7 Agente Informacion" real en MODO SOMBRA (no tiene herramientas
ni memoria: no escribe nada, no avisa a nadie) y el mismo armado final que ve el paciente (OrquestadorCore.componer + mensajes fijos del panel).
Simula a alguien que escribe por primera vez y no tiene turnos (el caso más común de las preguntas de información). No pasa por el orquestador: el
pedido es el mensaje del paciente tal cual.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v7_lib import Grafo  # noqa: E402
import v7_workflow_cerebro as CER  # noqa: E402

NOMBRE = "v7 Panel - probar Información"
RUTA = "panel-probar-informacion"
SECRETO_PH = "__PANEL_SECRET__"
MENSAJE_MAX, NOTAS_MAX = 500, 4000


def _trozo(js, inicio, fin):
    """Texto de `js` desde `inicio` hasta el final de la línea donde aparece `fin` (después de `inicio`). Exactamente una vez, o falla."""
    if js.count(inicio) != 1:
        raise SystemExit(f"v7_workflow_panel_probar: no encontré (o hay más de uno) el trozo del cerebro que empieza con {inicio[:60]!r}")
    i = js.index(inicio)
    j = js.index(fin, i)
    k = js.find("\n", j)
    return js[i:(k if k >= 0 else len(js))] + "\n"


CTX = CER.JS_CONTEXTO
DIAS = _trozo(CTX, "const DIAS = [", "];")
KB = _trozo(CTX, "const kb = {}; for (const r of $('Datos del consultorio')", "kb[String(r.id)]")
AHORA = _trozo(CTX, "const j = new Date(ahoraMs - 3 * 3600 * 1000);", "ahoraMs - 3 * 3600 * 1000") + _trozo(CTX, "const ahora = DIAS[", "slice(11, 16)")
DATOS = _trozo(CTX, "const datos = [kb['20']", ".filter(Boolean).join(")
DATOS_INFO = _trozo(CTX, "const datos_info = 'DATOS DEL CONSULTORIO", "+ notas : '')")
MENSAJES = _trozo(CTX, "const mensajes = {}; for (const k of Object.keys(kb))", "mensajes[k.slice(8)] = kb[k]")

VALIDAR_JS = r"""// Valida el secreto del panel (X-Panel-Secret; n8n entrega los headers en minúsculas) y el pedido.
const SECRET = "__PANEL_SECRET__";
const j = $input.first().json || {};
const headers = j.headers || {};
const body = j.body || {};
if (!SECRET || SECRET === '__PANEL_' + 'SECRET__' || String(headers['x-panel-secret'] || '') !== SECRET) return [{ json: { ok: false, status: 401, error: 'unauthorized' } }];
const mensaje = String(body.mensaje || '').trim();
const notas = body.notas === null || body.notas === undefined ? null : String(body.notas);
if (!mensaje) return [{ json: { ok: false, status: 400, error: 'mensaje vacío' } }];
if (mensaje.length > __MENSAJE_MAX__) return [{ json: { ok: false, status: 400, error: 'mensaje demasiado largo' } }];
if (notas !== null && notas.length > __NOTAS_MAX__) return [{ json: { ok: false, status: 400, error: 'notas demasiado largas' } }];
return [{ json: { ok: true, mensaje, notas } }];
""".replace("__MENSAJE_MAX__", str(MENSAJE_MAX)).replace("__NOTAS_MAX__", str(NOTAS_MAX))

# Mismo armado que el cerebro (trozos copiados de JS_CONTEXTO) salvo las notas: las del borrador del panel, o las guardadas si vienen en null.
ARMAR_JS = ("const p = $('Validar').first().json;\nconst ahoraMs = Date.now();\n" + DIAS + KB + AHORA + DATOS
            + "const notas = p.notas === null ? (kb['dir:notas_para_asiri'] || '') : String(p.notas).trim();\n"
            + DATOS_INFO + MENSAJES
            + "// Paciente nuevo, sin ficha ni turnos, primera vez que escribe (el caso más común de las preguntas de información).\n"
            + "const contexto = HistorialCore.mensajeAgente([], p.mensaje, ahora, [], '', { motivo: 'sin_ficha' }, { conversacion_nueva: true });\n"
            + "const pedido = 'El paciente pregunta: «' + p.mensaje + '»';\n"
            + "return [{ json: { contexto, datos_info, pedido, mensaje: p.mensaje, mensajes } }];\n")

# Lo que leería el paciente: el armado final del cerebro (componer: saca preguntas, oraciones de disponibilidad, etc.) + los mensajes fijos del panel.
RESPONDER_JS = r"""const a = $('Armar').first().json;
const i = $('Información').first().json || {};
const msgs = OrquestadorCore.mensajesDe(a.mensajes || {});
const fijo = (t) => OrquestadorCore.aplicarMensajes(t, msgs);
let resultado = 'error', texto = '', detalle = null;
if (i.agente !== 'informacion' || i.error_tecnico || i.error) {
  resultado = 'error';
} else if (i.estado === 'respondido') {
  const plan = OrquestadorCore.despachar({ text: JSON.stringify({ pasos: [{ a: 'informacion', pedido: a.pedido }] }) }, {});
  const c = OrquestadorCore.componer({ execId: String($execution.id), texto_paciente: a.mensaje, libros: [], ofertas: [], vistos: [], datosPago: '', menu: OrquestadorCore.MENU,
    plan, res: { informacion: i }, reunion: {}, conversacion_nueva: false });
  texto = fijo(String((c.partes && c.partes.informacion) || '').trim());
  resultado = texto ? 'responde' : 'nada';
} else if (i.fuera_de_alcance) {
  resultado = 'deriva';
  texto = fijo(OrquestadorCore.TEXTOS.DERIVA);
  if (i.codigo === 'NO_ESTA_EN_DATOS' && i.motivo_control) detalle = 'Iba a dar un dato que no está en Conocimiento (' + String(i.motivo_control).replace(/ que no están en los DATOS/g, '') + '), así que no lo dice.';
} else if (i.urgencia) {
  resultado = 'urgencia';
} else {
  resultado = 'nada';
}
return [{ json: { ok: true, resultado, texto, detalle } }];
"""


def wf_panel_probar(secreto=SECRETO_PH):
    g = Grafo(NOMBRE)
    g._nodo("Webhook", "n8n-nodes-base.webhook", 2, {"httpMethod": "POST", "path": RUTA, "responseMode": "responseNode", "options": {}}, 0, 300, {"webhookId": RUTA})
    g.code("Validar", VALIDAR_JS.replace(SECRETO_PH, secreto), 220, 300)
    g.si("¿Autorizado?", "$json.ok === true", 440, 300)
    g._nodo("Rechazar", "n8n-nodes-base.respondToWebhook", 1.3,
            {"respondWith": "json", "responseBody": "={{ JSON.stringify({ ok: false, error: $json.error }) }}", "options": {"responseCode": "={{ $json.status }}"}}, 660, 460)
    g.postgres("Datos del consultorio", CER.SQL_DATOS, "''", 660, 220, una_vez=True)
    g.code("Armar", ARMAR_JS, 880, 220, usar=("historial_core",))
    g.subworkflow("Información", "@@ID:agente_informacion@@", {
        "tel": "'5490000000999'", "exec_id_actual": "$execution.id", "modo": "'sombra'", "texto_paciente": "$('Armar').first().json.mensaje",
        "ultimo_asiri": "''", "textos_paciente": "'[]'", "turnos_json": "'[]'", "contexto": "$('Armar').first().json.contexto", "propuesta_staff": "''",
        "datos": "$('Armar').first().json.datos_info", "pedido": "$('Armar').first().json.pedido"}, 1100, 220)
    g.code("Responder", RESPONDER_JS, 1320, 220, usar=("chequeo_salida", "orquestador_core"))
    g._nodo("Responder al panel", "n8n-nodes-base.respondToWebhook", 1.3,
            {"respondWith": "json", "responseBody": "={{ JSON.stringify($json) }}", "options": {"responseCode": 200}}, 1540, 220)
    g.conectar("Webhook", "Validar")
    g.conectar("Validar", "¿Autorizado?")
    g.conectar("¿Autorizado?", "Datos del consultorio", 0)
    g.conectar("¿Autorizado?", "Rechazar", 1)
    g.conectar("Datos del consultorio", "Armar")
    g.conectar("Armar", "Información")
    g.conectar("Información", "Responder")
    g.conectar("Responder", "Responder al panel")
    return g.json()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(wf_panel_probar(), ensure_ascii=False, indent=1)[:2000])
