# -*- coding: utf-8 -*-
"""
apply_fix_subwf_reprogramar.py — 2026-10-05 (v2, tras leer el sub-WF entero y repetir la charla real de Dana turno por turno)

Sub-WF "CancelarReprogramar" (5cAWJxiWJ50hxEq3): el unico flujo que puede reservar el turno nuevo y anular el viejo.
Dato de contexto: en 90 dias ese camino de escritura corrio UNA sola vez (14/9, verificado en la agenda: cita nueva con comentario
"Reprogramado por bot (sub-WF)" + vieja anulada). Desde el arreglo de continuidad de hoy va a empezar a correr seguido: por eso las guardas.

QUE CAMBIA (8 nodos Code, ninguna conexion):

 1) MENSAJE HONESTO (Step 7). `Step 7` leia primero el mensaje optimista del `Step 5` ("Listo, reprogramado..." / "...queda cancelado")
    aunque la agenda hubiera rechazado la escritura: la paciente creia tener (o haber cancelado) un turno que no. Ahora, en las dos ramas
    que escriben (reservar_y_cancelar y cancelar_turno), vale el mensaje del nodo que vio la respuesta de la agenda (6d-4 / 6d-3b / 6a-out).
 2) READ-BACK DE REEMPLAZO (Step 0b / 3.5a / 3.5c / 5). Caso real exec 294752: el bot pregunto "Le confirmo: Jueves 22 de octubre a las
    09:20 hs ..., reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?" y la paciente dijo "Si / Gracias".
    Si la respuesta es SOLO una afirmacion, el turno nuevo y el viejo se leen POR CODIGO del read-back (sin LLM) y se ejecuta el cambio,
    siempre que el turno viejo exista (uno solo) en la ficha. No toca la maquina de estados: cualquier otra respuesta sigue como antes.
 3) GUARDAS DE ESCRITURA (Step 5). Solo descartan aceptaciones, nunca habilitan una escritura nueva:
      a. varias fichas en el mismo celular y sin turno enganchado por Step 4 → no se escribe (los turnos traidos pueden ser de otra ficha);
      b. read-back: el turno viejo nombrado tiene que existir y coincidir con el de Step 4;
      c. aceptacion del LLM: el horario elegido tiene que haber sido ofrecido por el bot en un bloque reciente de la memoria.
 4) TEXTOS (Step 5 / 6d-3b / 6d-4 / 6a-out): de "usted" como el resto de Asiri, y cuando falla dicen que el turno actual sigue vigente.

USO:  python scripts/apply_fix_subwf_reprogramar.py            # simulacion: muestra el diff, no escribe nada
      python scripts/apply_fix_subwf_reprogramar.py --apply    # backup PRE + PUT + verificacion + backup POST
Regla del proyecto: NUNCA --apply sin OK de Lucas.  Tests previos:  python tests/test_flujo_dana_subwf.py
"""
import argparse, copy, difflib, json, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
WID = "5cAWJxiWJ50hxEq3"
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}
MARCA = "READ-BACK DE REEMPLAZO (2026-10-05"

