# -*- coding: utf-8 -*-
"""
apply_politica_modo_humano.py — "el bot cede cuando una persona actua, no cuando el bot duda" (2026-10-05).

PROBLEMA (caso real de la paciente que queria cambiar un turno, exec 294752 + analisis de las escalaciones): la herramienta
`escalar_a_secretaria` le dice al modelo que "el bot se silencia y deja de responder hasta que un humano atienda" y lo manda a usarla en
siete situaciones (pagos, ambiguedad, "no pudiste resolver"...). Cada escalacion pasaba por `Helper - Notify Grupo`, que 20 s despues ponia
al paciente en MODO HUMANO 24 h. Resultado: el bot se cortaba justo cuando el paciente queria cerrar la accion.

POLITICA NUEVA
  Se silencia al bot SOLO cuando: (1) una persona escribe de verdad (celular o panel: ya funciona asi, no se toca), (2) el paciente pide hablar con
  una persona, (3) hay una urgencia (triaje: lo fuerza el codigo con tomar=true), (4) queja/reclamo o baja de datos.
  En cualquier otro caso escalar es solo un AVISO al grupo con el resumen y el bot sigue ayudando. Cuando una persona escribe, el bot se hace a un lado solo.

CAMBIOS
  Helper - Notify Grupo (S5U6tSipzlgFHCkf)
    + nodo nuevo `Decidir Takeover` (Code) entre `Esperar respuesta del bot (20s)` y `Activar Takeover Paciente`: deja pasar solo si viene
      `tomar=true` o el resumen indica pedido de persona / queja / reclamo / baja de datos / urgencia / dolor / sangrado. Si no, corta (no silencia).
  v6 (O155MqHgOSaNZ9ye)
    ~ `Triaje: Escalar (notify-grupo)`: manda `tomar: "true"` (las urgencias SIEMPRE silencian, ya no depende del texto).
    ~ `escalar_a_secretaria`: nueva descripcion (ya no dice que silencia ni habla de Chatwoot; explica cuando usarla y la frase del resumen para
      pedido de persona / queja / urgencia).
    ~ `Parse Intent`: "¿Quiere que le busque las fechas mas proximas?" tambien es una pregunta pendiente (caso real: el "Si" caia al Router).
    ~ `Sub-Agent Agendar` (prompt): no promete reemplazar/cancelar turnos (no tiene la herramienta) y toma nota de "anotenme por si se libera uno antes"
      como aviso (escalar_a_secretaria, que ya no silencia).

NO toca: credenciales, el resto de nodos, ni datos. Reversible con scripts/restaurar_workflow.py (un PUT por workflow, con backup PRE de cada uno).

USO:
    python scripts/apply_politica_modo_humano.py            # simulacion (solo GET): muestra el diff
    python scripts/apply_politica_modo_humano.py --apply    # backups PRE + PUT (Helper primero, v6 despues) + verificacion + backups POST

Regla del proyecto: NUNCA --apply sin OK de Lucas. Despues: prueba real (ver tests/test_politica_modo_humano.py) y limpiar el numero de prueba.
"""
import argparse, copy, difflib, json, re, sys, time, urllib.request, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
V6 = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
HELPER = "S5U6tSipzlgFHCkf"
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}

# ------------------------------------------------------------------ Helper: decidir si se toma el chat
DECIDIR_TAKEOVER_JS = r"""// Politica (2026-10-05): escalar = AVISAR al grupo. El bot solo se silencia si lo pide el codigo (tomar=true: urgencias del triaje)
// o si el resumen indica que el paciente pidio una persona, una queja/reclamo, una baja de datos o una urgencia/dolor/sangrado.
// En cualquier otro caso corta aca: el bot sigue atendiendo hasta que una persona escriba (ahi el modo humano se activa solo).
const wh = $('Webhook').first().json || {};
const q = wh.query || {};
const b = wh.body || {};
const tomarExplicito = String(q.tomar ?? b.tomar ?? '').toLowerCase() === 'true';
const resumen = String(q.resumen ?? b.resumen ?? '').toLowerCase();
const motivo = /pidi[oó]\s+hablar|quiere\s+hablar|solicit[oó]\s+hablar|hablar\s+con\s+(una\s+|un\s+)?(persona|alguien|humano|secretaria|doctora|dra\b)|\bqueja\b|reclamo|baja\s+de\s+datos|urgenc|dolor|sangr/.test(resumen);
if (tomarExplicito || motivo) return $input.all();
return [];
"""

