# -*- coding: utf-8 -*-
"""
apply_fix_ruteo_consultas_cambio.py — 2026-10-05 (correccion de la continuidad de flujo aplicada hoy; v6 `Parse Intent`)

PROBLEMA (encontrado repitiendo la charla real de Dana turno por turno, ANTES de que le pase a un paciente: 0 ejecuciones afectadas).
La continuidad v2 manda al sub-WF de cambios TODO lo que pasa en medio de un cambio de turno. El sub-WF ejecuta bien una eleccion de
horario (reserva el nuevo + anula el viejo), pero no conversa: su parser de intencion clasifica una PREGUNTA como "consultar_info" y contesta
"Tu proximo turno es el viernes 16..." (medido con el modelo real, 5/5 muestras, en los dos turnos reales de abajo):
   T3 «En esta semana excepto el 8 de octubre que fecha tendra disponible por la tarde o por la mañana?»   (tras un bloque de horarios)
   T4 «Si»   (respondiendo a «¿Quiere que le busque las fechas mas proximas?», pregunta que hizo el agente de agenda)
Antes de hoy esos dos mensajes los respondia el agente de agenda (Sub-Agent Agendar), y bien.

ARREGLO. En un cambio de turno el sub-WF recibe SOLO lo que puede ejecutar:
   - una eleccion de horario tras un bloque                         → sub-WF (como hoy)
   - un "si" a un read-back de reemplazo / de cancelacion           → sub-WF (como hoy)
   - "otro dia / otro horario / mas temprano / la semana que viene" → sub-WF (como hoy: tiene la logica de franja y de siguiente lote)
   - una pregunta ABIERTA de disponibilidad («que fecha tiene...?», «hay lugar...?», «tendra disponible...?»)   → agente de agenda   ← NUEVO
   - un "si" pelado tras un bloque con varias opciones (no eligio ninguna)                                      → agente de agenda   ← NUEVO
   - cualquier respuesta a «¿Quiere que le busque...?» (la pregunta la hizo el agente de agenda)                → agente de agenda   ← NUEVO
El agente de agenda muestra los horarios (su prompt ya le prohibe prometer el cambio o armar read-backs de reemplazo); cuando la paciente
elige, la eleccion vuelve al sub-WF, que es el unico que reserva el nuevo y anula el viejo.
Nada cambia fuera de un cambio de turno (reserva nueva, confirmaciones, urgencias, pagos).

USO:  python scripts/apply_fix_ruteo_consultas_cambio.py            # simulacion: muestra el diff, no escribe nada
      python scripts/apply_fix_ruteo_consultas_cambio.py --apply    # backup PRE + PUT + verificacion + backup POST
Regla del proyecto: NUNCA --apply sin OK de Lucas.
Tests:  python tests/test_continuidad_flujo.py · python tests/test_politica_modo_humano.py · python tests/escenarios_turnos.py · python tests/test_flujo_dana_subwf.py
"""
import argparse, copy, difflib, json, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
WID = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}
MARCA = "RUTEO DE CONSULTAS EN UN CAMBIO (2026-10-05)"

R1_VIEJO = r"""    const RE_HORARIOS = /tenemos los proximos turnos disponibles|le sirve alguno|quiere que le busque|desea que (le )?busque|fechas mas proximas|le busco otra|otra fecha\?/;
"""
R1_NUEVO = r"""    const RE_BLOQUE = /tenemos los proximos turnos disponibles|le sirve alguno/;
    const RE_BUSQUEDA = /quiere que le busque|desea que (le )?busque|fechas mas proximas|le busco otra|otra fecha\?/;
"""

R2_VIEJO = "    let flujo = null, pideDatos = false, esElUltimo = false, vistos = 0;\n"
R2_NUEVO = "    let flujo = null, tipo = '', pideDatos = false, esElUltimo = false, vistos = 0;\n"

R3_VIEJO = r"""      if (RE_CAMBIO.test(ub)) { flujo = 'cancelar_o_reprogramar'; }
      else if (RE_RESERVA.test(ub)) { flujo = 'agendar_nuevo'; }
      else if (RE_DATOS.test(ub)) { pideDatos = true; flujo = hablaDeCambio ? 'cancelar_o_reprogramar' : 'agendar_nuevo'; }
      else if (RE_HORARIOS.test(ub)) { flujo = hablaDeCambio ? 'cancelar_o_reprogramar' : 'agendar_nuevo'; }
"""
R3_NUEVO = r"""      if (RE_CAMBIO.test(ub)) { flujo = 'cancelar_o_reprogramar'; tipo = 'cambio'; }
      else if (RE_RESERVA.test(ub)) { flujo = 'agendar_nuevo'; tipo = 'reserva'; }
      else if (RE_DATOS.test(ub)) { pideDatos = true; flujo = hablaDeCambio ? 'cancelar_o_reprogramar' : 'agendar_nuevo'; tipo = 'datos'; }
      else if (RE_BLOQUE.test(ub)) { flujo = hablaDeCambio ? 'cancelar_o_reprogramar' : 'agendar_nuevo'; tipo = 'bloque'; }
      else if (RE_BUSQUEDA.test(ub)) { flujo = hablaDeCambio ? 'cancelar_o_reprogramar' : 'agendar_nuevo'; tipo = 'busqueda'; }
"""

