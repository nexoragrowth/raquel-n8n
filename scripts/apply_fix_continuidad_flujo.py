# -*- coding: utf-8 -*-
"""
apply_fix_continuidad_flujo.py — el flujo en curso se queda con la respuesta del paciente (2026-10-05).

CASO REAL (exec 294718 → 294752, paciente que queria cambiar un turno): en una sola charla el Router la paso por TRES agentes:
Cancelar/reprogramar → Agendar → Cancelar → Agendar → Confirmar. Al final, Agendar armo "Le confirmo: ... reemplazando el turno del
viernes 16/10 ... ¿Procedo con la reserva?" (Agendar NO puede reemplazar: solo reserva) y el "Si / Gracias" fue a Confirmar
(confirmar_post_recordatorio), que tampoco puede mover turnos y derivo a la secretaria. El Router decide con el texto suelto:
un "si" iba a Confirmar y un horario elegido iba a Agendar sin mirar que flujo estaba en curso.
Quien SI puede cambiar un turno es el sub-workflow Cancelar/Reprogramar (POST de la cita nueva + PUT que anula la vieja).

CAMBIO 1 · `Parse Intent` (determinístico, antes del return): si el ULTIMO mensaje del bot dejo una pregunta pendiente
  - read-back de reemplazo / de cancelacion         → flujo = cancelar_o_reprogramar
  - read-back de reserva "¿Procedo con la reserva?"  → flujo = agendar_nuevo (NUNCA confirmar_post_recordatorio)
  - bloque de horarios "Tenemos los próximos turnos…" → cancelar_o_reprogramar si en los ultimos turnos el paciente hablaba de
    cambiar/reprogramar/no poder; si no, agendar_nuevo
  y el paciente responde con un "si" corto, elige un horario o pregunta por disponibilidad, el intent es el del flujo pendiente.
  No pisa: urgencias, pagos/comprobantes, consultas de precio/alias/direccion, adjuntos. Si el ctx falla o el ultimo turno es del staff,
  no hace nada (sigue el Router).

CAMBIO 2 · `Gate Canned Directo` (error mio del cambio de las directrices, ya aplicado): cuando NO hay mensajes previos, el contexto vale
  '(sin mensajes previos)' (COALESCE de `Build Router Context`) y la regla del menu de bienvenida solo reconocia '' y '(sin contexto)':
  el menu editable nunca se activaba. Se agrega ese valor.

USO:
    python scripts/apply_fix_continuidad_flujo.py            # simulacion (solo GET): muestra el diff
    python scripts/apply_fix_continuidad_flujo.py --apply    # backup PRE + PUT + verificacion + backup POST

Regla del proyecto: NUNCA --apply sin OK de Lucas. Despues: prueba real desde el numero de prueba (ver tests/test_continuidad_flujo.py,
casos 1-3 son la charla real) y limpiar el numero (scripts/limpiar_numero_demo.py).
"""
import argparse, copy, difflib, json, re, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
WF_ID = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}

PARSE_MARCA = "\nreturn [{ json: { ...$input.first().json, intent, text } }];"
PARSE_RETURN_NUEVO = "\nreturn [{ json: { ...$input.first().json, intent, text, continuidad } }];"