# ------------------------------------------------------------------ Step 0b: leer el read-back de reemplazo por codigo
B0_VIEJO = "return [{ json: {\n  ...trigger,\n  multi_turn_state,\n"
B0_NUEVO = r"""// === READ-BACK DE REEMPLAZO (2026-10-05, caso real exec 294752) ===
// El Sub-Agent Agendar a veces confirma un cambio con un read-back: "Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel,
// reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?". Si el paciente SOLO afirma ("Si", "Si gracias", "Dale"),
// lo que acepto esta escrito ahi: el turno nuevo y el turno viejo. Se leen POR CODIGO (sin LLM) y "Step 5" verifica que el turno viejo exista
// antes de escribir. Cualquier otra respuesta, o un read-back que no se pueda leer entero, sigue el flujo de siempre (readback_accept = null).
let readback_accept = null;
try {
  const __sinT = (x) => String(x || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const __rb = __sinT(lastBotMsg);
  const __resp = __sinT(trigger.text).replace(/[^a-z\s]/g, ' ').replace(/\b(muchas|gracias|por favor|porfa|pf)\b/g, ' ').replace(/\s+/g, ' ').trim();
  const __afirma = /^(si+|dale|ok|oka|okey|listo|perfecto|de una|confirmo|proceda|procede|claro|bueno|genial|si si|si dale)$/.test(__resp);
  if (__afirma && /procedo con la reserva/.test(__rb) && /reemplazando el turno/.test(__rb)) {
    const __MES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
    const __mesNum = (s) => __MES.indexOf(s === 'setiembre' ? 'septiembre' : s) + 1;
    const __iso = (dia, mes) => {
      if (!(mes >= 1 && mes <= 12) || !(dia >= 1 && dia <= 31)) return '';
      const mm = String(mes).padStart(2, '0'), dd = String(dia).padStart(2, '0');
      const anio = Number(HOY_JUJUY.slice(0, 4));
      const cand = anio + '-' + mm + '-' + dd;
      return cand >= HOY_JUJUY ? cand : (anio + 1) + '-' + mm + '-' + dd;
    };
    const __hhmm = (h, m) => String(Number(h)).padStart(2, '0') + ':' + m;
    const __partes = __rb.split('reemplazando el turno');
    const __mN = /le confirmo:\s*[^\d]*?(\d{1,2})\s+de\s+([a-z]+)[^\d]*?(\d{1,2}):(\d{2})/.exec(__partes[0]);
    const __mV = /^\s*(?:del|de)\s+[^\d]*?(\d{1,2})(?:\s*\/\s*(\d{1,2})|\s+de\s+([a-z]+))(?:[^\d]*?(\d{1,2}):(\d{2}))?/.exec(__partes[1] || '');
    if (__partes.length === 2 && __mN && __mV) {
      const __fN = __iso(Number(__mN[1]), __mesNum(__mN[2]));
      const __fV = __iso(Number(__mV[1]), __mV[2] ? Number(__mV[2]) : __mesNum(__mV[3]));
      if (__fN && __fV) {
        readback_accept = {
          slot: { fecha: __fN, hora_inicio: __hhmm(__mN[3], __mN[4]) },
          viejo: { fecha: __fV, hora: __mV[4] ? __hhmm(__mV[4], __mV[5]) : null }
        };
      }
    }
  }
} catch (e) { readback_accept = null; }

return [{ json: {
  ...trigger,
  multi_turn_state,
  readback_accept,
"""

# ------------------------------------------------------------------ Step 3.5a: si ya hay read-back leido por codigo, no se llama al LLM
A_VIEJO = "trig = trig || {};\nconst state = "
A_NUEVO = r"""trig = trig || {};
// READ-BACK DE REEMPLAZO ya leido por codigo en "Step 0b": no se le pregunta al LLM (el read-back nombra tambien el turno viejo y lo confunde).
if (trig.readback_accept && trig.readback_accept.slot && trig.readback_accept.slot.fecha) {
  return [{ json: { ...prev, _skip_acceptance: true, _det_accept: {
    accepts: true, slot_chosen: trig.readback_accept.slot, turno_viejo: trig.readback_accept.viejo || null,
    origen: 'readback', razon: 'afirma el read-back de reemplazo (leido por codigo)'
  } } }];
}
const state = """

# ------------------------------------------------------------------ Step 3.5c: la aceptacion leida por codigo pasa tal cual
C_VIEJO = "const prev = $('Step 3.5a: Prep Acceptance LLM').first().json;\n"
C_NUEVO = C_VIEJO + "if (prev._det_accept) { return [{ json: { ...prev, acceptance_intent: prev._det_accept } }]; }\n"

