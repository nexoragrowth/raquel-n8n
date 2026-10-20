# -*- coding: utf-8 -*-
"""
apply_v6_confirmar_reprogramacion.py — 2026-10-19 · el v6 (sub-workflow "Sub-WF - CancelarReprogramar", 5cAWJxiWJ50hxEq3) deja de
reprogramar en el acto cuando el paciente elige un horario del bloque: primero le confirma y espera el "sí" (backlog BOT-02).

POR QUÉ: regla de Lucas (15/10, no revisable): "ante cualquier acción destructiva consulta" (agendar, cancelar, reprogramar). Cancelar ya
confirma (apply_v6_confirmar_cancelacion.py). Reprogramar ejecutaba "reservar_y_cancelar" apenas el parser de aceptación reconocía un
horario del bloque. El v7 ya confirma siempre; el v6 atiende hasta el pase del v7 (16/11).

QUÉ CAMBIA (3 nodos Code, nada más):
  1) "Step 0b": nuevo estado 'esperando_confirmacion_reprogramacion' cuando el último mensaje del bot es "Le confirmo: … reemplazando el
     turno del …" (se chequea ANTES que la oferta de horarios).
  2) "Step 3.5a": el parser de aceptación también corre en ese estado (el read-back trae UN horario: un "sí" lo acepta).
  3) "Step 5": al elegir un horario, si el último mensaje NO es la confirmación de ESE horario reemplazando ESE turno, responde
     "Le confirmo: <nuevo>, reemplazando el turno del <viejo>. ¿Procedo con el cambio? Si es así, respóndame «sí»." y no toca la agenda.
     Recién con esa pregunta a la vista y el "sí" ejecuta reservar_y_cancelar. "reemplazando el turno" hace que la continuidad del Parse
     Intent del v6 mande el "sí" de vuelta a este sub-workflow.

USO:  python scripts/apply_v6_confirmar_reprogramacion.py            # simula: GET + parche en memoria + pruebas del JS
      python scripts/apply_v6_confirmar_reprogramacion.py --apply    # backup PRE, PUT, GET, backup POST, verificación
      python scripts/apply_v6_confirmar_reprogramacion.py --revertir # vuelve al último backup PRE de este script
"""
import argparse, json, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from flag_v7 import api

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
WID = "5cAWJxiWJ50hxEq3"
HIST = ROOT / "workflows" / "history"
N0B, N35, N5 = "Step 0b: Detect Multi-Turn State", "Step 3.5a: Prep Acceptance LLM", "Step 5: Decidir Accion Ejecutable"
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution", "executionTimeout",
               "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}
MARCA = "(19/10, BOT-02)"

C0_VIEJO = "if (/turnos disponibles:|te ofrezco|te puedo ofrecer|tengo disponible|cual confirma|cual prefiere/i.test(lower)) {\n  multi_turn_state = 'oferta_horarios';"
C0_NUEVO = ("if (/(te|le) confirmo.*reemplazando el turno/i.test(lower)) {   // " + MARCA + " read-back de reprogramación del Step 5\n"
            "  multi_turn_state = 'esperando_confirmacion_reprogramacion';\n} else " + C0_VIEJO)

C35_VIEJO = "if (state !== 'oferta_horarios') {"
C35_NUEVO = "if (state !== 'oferta_horarios' && state !== 'esperando_confirmacion_reprogramacion') {   // " + MARCA

C5_VIEJO = """  return [{ json: {
    ...prev,
    action_to_execute: 'reservar_y_cancelar',"""
C5_NUEVO = """  // """ + MARCA + """ Regla de Lucas: confirmar ANTES de tocar la agenda. Se ejecuta solo si el último mensaje del bot es la confirmación de
  // ESTE horario reemplazando ESTE turno; si no, se le pregunta y no se toca nada.
  let trgR = prev.trigger;
  if (typeof trgR === 'string') { try { trgR = JSON.parse(trgR); } catch (e) { trgR = {}; } }
  trgR = trgR || {};
  const nuevoTxt = fechaNatural(accept.slot_chosen.fecha) + ' a las ' + horaNatural(accept.slot_chosen.hora_inicio);
  const viejoTxt = fechaNatural(tCancelar.fecha) + ' a las ' + horaNatural(tCancelar.hora_inicio);
  const ubR = String(trgR.last_bot_msg || '').toLowerCase();
  const confirmadoR = trgR.multi_turn_state === 'esperando_confirmacion_reprogramacion' && ubR.includes(nuevoTxt.toLowerCase()) && ubR.includes(viejoTxt.toLowerCase());
  if (!confirmadoR) {
    return [{ json: { ...prev, action_to_execute: 'ninguna',
      mensaje_final: 'Le confirmo: ' + nuevoTxt.charAt(0).toUpperCase() + nuevoTxt.slice(1) + ', reemplazando el turno del ' + viejoTxt + '. ¿Procedo con el cambio? Si es así, respóndame «sí».' } }];
  }
""" + C5_VIEJO