R4_VIEJO = r"""      if (afirma || eligeHorario || preguntaDisponibilidad || respondeDatos) {
        intent = flujo;
        continuidad = 'flujo_pendiente:' + flujo;
      }
"""
R4_NUEVO = r"""      if (afirma || eligeHorario || preguntaDisponibilidad || respondeDatos) {
        // === RUTEO DE CONSULTAS EN UN CAMBIO (2026-10-05) ===
        // El sub-WF de cambios EJECUTA (reserva el turno nuevo y anula el viejo) pero no conversa: su parser lee una pregunta como "consulta de info"
        // y contesta "Tu proximo turno es el..." (medido con el modelo real sobre la charla de la exec 294727 y 294731). En un cambio recibe SOLO lo
        // que puede ejecutar; una pregunta abierta de disponibilidad, un "si" pelado tras un bloque con varias opciones, o cualquier respuesta a
        // "¿quiere que le busque...?" (pregunta del agente de agenda) las atiende el agente de agenda, que muestra horarios. La eleccion vuelve al sub-WF.
        let destino = flujo;
        if (flujo === 'cancelar_o_reprogramar') {
          const preguntaAbierta = /disponib|que (fecha|dia|horario)s?\b|hay (lugar|turnos?)\b|tiene (algo|lugar|turnos?)\b|\btendra\b|\bhabra\b/.test(textoNorm);
          if (tipo === 'busqueda') destino = 'agendar_nuevo';
          else if (tipo === 'bloque' && (preguntaAbierta || afirma)) destino = 'agendar_nuevo';
          else if (tipo === 'cambio' && preguntaAbierta && !afirma) destino = 'agendar_nuevo';
        }
        intent = destino;
        continuidad = 'flujo_pendiente:' + flujo + (destino !== flujo ? ' (consulta: responde ' + destino + ')' : '');
      }
"""

CAMBIOS = [(R1_VIEJO, R1_NUEVO), (R2_VIEJO, R2_NUEVO), (R3_VIEJO, R3_NUEVO), (R4_VIEJO, R4_NUEVO)]


def transformar_parse(code):
    """Parse Intent con la continuidad v2 (apply_politica_modo_humano.py) → + ruteo de consultas en un cambio."""
    if MARCA in code:
        sys.exit("ABORTO: 'Parse Intent' ya tiene el ruteo de consultas en un cambio.")
    if "CONTINUIDAD DE FLUJO v2" not in code:
        sys.exit("ABORTO: 'Parse Intent' no tiene la continuidad v2 (aplicar antes scripts/apply_politica_modo_humano.py).")
    for viejo, nuevo in CAMBIOS:
        if code.count(viejo) != 1:
            sys.exit(f"ABORTO: en 'Parse Intent' la cadena a reemplazar aparece {code.count(viejo)} veces (esperaba 1). Otra sesion cambio el nodo.\n  cadena: {viejo[:90]!r}")
        code = code.replace(viejo, nuevo)
    return code


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
    nuevo = copy.deepcopy(wf)
    n_old = next(n for n in wf["nodes"] if n["name"] == "Parse Intent")
    n_new = next(n for n in nuevo["nodes"] if n["name"] == "Parse Intent")
    n_new["parameters"]["jsCode"] = transformar_parse(n_old["parameters"]["jsCode"])
    print(f"v6 active={wf.get('active')} nodos={len(wf['nodes'])} v={wf.get('versionId')[:8]}\n\n--- v6 · Parse Intent")
    for l in difflib.unified_diff(n_old["parameters"]["jsCode"].splitlines(), n_new["parameters"]["jsCode"].splitlines(), lineterm="", n=0):
        if not l.startswith(("---", "+++", "@@")):
            print("   ", l[:220])
    if not apply:
        print("\n[SIMULACION] No se aplico nada. Correr con --apply (con OK de Lucas).")
        return
    HIST.mkdir(parents=True, exist_ok=True)
    pre = HIST / f"{WID}_PRE_ruteo_consultas_cambio_{int(time.time())}.json"
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n  backup:", pre.name)
    if api(f"/workflows/{WID}").get("versionId") != wf.get("versionId"):
        sys.exit("ABORTO: el v6 cambio mientras preparaba el PUT.")
    body = {k: nuevo[k] for k in PUT_KEYS if k in nuevo}
    body["settings"] = {k: v for k, v in (nuevo.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{WID}", method="PUT", payload=body)
    post = api(f"/workflows/{WID}")
    (HIST / f"{WID}_POST_ruteo_consultas_cambio_{int(time.time())}.json").write_text(json.dumps(post, indent=2, ensure_ascii=False), encoding="utf-8")
    viejos = {n["name"]: n for n in wf["nodes"]}
    cambiados = sorted(n["name"] for n in post["nodes"] if viejos.get(n["name"]) != n)
    webhook = next((n for n in post["nodes"] if n.get("webhookId") == "evo-webhook-v2"), None)
    codigo_ok = next(n for n in post["nodes"] if n["name"] == "Parse Intent")["parameters"]["jsCode"] == n_new["parameters"]["jsCode"]
    print("  nodos que cambiaron:", cambiados, "| codigo vivo == codigo probado:", codigo_ok, "| activo:", post.get("active"),
          "| webhookId evo-webhook-v2:", bool(webhook), "| mismas conexiones:", wf["connections"] == post["connections"], "| nodos:", len(post["nodes"]))
    if cambiados != ["Parse Intent"] or not codigo_ok or not post.get("active") or not webhook or wf["connections"] != post["connections"] or len(wf["nodes"]) != len(post["nodes"]):
        sys.exit("ATENCION: la verificacion no dio lo esperado. Restaurar con: python scripts/restaurar_workflow.py workflows/history/" + pre.name + " --apply")
    print("Aplicado.")


if __name__ == "__main__":
    main()