# ------------------------------------------------------------------ Step 5: guardas de escritura + turno viejo del read-back + texto de exito
S5_ACCEPT_VIEJO = "const accept = prev.acceptance_intent || { accepts: null, slot_chosen: null };\n"
S5_ACCEPT_NUEVO = r"""let accept = prev.acceptance_intent || { accepts: null, slot_chosen: null };

// === GUARDAS DE ESCRITURA (2026-10-05). Solo DESCARTAN aceptaciones que no se pueden respaldar; nunca habilitan una escritura nueva. ===
//  (a) Varias fichas en el mismo celular y "Step 4" no engancho un turno: no se escribe (los turnos traidos pueden ser de otra ficha).
//  (b) Aceptacion por READ-BACK DE REEMPLAZO: el turno viejo que nombra el read-back tiene que existir (uno solo) y coincidir con el de "Step 4".
//  (c) Aceptacion del LLM: el horario elegido tiene que haber sido OFRECIDO por el bot en un bloque reciente (si hay bloques legibles en la memoria).
// Si se descarta, el flujo sigue exactamente como cuando el paciente no acepto nada.
const __normHora = (h) => { const m = /^(\d{1,2}):(\d{2})/.exec(String(h || '')); return m ? m[1].padStart(2, '0') + ':' + m[2] : ''; };
let __multi = false;
try { __multi = $('Step 1b: Procesar resultado').first().json.multiple_fichas === true; } catch (e) { __multi = false; }
let __turnoReadback = null;
let __descarte = '';
if (accept.accepts === true && accept.slot_chosen && accept.slot_chosen.fecha) {
  if (__multi && !turno) {
    __descarte = 'varias_fichas_sin_turno_enganchado';
  } else if (accept.origen === 'readback') {
    const v = accept.turno_viejo || {};
    const cand = turnos.filter(t => t.fecha === v.fecha && (!v.hora || __normHora(t.hora_inicio) === v.hora));
    if (cand.length !== 1) __descarte = 'readback_turno_viejo_no_encontrado';
    else if (turno && turno.id !== cand[0].id) __descarte = 'readback_turno_viejo_distinto_al_de_step4';
    else __turnoReadback = cand[0];
  } else {
    const __ofrecidos = new Set();
    try {
      const __hoy = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Argentina/Jujuy' }).format(new Date());
      const __MES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
      const __sinT = (x) => String(x || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
      for (const it of ($('Step 0a: Read Chat Memory').all() || [])) {
        let m = it.json && it.json.message;
        if (typeof m === 'string') { try { m = JSON.parse(m); } catch (e) { m = null; } }
        if (!m || m.type !== 'ai') continue;
        const c = String(m.content || '');
        if (!/turnos disponibles:/i.test(c)) continue;
        for (const raw of c.split('\n')) {
          const l = __sinT(raw.trim());
          const lm = /^\*\s*[^\d]+?(\d{1,2})\s+de\s+([a-z]+)\s+(.*)$/.exec(l);
          if (!lm) continue;
          const mes = __MES.indexOf(lm[2] === 'setiembre' ? 'septiembre' : lm[2]) + 1;
          if (!mes) continue;
          const mm = String(mes).padStart(2, '0'), dd = String(Number(lm[1])).padStart(2, '0');
          const anio = Number(__hoy.slice(0, 4));
          const iso = (anio + '-' + mm + '-' + dd) >= __hoy ? (anio + '-' + mm + '-' + dd) : ((anio + 1) + '-' + mm + '-' + dd);
          for (const h of (lm[3].match(/\d{1,2}:\d{2}/g) || [])) __ofrecidos.add(iso + ' ' + __normHora(h));
        }
      }
    } catch (e) { /* sin memoria legible no se valida (comportamiento anterior) */ }
    if (__ofrecidos.size > 0 && !__ofrecidos.has(accept.slot_chosen.fecha + ' ' + __normHora(accept.slot_chosen.hora_inicio))) {
      __descarte = 'horario_no_ofrecido_por_el_bot';
    }
  }
  if (__descarte) accept = { accepts: null, slot_chosen: null, razon: 'descartada: ' + __descarte };
}
const __readbackOk = !!__turnoReadback;
"""

S5_INFO_VIEJO = "if (dec.siguiente_paso === 'responder_info') {\n"
S5_INFO_NUEVO = ("// Un read-back de reemplazo confirmado y verificado gana sobre una lectura \"consulta de info\" del LLM de intencion (el paciente dijo solo \"Si\").\n"
                 "if (dec.siguiente_paso === 'responder_info' && !__readbackOk) {\n")

S5_TCANCELAR_VIEJO = "  const tCancelar = turno || (turnos.length === 1 ? turnos[0] : null);\n"
S5_TCANCELAR_NUEVO = "  const tCancelar = __readbackOk ? __turnoReadback : (turno || (turnos.length === 1 ? turnos[0] : null));\n"