# ------------------------------------------------------------------ v6
TRIAJE_VIEJO = "qs: { phone: p.phone, resumen: p.resumen },"
TRIAJE_NUEVO = 'qs: { phone: p.phone, resumen: p.resumen, tomar: "true" },'

TOOL_DESC_PREFIJO = "Escala el caso a la secretaria humana"
TOOL_DESC_NUEVA = (
    "Avisa a la secretaria por el grupo de WhatsApp del consultorio. NO silencia al bot: la conversacion sigue y vos seguis ayudando con lo "
    "que si podes (turnos, datos, confirmaciones). Cuando una persona escribe, el bot se hace a un lado solo.\n\n"
    "USAR cuando: (a) consulta clinica o foto/estudio que tiene que ver la Dra., (b) comprobante de pago o duda de pago (acusa recibo y avisa), "
    "(c) algo que no pudiste resolver con tus herramientas, (d) pedido fuera de alcance, (e) el paciente pide que lo anoten por si se libera un turno antes.\n\n"
    "Si el paciente PIDE hablar con una persona, hace una QUEJA o reclamo, o hay una URGENCIA, usala igual y escribi en el resumen exactamente "
    "\"pidio hablar con una persona\", \"queja\" o \"urgencia\": en esos casos el bot se silencia solo.\n"
    "NO la uses por dudas generales ni para dejar de atender: si podes avanzar, avanza.\n\n"
    "ARG REQUERIDO:\n"
    "- resumen: 1-2 oraciones del caso para que la secretaria entienda sin abrir conversacion. Incluir nombre del paciente si lo conoces, motivo y accion concreta. "
    "Ejemplo: \"Paciente Marcos pregunta por radiografia con Sancor, no tengo info del convenio. Verificar y responder\".\n\n"
    "El telefono del paciente se adjunta AUTOMATICAMENTE, no lo pases vos.\n"
    "CRITICO: NUNCA llamar a esta tool sin pasar resumen no vacio. UNA sola vez por turno."
)

# ---- Parse Intent v2 (replay de escenarios 2026-10-05): urgencia primero + frases reales de cambio + continuidad con preguntas de datos / "¿le busco otra fecha?" / interrupciones
OVERRIDE_VIEJO = r"""const esPedidoReprogramar = /\b(cambiar|reprogramar|mover|pasar|posponer|anular|cancelar)\b/.test(textoNorm) &&
  /\b(turnos?|cita|horarios?|fecha|dia|tarde|manana)\b/.test(textoNorm);

if (esPedidoReprogramar) {
  intent = 'cancelar_o_reprogramar';
} else {"""

OVERRIDE_NUEVO = r"""// URGENCIA (defensa en profundidad): un sintoma o un aparato roto gana sobre "pasar/cambiar el turno".
const esUrgenciaFuerte = (/\b(dolor\w*|duele\w*|sangr\w*|hinchaz\w*|hinchad[oa]|fiebre|pincha\w*|lastima\w*)\b/.test(textoNorm) ||
  /\bse (me |le )?(salio|desprendio|despego|rompio|solto|cayo)\b.{0,40}\b(bracket|brackets|alambre|aparato|arco|banda|ligadura|expansor)/.test(textoNorm)) &&
  !/\b(sin dolor|no (me |le )?(duele|dolio)|no (tengo|tiene|siento|siente) (ningun |nada de )?(dolor|molestia)\w*|sin molestias)\b/.test(textoNorm);
// CAMBIO / CANCELACION con las formas reales de escribirlo ("cambio el turno", "lo cancelo", "no podre asistir", "antes del que me toca").
const esPedidoReprogramar = (/\b(cambi\w*|reprogramar|mover|posponer|anular|cancel\w*|adelantar|adelanto|pasar|pasarlo|pasarla)\b/.test(textoNorm) &&
  /\b(turnos?|cita|horarios?|fecha|dias?|tarde|manana|semana)\b/.test(textoNorm)) ||
  /\bno (voy a |podre |puedo |podria |llego )?(asistir|ir|llegar|concurrir|venir)\b/.test(textoNorm) ||
  (/\bantes del (que|turno)\b/.test(textoNorm) && /\bturno\b/.test(textoNorm));

if (esUrgenciaFuerte) {
  intent = 'urgencia_dolor';
} else if (esPedidoReprogramar) {
  intent = 'cancelar_o_reprogramar';
} else {"""