CONTINUIDAD_SNIPPET = r"""
// === CONTINUIDAD DE FLUJO (2026-10-05, caso real exec 294752) ===
// El Router decide con el texto suelto: un "si" iba a Confirmar y un horario elegido a Agendar aunque la charla estuviera en un
// cambio de turno. Si el ULTIMO mensaje del bot dejo una pregunta pendiente (read-back o bloque de horarios) y el paciente responde
// con un "si" corto, elige un horario o pregunta por disponibilidad, la respuesta PERTENECE a ese flujo. No pisa urgencias, pagos,
// consultas de precio/alias/direccion ni adjuntos. Si el contexto falla o el ultimo turno no es del bot, sigue el Router.
let continuidad = null;
try {
  const ctxCrudo = String($('Build Router Context').first().json.ctx || '');
  const turnos = ctxCrudo.split('\n---\n').map(s => s.trim()).filter(Boolean).map(s => ({
    quien: /^PACIENTE:/.test(s) ? 'P' : (/^BOT:/.test(s) ? 'B' : 'S'),
    texto: s.replace(/^(PACIENTE|BOT|SYSTEM):\s*/, '')
  }));
  const ultimo = turnos[turnos.length - 1];
  const sinTildes = x => (x || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
  const excluir = /\b(cuanto|precio|vale|cuesta|costo|alias|cbu|transfer\w*|comprobante|abon\w*|pague|obra social|direccion|donde queda)\b|\[imagen|\[documento|\[audio|dolor|duele|sangr\w*|bracket|alambre|urgenc\w*/.test(textoNorm);
  if (ultimo && ultimo.quien === 'B' && !/^\[ATENCION HUMANA/.test(ultimo.texto) && intent !== 'urgencia_dolor' && !excluir) {
    const ub = sinTildes(ultimo.texto);
    const esReemplazo = /reemplazando el turno|desea cambiar ese|cambiar ese por/.test(ub);
    const esReadbackCancelar = /desea cancelar|que desea cancelar|cancelar (el|ese) turno\?/.test(ub);
    const esReadbackReserva = /procedo con la reserva|le confirmo:/.test(ub);
    const esBloqueHorarios = /tenemos los proximos turnos disponibles|le sirve alguno/.test(ub);
    let flujo = null;
    if (esReemplazo || esReadbackCancelar) {
      flujo = 'cancelar_o_reprogramar';
    } else if (esReadbackReserva) {
      flujo = 'agendar_nuevo';
    } else if (esBloqueHorarios) {
      const recientesPaciente = turnos.slice(-6).filter(x => x.quien === 'P').map(x => sinTildes(x.texto)).join(' | ');
      flujo = /\b(cambi\w*|reprogram\w*|pasar (el )?turno|mover|no podre|no puedo|otro dia|otro turno|adelantar|posterg\w*|reemplaz\w*)\b/.test(recientesPaciente)
        ? 'cancelar_o_reprogramar' : 'agendar_nuevo';
    }
    if (flujo) {
      const limpio = textoNorm.replace(/[^a-z\s]/g, ' ').replace(/\b(muchas|gracias|por favor|porfa|pf)\b/g, ' ').replace(/\s+/g, ' ').trim();
      const afirma = /^(si+|dale|ok|oka|okey|listo|perfecto|de una|confirmo|proceda|procede|claro|bueno|genial|si si|si dale)$/.test(limpio);
      const eligeHorario = /\b(lunes|martes|miercoles|jueves|viernes|sabado)\b|\ba las \d|\b\d{1,2}\s*(:|\.|y)\s*\d{2}\b|\b\d{1,2}\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b|\b(el|la)\s+(primero|primera|segundo|segunda|ultimo|ultima)\b|\b(ese|esa)\b|\b(por la|a la)\s+(manana|tarde)\b/.test(textoNorm);
      const preguntaDisponibilidad = /disponib|que (fecha|dia|horario)|hay (lugar|turno)|otra (fecha|semana)|otro (dia|horario)|mas (temprano|tarde)|esta semana|semana que viene|proxim/.test(textoNorm);
      if (afirma || eligeHorario || preguntaDisponibilidad) {
        intent = flujo;
        continuidad = 'flujo_pendiente:' + flujo;
      }
    }
  }
} catch (e) { continuidad = null; }
"""

GATE_VIEJO = "const conversacionNueva = ctxPrevio === '' || ctxPrevio === '(sin contexto)';"
GATE_NUEVO = "const conversacionNueva = ctxPrevio === '' || ctxPrevio === '(sin contexto)' || ctxPrevio === '(sin mensajes previos)';"


def reemplazar_unico(texto, viejo, nuevo, donde):
    if texto.count(viejo) != 1:
        sys.exit(f"ABORTO: en {donde} la cadena a reemplazar aparece {texto.count(viejo)} veces (esperaba 1). Otra sesion cambio el nodo: revisar a mano.")
    return texto.replace(viejo, nuevo)