PRUEBAS_JS = r"""
const fs = require('fs');
const code = fs.readFileSync(process.argv[2], 'utf8');
const VIEJO = { id: 9201, fecha: '2026-10-16', hora_inicio: '09:10:00' };
const SLOT = { fecha: '2026-10-22', hora_inicio: '09:20' };
const correr = (prev) => new Function('$input', '$', code)({ first: () => ({ json: prev }) }, () => ({ first: () => ({ json: {} }), all: () => [] }))[0].json;
const base = (trigger, accept) => ({ intent: { accion: 'reprogramar' }, turno_objetivo: VIEJO, turnos_proximos: [VIEJO], decision: {}, acceptance_intent: accept, trigger });
let fallas = 0; const t = (n, ok, x) => { console.log((ok ? '  ok    ' : '  FALLA ') + n + (ok ? '' : ' → ' + JSON.stringify(x).slice(0, 300))); if (!ok) fallas++; };
const PREG = 'Le confirmo: Jueves 22 de octubre a las 9:20 de la mañana, reemplazando el turno del viernes 16 de octubre a las 9:10 de la mañana. ¿Procedo con el cambio? Si es así, respóndame «sí».';
let r = correr(base({ multi_turn_state: 'oferta_horarios', last_bot_msg: 'Tenemos los próximos turnos disponibles: …' }, { accepts: true, slot_chosen: SLOT }));
t('R1 elige un horario del bloque: NO reprograma, pregunta con el nuevo y el viejo', r.action_to_execute === 'ninguna' && r.mensaje_final === PREG, r);
r = correr(base({ multi_turn_state: 'esperando_confirmacion_reprogramacion', last_bot_msg: PREG }, { accepts: true, slot_chosen: SLOT }));
t('R2 "sí" con la confirmación de ESE horario y ESE turno a la vista: reprograma', r.action_to_execute === 'reservar_y_cancelar' && r.cita_a_cancelar === 9201 && r.slot_a_reservar.hora_inicio === '09:20', r);
r = correr(base({ multi_turn_state: 'esperando_confirmacion_reprogramacion', last_bot_msg: PREG.replace('22 de octubre', '23 de octubre') }, { accepts: true, slot_chosen: SLOT }));
t('R3 la confirmación era de OTRO horario: no reprograma, pregunta por este', r.action_to_execute === 'ninguna' && r.mensaje_final === PREG, r);
r = correr(base({ multi_turn_state: 'esperando_confirmacion_reprogramacion', last_bot_msg: PREG.replace('viernes 16 de octubre', 'lunes 19 de octubre') }, { accepts: true, slot_chosen: SLOT }));
t('R4 la confirmación reemplazaba OTRO turno: no reprograma', r.action_to_execute === 'ninguna', r);
r = correr(base(JSON.stringify({ multi_turn_state: 'esperando_confirmacion_reprogramacion', last_bot_msg: PREG }), { accepts: true, slot_chosen: SLOT }));
t('R5 trigger serializado (string): igual reprograma con la confirmación a la vista', r.action_to_execute === 'reservar_y_cancelar', r);
r = correr(base({ multi_turn_state: 'esperando_confirmacion_reprogramacion', last_bot_msg: PREG }, { accepts: false, slot_chosen: null }));
t('R6 después de la confirmación dice que no: no reprograma', r.action_to_execute !== 'reservar_y_cancelar', r);
process.exit(fallas ? 1 : 0);
"""
PRUEBA_0B = r"""
const re1 = /(te|le) confirmo.*reemplazando el turno/i, reC = /(te|le) confirmo.*cancel/i;
const preg = 'le confirmo: jueves 22 de octubre a las 9:20 de la mañana, reemplazando el turno del viernes 16 de octubre a las 9:10 de la mañana. ¿procedo con el cambio?';
const RE_CAMBIO = /reemplazando el turno|desea cambiar ese|cambiar ese por|desea cancelar|que desea cancelar|cancelar (el|ese) turno\?/;
process.exit(re1.test(preg) && !reC.test(preg) && RE_CAMBIO.test(preg) && !re1.test('tenemos los próximos turnos disponibles:') ? 0 : 1);
"""