CONT_V2 = r"""
// === CONTINUIDAD DE FLUJO v2 (2026-10-05, caso real exec 294752 + replay de escenarios) ===
// El Router decide con el texto suelto. Si un flujo de turnos tiene una pregunta PENDIENTE (read-back, bloque de horarios, "¿le busco otra fecha?",
// "¿para quien es?", pedido de nombre/DNI) y el paciente la responde, la respuesta PERTENECE a ese flujo. Un cambio de turno se queda en
// cancelar_o_reprogramar (unico que puede reservar el nuevo y anular el viejo); una reserva pura en agendar_nuevo; nunca en confirmar_post_recordatorio.
// Sobrevive a una interrupcion (el paciente pregunta el precio en medio) hasta que el flujo se cierra ("quedo confirmado/cancelado/reprogramado", pre-reserva).
// No pisa urgencias, pagos/comprobantes, precio/alias/direccion ni adjuntos. Si el contexto falla o el ultimo turno no es del bot, sigue el Router.
let continuidad = null;
try {
  const ctxCrudo = String($('Build Router Context').first().json.ctx || '');
  const turnos = ctxCrudo.split('\n---\n').map(s => s.trim()).filter(Boolean).map(s => ({
    quien: /^PACIENTE:/.test(s) ? 'P' : (/^BOT:/.test(s) ? 'B' : 'S'),
    texto: s.replace(/^(PACIENTE|BOT|SYSTEM):\s*/, '')
  }));
  const ultimo = turnos[turnos.length - 1];
  const sinTildes = x => (x || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
  const excluir = /\b(cuanto|precio|vale|cuesta|costo|alias|cbu|transfer\w*|comprobante|abon\w*|pague|obra social|direccion|donde queda)\b|\[imagen|\[documento|\[audio/.test(textoNorm);
  if (!esUrgenciaFuerte && intent !== 'urgencia_dolor' && !excluir &&
      ultimo && ultimo.quien === 'B' && !/^\[ATENCION HUMANA/.test(ultimo.texto)) {
    const RE_CIERRE = /queda(ra)? (confirmado|cancelado|reprogramado)|quedo (confirmado|cancelado|reprogramado)|pre-?reservado/;
    const RE_CAMBIO = /reemplazando el turno|desea cambiar ese|cambiar ese por|desea cancelar|que desea cancelar|cancelar (el|ese) turno\?/;
    const RE_RESERVA = /procedo con la reserva|le confirmo:/;
    const RE_DATOS = /nombre completo|\bdni\b|para quien (es|agendo|reservo|lo agendo)|de quien es el turno|cual de ellos/;
    const RE_HORARIOS = /tenemos los proximos turnos disponibles|le sirve alguno|quiere que le busque|desea que (le )?busque|fechas mas proximas|le busco otra|otra fecha\?/;
    const recientesPaciente = turnos.slice(-6).filter(x => x.quien === 'P').map(x => sinTildes(x.texto)).join(' | ');
    const hablaDeCambio = esPedidoReprogramar || /\b(cambi\w*|reprogram\w*|mover|no podre|no puedo|otro dia|otro turno|adelant\w*|posterg\w*|reemplaz\w*|antes del (que|turno)|pasar (el )?turno)\b/.test(recientesPaciente);
    let flujo = null, pideDatos = false, esElUltimo = false, vistos = 0;
    for (let i = turnos.length - 1; i >= 0; i--) {
      const t = turnos[i];
      if (t.quien !== 'B') continue;
      vistos++;
      if (/^\[ATENCION HUMANA/.test(t.texto)) break;
      const ub = sinTildes(t.texto);
      if (RE_CIERRE.test(ub)) break;
      if (RE_CAMBIO.test(ub)) { flujo = 'cancelar_o_reprogramar'; }
      else if (RE_RESERVA.test(ub)) { flujo = 'agendar_nuevo'; }
      else if (RE_DATOS.test(ub)) { pideDatos = true; flujo = hablaDeCambio ? 'cancelar_o_reprogramar' : 'agendar_nuevo'; }
      else if (RE_HORARIOS.test(ub)) { flujo = hablaDeCambio ? 'cancelar_o_reprogramar' : 'agendar_nuevo'; }
      if (flujo) { esElUltimo = (vistos === 1); break; }
    }
    if (flujo) {
      const limpio = textoNorm.replace(/[^a-z\s]/g, ' ').replace(/\b(muchas|gracias|por favor|porfa|pf)\b/g, ' ').replace(/\s+/g, ' ').trim();
      const afirma = esElUltimo && /^(si+|dale|ok|oka|okey|listo|perfecto|de una|confirmo|proceda|procede|claro|bueno|genial|si si|si dale)$/.test(limpio);
      const eligeHorario = /\b(lunes|martes|miercoles|jueves|viernes|sabado)\b|\ba las \d|\b\d{1,2}\s*(:|\.|y)\s*\d{2}\b|\b\d{1,2}\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b|\b(el|la)\s+(primero|primera|segundo|segunda|ultimo|ultima)\b|\b(ese|esa)\b|\b(por la|a la)\s+(manana|tarde)\b/.test(textoNorm);
      const preguntaDisponibilidad = /disponib|que (fecha|dia|horario)|hay (lugar|turno)|otra (fecha|semana)|otro (dia|horario)|mas (temprano|tarde)|esta semana|semana que viene|proxim/.test(textoNorm);
      const respondeDatos = esElUltimo && pideDatos && textoNorm.length > 2 && textoNorm.length < 220;
      if (afirma || eligeHorario || preguntaDisponibilidad || respondeDatos) {
        intent = flujo;
        continuidad = 'flujo_pendiente:' + flujo;
      }
    }
  }
} catch (e) { continuidad = null; }
"""