def transformar_parse(code):
    if "CONTINUIDAD DE FLUJO" in code:
        sys.exit("ABORTO: 'Parse Intent' ya tiene la continuidad de flujo (¿se aplico antes?).")
    code = reemplazar_unico(code, PARSE_MARCA, CONTINUIDAD_SNIPPET + PARSE_RETURN_NUEVO, "Parse Intent")
    return code


def transformar_gate(code):
    if "(sin mensajes previos)" in code:
        sys.exit("ABORTO: 'Gate Canned Directo' ya reconoce '(sin mensajes previos)'.")
    return reemplazar_unico(code, GATE_VIEJO, GATE_NUEVO, "Gate Canned Directo")


def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def backup(wf, label):
    HIST.mkdir(parents=True, exist_ok=True)
    dest = HIST / f"{WF_ID}_{label}_{int(time.time())}.json"
    dest.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  backup: workflows/history/{dest.name}")


def nodo(wf, nombre):
    n = next((n for n in wf["nodes"] if n["name"] == nombre), None)
    if not n:
        sys.exit(f"ABORTO: falta el nodo '{nombre}'.")
    return n


def mostrar_diff(titulo, a, b):
    print(f"\n--- {titulo}")
    for l in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0):
        if not l.startswith(("---", "+++", "@@")):
            print("   ", l[:250])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    wf = api(f"/workflows/{WF_ID}")
    print(f"v6 {WF_ID} | active={wf.get('active')} | {len(wf['nodes'])} nodos | versionId={wf.get('versionId')}")
    nuevo = copy.deepcopy(wf)
    n = nodo(nuevo, "Parse Intent"); viejo = n["parameters"]["jsCode"]
    n["parameters"]["jsCode"] = transformar_parse(viejo)
    mostrar_diff("1 · Parse Intent (continuidad de flujo)", viejo, n["parameters"]["jsCode"])
    n = nodo(nuevo, "Gate Canned Directo"); viejo = n["parameters"]["jsCode"]
    n["parameters"]["jsCode"] = transformar_gate(viejo)
    mostrar_diff("2 · Gate Canned Directo (el menu editable no se activaba)", viejo, n["parameters"]["jsCode"])

    if not args.apply:
        print("\n[SIMULACION] No se aplico nada. Correr con --apply (con OK de Lucas).")
        return
    if api(f"/workflows/{WF_ID}").get("versionId") != wf.get("versionId"):
        sys.exit("ABORTO: el workflow cambio mientras preparaba el fix (otra sesion hizo un PUT). Volver a correr.")
    backup(wf, "PRE_continuidad_flujo")
    body = {k: nuevo[k] for k in PUT_KEYS if k in nuevo}
    body["settings"] = {k: v for k, v in (nuevo.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{WF_ID}", method="PUT", payload=body)
    post = api(f"/workflows/{WF_ID}")
    backup(post, "POST_continuidad_flujo")
    a, d = {x["name"]: x for x in wf["nodes"]}, {x["name"]: x for x in post["nodes"]}
    cambiados = sorted(k for k in a if a[k] != d.get(k))
    chequeos = {
        "solo cambiaron Parse Intent y Gate Canned Directo": cambiados == ["Gate Canned Directo", "Parse Intent"],
        "misma cantidad de nodos y conexiones identicas": len(a) == len(d) and wf["connections"] == post["connections"],
        "webhookId evo-webhook-v2 intacto": d["Webhook - Evolution API"].get("webhookId") == "evo-webhook-v2",
        "workflow sigue activo": post.get("active") is True,
    }
    ok = True
    for k, v in chequeos.items():
        print(f"  {'OK   ' if v else 'FALLA'} {k}" + ("" if v else f"  (cambiados={cambiados})"))
        ok &= v
    if not ok:
        sys.exit("VERIFICACION FALLIDA: restaurar con scripts/restaurar_workflow.py <backup PRE>.")
    print("\nAplicado. Falta la prueba real (ver cabecera) y limpiar el numero de prueba.")


if __name__ == "__main__":
    main()