S5_MSG_VIEJO = ("    mensaje_final: 'Listo, reprogramado: cancele el ' + fechaNatural(tCancelar.fecha) + ' a las ' + horaNatural(tCancelar.hora_inicio) + ' y te reserve el ' "
                "+ fechaNatural(accept.slot_chosen.fecha) + ' a las ' + horaNatural(accept.slot_chosen.hora_inicio) + '. Cualquier consulta nos escribis.'\n")
S5_MSG_NUEVO = ("    descarte_aceptacion: __descarte || null,\n"
                "    mensaje_final: 'Listo, quedó reprogramado su turno: anulé el del ' + fechaNatural(tCancelar.fecha) + ' a las ' + horaNatural(tCancelar.hora_inicio) + ' y le reservé el ' "
                "+ fechaNatural(accept.slot_chosen.fecha) + ' a las ' + horaNatural(accept.slot_chosen.hora_inicio) + '. Cualquier consulta, nos escribe.'\n")

# ------------------------------------------------------------------ Step 7: en las ramas que escriben vale el mensaje del nodo que vio la respuesta de la agenda
S7_VIEJO = "const mf = fromStep5.mensaje_final || prev.mensaje_final || 'Le paso a la secretaria.';"
S7_NUEVO = ("// En las dos ramas que ESCRIBEN en la agenda (reservar_y_cancelar / cancelar_turno) el mensaje que vale es el del nodo que vio la respuesta de la\n"
            "// agenda (6d-4 / 6d-3b / 6a-out): si salio bien es el mismo del Step 5; si fallo, el del Step 5 es un \"Listo...\" optimista y seria mentirle al paciente.\n"
            "const __escribe = fromStep5.action_to_execute === 'reservar_y_cancelar' || fromStep5.action_to_execute === 'cancelar_turno';\n"
            "const mf = (__escribe && prev.mensaje_final) ? prev.mensaje_final : (fromStep5.mensaje_final || prev.mensaje_final || 'Le paso a la secretaria.');")

# ------------------------------------------------------------------ textos de falla (de "usted" + el turno actual sigue vigente)
F3B_VIEJO = "  mensaje_final: 'No pude reservar el horario que elegiste. Le paso a la secretaria para que lo coordine manualmente.',"
F3B_NUEVO = "  mensaje_final: 'No pude reservar ese horario: puede que se haya ocupado recién. Su turno actual sigue vigente, no se modificó nada. Le aviso a la secretaria para que lo coordine con usted.',"
F4_VIEJO = "  mensaje = 'Te reserve el nuevo turno, pero no logre cancelar el anterior automaticamente. Le paso a la secretaria para que ajuste.';"
F4_NUEVO = "  mensaje = 'Le reservé el nuevo turno, pero no pude anular el anterior. Le aviso a la secretaria para que lo ajuste.';"
F6A_VIEJO = "  mensaje_final: success ? prev.mensaje_final : 'No pude cancelar el turno en el sistema. Le paso a la secretaria para que lo coordine.',"
F6A_NUEVO = "  mensaje_final: success ? prev.mensaje_final : 'No pude cancelar el turno en este momento: sigue vigente. Le aviso a la secretaria para que lo coordine con usted.',"

CAMBIOS = [
    ("Step 0b: Detect Multi-Turn State", [(B0_VIEJO, B0_NUEVO)]),
    ("Step 3.5a: Prep Acceptance LLM", [(A_VIEJO, A_NUEVO)]),
    ("Step 3.5c: Parse Acceptance", [(C_VIEJO, C_NUEVO)]),
    ("Step 5: Decidir Accion Ejecutable", [(S5_ACCEPT_VIEJO, S5_ACCEPT_NUEVO), (S5_INFO_VIEJO, S5_INFO_NUEVO),
                                           (S5_TCANCELAR_VIEJO, S5_TCANCELAR_NUEVO), (S5_MSG_VIEJO, S5_MSG_NUEVO)]),
    ("Step 7: Output Final", [(S7_VIEJO, S7_NUEVO)]),
    ("Step 6d-3b: Escalar Reserva Falla", [(F3B_VIEJO, F3B_NUEVO)]),
    ("Step 6d-4: Consolidar Resultado", [(F4_VIEJO, F4_NUEVO)]),
    ("Step 6a-out: Resultado Cancelar", [(F6A_VIEJO, F6A_NUEVO)]),
]