AGENDAR_ANCLA = "REGLAS GENERALES Y ESCALACIÓN:\n"
AGENDAR_AGREGADO = (
    "- No tenés herramienta para cancelar ni reemplazar turnos: si el paciente quiere CAMBIAR un turno que ya tiene (no sumar otro), NO armes un read-back de "
    "«reemplazando» ni prometas el cambio; mostrale los horarios con buscar_horarios y el cambio lo cierra el flujo de reprogramación.\n"
    "- Si pide que lo anoten por si se libera un turno antes de la fecha: decile que se toma nota y llamá `escalar_a_secretaria` con un resumen que empiece "
    "«Lista de espera:» (no silencia al bot).\n"
)

NODOS_V6 = ["Triaje: Escalar (notify-grupo)", "escalar_a_secretaria", "Parse Intent", "Sub-Agent Agendar"]


def reemplazar_unico(texto, viejo, nuevo, donde):
    if texto.count(viejo) != 1:
        sys.exit(f"ABORTO: en {donde} la cadena a reemplazar aparece {texto.count(viejo)} veces (esperaba 1). Otra sesion cambio el nodo: revisar a mano.")
    return texto.replace(viejo, nuevo)


def transformar_parse_busqueda(code):
    """Parse Intent con la continuidad v1 (apply_fix_continuidad_flujo.py) → v2: urgencia primero, frases reales de cambio, continuidad mejorada."""
    if "CONTINUIDAD DE FLUJO v2" in code:
        sys.exit("ABORTO: 'Parse Intent' ya tiene la continuidad v2.")
    if "CONTINUIDAD DE FLUJO" not in code:
        sys.exit("ABORTO: 'Parse Intent' no tiene la continuidad de flujo (aplicar antes scripts/apply_fix_continuidad_flujo.py).")
    code = reemplazar_unico(code, OVERRIDE_VIEJO, OVERRIDE_NUEVO, "Parse Intent (override de cambio)")
    ini = code.index("\n// === CONTINUIDAD DE FLUJO")
    fin = code.index("\nreturn [{ json: { ...$input.first().json, intent, text, continuidad } }];")
    return code[:ini] + CONT_V2 + code[fin:]