def parchar(w):
    nodos = {n["name"]: n for n in w["nodes"]}
    for nombre in (N0B, N35, N5):
        if nombre not in nodos: raise SystemExit(f"No encontré «{nombre}»: no toco nada.")
    pares = ((N0B, C0_VIEJO, C0_NUEVO), (N35, C35_VIEJO, C35_NUEVO), (N5, C5_VIEJO, C5_NUEVO))
    if MARCA in nodos[N5]["parameters"]["jsCode"]: raise SystemExit("El vivo ya tiene este parche.")
    for nombre, viejo, _ in pares:
        n = nodos[nombre]["parameters"]["jsCode"].count(viejo)
        if n != 1: raise SystemExit(f"El texto a reemplazar en «{nombre}» aparece {n} veces (esperaba 1): el vivo cambió, no toco nada.")
    for nombre, viejo, nuevo in pares:
        nodos[nombre]["parameters"]["jsCode"] = nodos[nombre]["parameters"]["jsCode"].replace(viejo, nuevo)
    return w, nodos[N5]["parameters"]["jsCode"]


def probar(codigo5):
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "step5.js"; f.write_text(codigo5, encoding="utf-8")
        p = Path(d) / "pruebas.js"; p.write_text(PRUEBAS_JS, encoding="utf-8")
        r = subprocess.run(["node", str(p), str(f)], capture_output=True, text=True, encoding="utf-8")
        print(r.stdout.rstrip() or r.stderr[-800:])
        q = Path(d) / "p0b.js"; q.write_text(PRUEBA_0B, encoding="utf-8")
        r0 = subprocess.run(["node", str(q)], capture_output=True)
        print(("  ok    " if r0.returncode == 0 else "  FALLA ") + "B1 Step 0b reconoce la confirmación nueva (y no la confunde con cancelar); la continuidad del Parse Intent la manda acá")
        return r.returncode == 0 and r0.returncode == 0


def cuerpo(w):
    return {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
            "settings": {k: v for k, v in (w.get("settings") or {}).items() if k in SETTINGS_OK}, "staticData": w.get("staticData")}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revertir", action="store_true")
    a = ap.parse_args()
    vivo = api(f"/workflows/{WID}")
    if a.revertir:
        pres = sorted(HIST.glob(f"{WID}_PRE_confirmar_reprogramacion_*.json"))
        if not pres: raise SystemExit("No hay backup PRE de este script.")
        if MARCA not in json.dumps(vivo, ensure_ascii=False): raise SystemExit("El vivo no tiene este parche: no revierto nada.")
        api(f"/workflows/{WID}", "PUT", cuerpo(json.loads(pres[-1].read_text(encoding="utf-8")))); print("Revertido a", pres[-1].name); return
    version = vivo.get("versionId")
    nuevo, codigo5 = parchar(json.loads(json.dumps(vivo)))
    print(f"Vivo: {vivo['name']} · {len(vivo['nodes'])} nodos · versionId {version} · activo {vivo.get('active')}")
    print(f"Cambios: 3 nodos Code («{N0B}», «{N35}», «{N5}»); conexiones y demás nodos sin tocar.")
    if not probar(codigo5): raise SystemExit("Las pruebas del JS fallaron: no se aplica nada.")
    if not a.apply: print("\n[SIMULACIÓN] No se cambió nada. Para aplicar: --apply"); return
    ts = int(time.time()); HIST.mkdir(parents=True, exist_ok=True)
    (HIST / f"{WID}_PRE_confirmar_reprogramacion_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
    if api(f"/workflows/{WID}").get("versionId") != version: raise SystemExit("El vivo cambió mientras tanto: no aplico.")
    api(f"/workflows/{WID}", "PUT", cuerpo(nuevo))
    post = api(f"/workflows/{WID}")
    (HIST / f"{WID}_POST_confirmar_reprogramacion_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
    n5 = next(n for n in post["nodes"] if n["name"] == N5)["parameters"]["jsCode"]
    ok = MARCA in n5 and len(post["nodes"]) == len(vivo["nodes"]) and post.get("active") == vivo.get("active")
    print(("OK" if ok else "ATENCIÓN") + f": aplicado. versionId {post.get('versionId')} · nodos {len(post['nodes'])} · activo {post.get('active')} · backups _{ts}")
    if not ok: raise SystemExit("La verificación posterior falló: revisar y, si hace falta, --revertir.")


if __name__ == "__main__":
    main()