def reemplazar_unico(texto, viejo, nuevo, donde):
    if texto.count(viejo) != 1:
        sys.exit(f"ABORTO: en {donde} la cadena a reemplazar aparece {texto.count(viejo)} veces (esperaba 1). Ya aplicado o cambiado a mano: revisar.\n  cadena: {viejo[:90]!r}")
    return texto.replace(viejo, nuevo)


def transformar(wf):
    """Devuelve una copia del sub-WF con los cambios (lo usan el --apply y tests/test_flujo_dana_subwf.py)."""
    if any(MARCA in (n.get("parameters", {}).get("jsCode") or "") for n in wf["nodes"]):
        sys.exit("ABORTO: el sub-WF ya tiene este arreglo aplicado.")
    nuevo = copy.deepcopy(wf)
    for nombre, reemplazos in CAMBIOS:
        n = next((n for n in nuevo["nodes"] if n["name"] == nombre), None)
        if not n:
            sys.exit(f"ABORTO: falta el nodo '{nombre}'.")
        code = n["parameters"]["jsCode"]
        for viejo, nvo in reemplazos:
            code = reemplazar_unico(code, viejo, nvo, nombre)
        n["parameters"]["jsCode"] = code
    return nuevo


def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    apply = ap.parse_args().apply
    wf = api(f"/workflows/{WID}")
    nuevo = transformar(wf)
    print(f"Sub-WF {wf['name']} active={wf.get('active')} nodos={len(wf['nodes'])} v={wf.get('versionId')[:8]}")
    for (nombre, _r) in CAMBIOS:
        a = next(n for n in wf["nodes"] if n["name"] == nombre)["parameters"]["jsCode"]
        b = next(n for n in nuevo["nodes"] if n["name"] == nombre)["parameters"]["jsCode"]
        print(f"\n--- {nombre}")
        k = 0
        for l in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0):
            if l.startswith(("---", "+++", "@@")):
                continue
            k += 1
            if k <= 12:
                print("   ", l[:210])
        if k > 12:
            print(f"    … ({k - 12} lineas mas)")
    if not apply:
        print("\n[SIMULACION] No se aplico nada. Correr con --apply (con OK de Lucas).")
        return
    HIST.mkdir(parents=True, exist_ok=True)
    pre = HIST / f"{WID}_PRE_fix_subwf_reprogramar_{int(time.time())}.json"
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n  backup:", pre.name)
    if api(f"/workflows/{WID}").get("versionId") != wf.get("versionId"):
        sys.exit("ABORTO: el sub-WF cambio mientras preparaba el PUT.")
    body = {k: nuevo[k] for k in PUT_KEYS if k in nuevo}
    body["settings"] = {k: v for k, v in (nuevo.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{WID}", method="PUT", payload=body)
    post = api(f"/workflows/{WID}")
    (HIST / f"{WID}_POST_fix_subwf_reprogramar_{int(time.time())}.json").write_text(json.dumps(post, indent=2, ensure_ascii=False), encoding="utf-8")
    viejos = {n["name"]: n for n in wf["nodes"]}
    cambiados = sorted(n["name"] for n in post["nodes"] if viejos.get(n["name"]) != n)
    esperados = sorted(n for n, _ in CAMBIOS)
    codigo_ok = all(next(n for n in post["nodes"] if n["name"] == nombre)["parameters"]["jsCode"]
                    == next(n for n in nuevo["nodes"] if n["name"] == nombre)["parameters"]["jsCode"] for nombre in esperados)
    print("  nodos que cambiaron:", cambiados)
    print("  codigo vivo == codigo probado:", codigo_ok, "| activo:", post.get("active"),
          "| mismas conexiones:", wf["connections"] == post["connections"], "| mismos nodos:", len(wf["nodes"]) == len(post["nodes"]))
    if cambiados != esperados or not codigo_ok or not post.get("active") or wf["connections"] != post["connections"]:
        sys.exit("ATENCION: la verificacion no dio lo esperado. Restaurar con: python scripts/restaurar_workflow.py workflows/history/" + pre.name + " --apply")
    print("Aplicado.")


if __name__ == "__main__":
    main()