def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def backup(wid, wf, label):
    HIST.mkdir(parents=True, exist_ok=True)
    dest = HIST / f"{wid}_{label}_{int(time.time())}.json"
    dest.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  backup: workflows/history/{dest.name}")


def nodo(wf, nombre):
    n = next((n for n in wf["nodes"] if n["name"] == nombre), None)
    if not n:
        sys.exit(f"ABORTO: falta el nodo '{nombre}' en {wf.get('name')}.")
    return n


def diff(titulo, a, b, max_lineas=30):
    print(f"\n--- {titulo}")
    n = 0
    for l in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0):
        if l.startswith(("---", "+++", "@@")):
            continue
        n += 1
        if n <= max_lineas:
            print("   ", l[:230])
    if n > max_lineas:
        print(f"    … ({n - max_lineas} lineas mas)")


def preparar(v6, helper):
    nv6, nh = copy.deepcopy(v6), copy.deepcopy(helper)
    # --- Helper: nodo Decidir Takeover entre la espera y Activar Takeover
    if any(n["name"] == "Decidir Takeover" for n in nh["nodes"]):
        sys.exit("ABORTO: el Helper ya tiene 'Decidir Takeover'.")
    espera, activar = nodo(nh, "Esperar respuesta del bot (20s)"), nodo(nh, "Activar Takeover Paciente")
    if nh["connections"]["Esperar respuesta del bot (20s)"]["main"] != [[{"node": "Activar Takeover Paciente", "type": "main", "index": 0}]]:
        sys.exit("ABORTO: la conexion Espera → Activar Takeover no es la esperada. Revisar a mano.")
    x = (espera["position"][0] + activar["position"][0]) // 2
    nh["nodes"].append({"id": str(uuid.uuid4()), "name": "Decidir Takeover", "type": "n8n-nodes-base.code", "typeVersion": 2,
                        "position": [x, espera["position"][1] - 120], "parameters": {"jsCode": DECIDIR_TAKEOVER_JS}})
    nh["connections"]["Esperar respuesta del bot (20s)"]["main"] = [[{"node": "Decidir Takeover", "type": "main", "index": 0}]]
    nh["connections"]["Decidir Takeover"] = {"main": [[{"node": "Activar Takeover Paciente", "type": "main", "index": 0}]]}
    print("--- Helper · nodo nuevo 'Decidir Takeover' (Code)\n    Esperar respuesta del bot (20s) → Decidir Takeover → Activar Takeover Paciente")
    print("    corta (no silencia) salvo tomar=true o resumen con: pidió hablar / queja / reclamo / baja de datos / urgencia / dolor / sangrado")
    # --- v6
    n = nodo(nv6, "Triaje: Escalar (notify-grupo)"); viejo = n["parameters"]["jsCode"]
    n["parameters"]["jsCode"] = reemplazar_unico(viejo, TRIAJE_VIEJO, TRIAJE_NUEVO, "Triaje: Escalar")
    diff("v6 · Triaje: Escalar (notify-grupo)", viejo, n["parameters"]["jsCode"])
    n = nodo(nv6, "escalar_a_secretaria"); viejo = n["parameters"]["toolDescription"]
    if not viejo.startswith(TOOL_DESC_PREFIJO):
        sys.exit("ABORTO: la descripcion de escalar_a_secretaria no es la esperada. Revisar a mano.")
    n["parameters"]["toolDescription"] = TOOL_DESC_NUEVA
    diff("v6 · escalar_a_secretaria (descripcion que lee el modelo)", viejo, TOOL_DESC_NUEVA, 40)
    n = nodo(nv6, "Parse Intent"); viejo = n["parameters"]["jsCode"]
    n["parameters"]["jsCode"] = transformar_parse_busqueda(viejo)
    diff("v6 · Parse Intent", viejo, n["parameters"]["jsCode"])
    n = nodo(nv6, "Sub-Agent Agendar"); viejo = n["parameters"]["options"]["systemMessage"]
    n["parameters"]["options"]["systemMessage"] = reemplazar_unico(viejo, AGENDAR_ANCLA, AGENDAR_ANCLA + AGENDAR_AGREGADO, "Sub-Agent Agendar")
    diff("v6 · prompt de Sub-Agent Agendar", viejo, n["parameters"]["options"]["systemMessage"])
    return nv6, nh


def put(wid, wf):
    body = {k: wf[k] for k in PUT_KEYS if k in wf}
    body["settings"] = {k: v for k, v in (wf.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{wid}", method="PUT", payload=body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    v6, helper = api(f"/workflows/{V6}"), api(f"/workflows/{HELPER}")
    print(f"v6 active={v6.get('active')} nodos={len(v6['nodes'])} v={v6.get('versionId')[:8]} | Helper active={helper.get('active')} nodos={len(helper['nodes'])} v={helper.get('versionId')[:8]}\n")
    nv6, nh = preparar(v6, helper)

    if not args.apply:
        print("\n[SIMULACION] No se aplico nada. Correr con --apply (con OK de Lucas).")
        return
    if api(f"/workflows/{V6}").get("versionId") != v6.get("versionId") or api(f"/workflows/{HELPER}").get("versionId") != helper.get("versionId"):
        sys.exit("ABORTO: un workflow cambio mientras preparaba el fix (otra sesion hizo un PUT). Volver a correr.")
    backup(HELPER, helper, "PRE_politica_modo_humano")
    backup(V6, v6, "PRE_politica_modo_humano")
    put(HELPER, nh)          # primero el Helper: sin el nodo nuevo el v6 seguiria silenciando como antes
    put(V6, nv6)
    ph, pv = api(f"/workflows/{HELPER}"), api(f"/workflows/{V6}")
    backup(HELPER, ph, "POST_politica_modo_humano")
    backup(V6, pv, "POST_politica_modo_humano")
    a, d = {n["name"]: n for n in v6["nodes"]}, {n["name"]: n for n in pv["nodes"]}
    ha, hd = {n["name"]: n for n in helper["nodes"]}, {n["name"]: n for n in ph["nodes"]}
    chequeos = {
        "v6: solo cambiaron los 4 nodos previstos": sorted(k for k in a if a[k] != d.get(k)) == sorted(NODOS_V6),
        "v6: mismos nodos y conexiones": set(a) == set(d) and v6["connections"] == pv["connections"],
        "v6: webhookId evo-webhook-v2 intacto y activo": d["Webhook - Evolution API"].get("webhookId") == "evo-webhook-v2" and pv.get("active") is True,
        "Helper: solo se agrego 'Decidir Takeover'": sorted(set(hd) - set(ha)) == ["Decidir Takeover"] and not (set(ha) - set(hd)) and all(ha[k] == hd[k] for k in ha),
        "Helper: Espera → Decidir → Activar": ph["connections"]["Esperar respuesta del bot (20s)"]["main"][0][0]["node"] == "Decidir Takeover"
                                               and ph["connections"]["Decidir Takeover"]["main"][0][0]["node"] == "Activar Takeover Paciente",
        "Helper: sigue activo": ph.get("active") is True,
    }
    ok = True
    for k, v in chequeos.items():
        print(f"  {'OK   ' if v else 'FALLA'} {k}")
        ok &= v
    if not ok:
        sys.exit("VERIFICACION FALLIDA: restaurar con scripts/restaurar_workflow.py <backup PRE>.")
    print("\nAplicado. Falta la prueba real y limpiar el numero de prueba.")


if __name__ == "__main__":
    main()
