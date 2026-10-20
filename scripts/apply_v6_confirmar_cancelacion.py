# -*- coding: utf-8 -*-
"""
apply_v6_confirmar_cancelacion.py — 2026-10-15 · el v6 (sub-workflow "Sub-WF - CancelarReprogramar", 5cAWJxiWJ50hxEq3) deja de cancelar
turnos sin preguntar.

POR QUÉ: el 14/10 una paciente escribió "Ya aboné la consulta… pero tuve que cancelar el turno" (hablaba de uno ANTERIOR) y el v6 anuló en
el acto su turno vigente del 16/10 (ejecución 314672). Regla de Lucas (15/10): toda acción que cambia la agenda se confirma antes con el
paciente. El v7 ya lo hace; el v6 sigue atendiendo hasta que el v7 pase a todos.

QUÉ CAMBIA (2 nodos Code, nada más):
  1) "Step 0b: Detect Multi-Turn State": el estado 'esperando_confirmacion_cancelacion' se reconoce también con "Le confirmo… cancel…"
     (antes solo "te confirmo… cancelar", que ningún texto del bot usaba).
  2) "Step 5: Decidir Accion Ejecutable", rama `intent.accion === 'cancelar'`: si el último mensaje del bot NO es la pregunta de
     confirmación de ESE turno (misma fecha y hora), no cancela: responde "Le confirmo: ¿desea cancelar su turno del … a las …? Si es así,
     respóndame «sí» y lo cancelo." Recién con esa pregunta a la vista y el parser diciendo "cancelar" (p. ej. "sí") se anula.
     Si el turno que entiende ahora es otro (otra fecha/hora), vuelve a preguntar por ese: nunca anula algo que no se preguntó.

USO:  python scripts/apply_v6_confirmar_cancelacion.py            # simula: GET + parche en memoria + pruebas del JS + diff
      python scripts/apply_v6_confirmar_cancelacion.py --apply    # backup PRE, PUT, GET, backup POST, verificación
      python scripts/apply_v6_confirmar_cancelacion.py --revertir # PUT del último backup PRE (solo si el vivo es el POST de este script)
"""
import argparse, json, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from flag_v7 import api   # GET/PUT a la API de n8n con la clave del .env (muestra el cuerpo de los errores)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
WID = "5cAWJxiWJ50hxEq3"
HIST = ROOT / "workflows" / "history"
N0B, N5 = "Step 0b: Detect Multi-Turn State", "Step 5: Decidir Accion Ejecutable"
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution", "executionTimeout",
               "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}

R0B_VIEJO = "} else if (/te confirmo.*cancelar/i.test(lower)) {"
R0B_NUEVO = "} else if (/(te|le) confirmo.*cancel/i.test(lower)) {   // (15/10) la pregunta de confirmación del Step 5 dice \"Le confirmo: ¿quiere cancelar…\""

R5_VIEJO = """if (intent.accion === 'cancelar') {
  return [{ json: {
    ...prev,
    action_to_execute: 'cancelar_turno',"""
R5_NUEVO = """if (intent.accion === 'cancelar') {
  // (15/10, regla de Lucas) Nunca cancelar sin preguntar: incidente del 14/10 ("tuve que cancelar el turno" hablaba de uno anterior y se
  // anuló el vigente). Se anula SOLO si el último mensaje del bot es la pregunta de confirmación de ESTE turno (misma fecha y hora).
  let trgC = prev.trigger;
  if (typeof trgC === 'string') { try { trgC = JSON.parse(trgC); } catch (e) { trgC = {}; } }
  trgC = trgC || {};
  const queTurno = fechaNatural(turno.fecha) + ' a las ' + horaNatural(turno.hora_inicio);
  const ultimoBot = String(trgC.last_bot_msg || '').toLowerCase();
  const preguntado = trgC.multi_turn_state === 'esperando_confirmacion_cancelacion' && ultimoBot.includes(queTurno.toLowerCase());
  if (!preguntado) {
    return [{ json: { ...prev, action_to_execute: 'ninguna',
      mensaje_final: 'Le confirmo: ¿desea cancelar su turno del ' + queTurno + '? Si es así, respóndame «sí» y lo cancelo.' } }];
  }
  return [{ json: {
    ...prev,
    action_to_execute: 'cancelar_turno',"""

PRUEBAS_JS = r"""
const fs = require('fs');
const code = fs.readFileSync(process.argv[2], 'utf8');
const T = { id: 9201, fecha: '2026-10-16', hora_inicio: '09:10:00' };
const correr = (prev) => new Function('$input', '$', code)({ first: () => ({ json: prev }) }, () => ({ first: () => ({ json: {} }), all: () => [] }))[0].json;
const base = (trigger, intent) => ({ intent: { accion: 'cancelar', ...intent }, turno_objetivo: T, turnos_proximos: [T], decision: {}, acceptance_intent: { accepts: null }, trigger });
let fallas = 0; const t = (n, ok, x) => { console.log((ok ? '  ok    ' : '  FALLA ') + n + (ok ? '' : ' → ' + JSON.stringify(x).slice(0, 300))); if (!ok) fallas++; };
const PREG = 'Le confirmo: ¿desea cancelar su turno del viernes 16 de octubre a las 9:10 de la mañana? Si es así, respóndame «sí» y lo cancelo.';
let r = correr(base({ multi_turn_state: 'conversacion_nueva', last_bot_msg: '' }));
t('C1 primer "quiero cancelar": NO cancela, pregunta con fecha y hora', r.action_to_execute === 'ninguna' && r.mensaje_final === PREG, r);
r = correr(base({ multi_turn_state: 'esperando_confirmacion_cancelacion', last_bot_msg: PREG }));
t('C2 "sí" con la pregunta de ESE turno a la vista: cancela ese turno', r.action_to_execute === 'cancelar_turno' && r.cita_a_cancelar === 9201, r);
r = correr(base({ multi_turn_state: 'esperando_confirmacion_cancelacion', last_bot_msg: PREG.replace('16 de octubre', '23 de octubre') }));
t('C3 la pregunta era de OTRO turno: no cancela, pregunta por este', r.action_to_execute === 'ninguna' && r.mensaje_final === PREG, r);
r = correr(base({ multi_turn_state: 'oferta_horarios', last_bot_msg: PREG }));
t('C4 estado distinto (no esperando confirmación): no cancela', r.action_to_execute === 'ninguna', r);
r = correr(base(JSON.stringify({ multi_turn_state: 'esperando_confirmacion_cancelacion', last_bot_msg: PREG })));
t('C5 trigger serializado (string): igual cancela con la pregunta a la vista', r.action_to_execute === 'cancelar_turno', r);
r = correr(base({ multi_turn_state: 'esperando_confirmacion_cancelacion', last_bot_msg: PREG }, { accion: 'reprogramar' }));
t('C6 después de la pregunta pide reprogramar: no entra a cancelar', r.action_to_execute !== 'cancelar_turno', r);
process.exit(fallas ? 1 : 0);
"""
PRUEBA_0B = r"""
const lower = process.argv[2].toLowerCase();
const re = /(te|le) confirmo.*cancel/i;
process.exit(re.test(lower) && re.test('te confirmo que vas a cancelar') && !re.test('listo, su turno queda cancelado') ? 0 : 1);
"""


def parchar(w):
    nodos = {n["name"]: n for n in w["nodes"]}
    for nombre in (N0B, N5):
        if nombre not in nodos:
            raise SystemExit(f"No encontré el nodo «{nombre}» en el vivo: no toco nada.")
    c0, c5 = nodos[N0B]["parameters"]["jsCode"], nodos[N5]["parameters"]["jsCode"]
    if R5_NUEVO.split("\n")[1] in c5:
        raise SystemExit("El vivo ya tiene este parche.")
    for viejo, codigo, nombre in ((R0B_VIEJO, c0, N0B), (R5_VIEJO, c5, N5)):
        if codigo.count(viejo) != 1:
            raise SystemExit(f"El texto a reemplazar en «{nombre}» aparece {codigo.count(viejo)} veces (esperaba 1): el vivo cambió, no toco nada.")
    nodos[N0B]["parameters"]["jsCode"] = c0.replace(R0B_VIEJO, R0B_NUEVO)
    nodos[N5]["parameters"]["jsCode"] = c5.replace(R5_VIEJO, R5_NUEVO)
    return w, nodos[N5]["parameters"]["jsCode"]


def probar(codigo5):
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "step5.js"; f.write_text(codigo5, encoding="utf-8")
        p = Path(d) / "pruebas.js"; p.write_text(PRUEBAS_JS, encoding="utf-8")
        r = subprocess.run(["node", str(p), str(f)], capture_output=True, text=True, encoding="utf-8")
        print(r.stdout.rstrip() or r.stderr[-800:])
        q = Path(d) / "p0b.js"; q.write_text(PRUEBA_0B, encoding="utf-8")
        r0 = subprocess.run(["node", str(q), "Le confirmo: ¿desea cancelar su turno del viernes 16 de octubre a las 9:10 de la mañana?"], capture_output=True)
        print(("  ok    " if r0.returncode == 0 else "  FALLA ") + "B1 Step 0b reconoce la pregunta nueva como 'esperando_confirmacion_cancelacion'")
        return r.returncode == 0 and r0.returncode == 0


def cuerpo(w):
    return {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
            "settings": {k: v for k, v in (w.get("settings") or {}).items() if k in SETTINGS_OK}, "staticData": w.get("staticData")}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revertir", action="store_true")
    a = ap.parse_args()
    vivo = api(f"/workflows/{WID}")
    if a.revertir:
        pres = sorted(HIST.glob(f"{WID}_PRE_confirmar_cancelacion_*.json"))
        if not pres: raise SystemExit("No hay backup PRE de este script.")
        if R5_NUEVO.split("\n")[1] not in json.dumps(vivo, ensure_ascii=False):
            raise SystemExit("El vivo no tiene este parche: no revierto nada.")
        api(f"/workflows/{WID}", "PUT", cuerpo(json.loads(pres[-1].read_text(encoding="utf-8"))))
        print("Revertido al backup", pres[-1].name); return
    version = vivo.get("versionId")
    nuevo, codigo5 = parchar(json.loads(json.dumps(vivo)))
    print(f"Vivo: {vivo['name']} · {len(vivo['nodes'])} nodos · versionId {version} · activo {vivo.get('active')}")
    print("Cambios: 2 nodos Code («%s», «%s»); conexiones y demás nodos sin tocar." % (N0B, N5))
    if not probar(codigo5):
        raise SystemExit("Las pruebas del JS fallaron: no se aplica nada.")
    if not a.apply:
        print("\n[SIMULACIÓN] No se cambió nada. Para aplicar: --apply"); return
    ts = int(time.time())
    HIST.mkdir(parents=True, exist_ok=True)
    (HIST / f"{WID}_PRE_confirmar_cancelacion_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
    otra = api(f"/workflows/{WID}")
    if otra.get("versionId") != version: raise SystemExit("El vivo cambió mientras tanto: no aplico.")
    api(f"/workflows/{WID}", "PUT", cuerpo(nuevo))
    post = api(f"/workflows/{WID}")
    (HIST / f"{WID}_POST_confirmar_cancelacion_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
    n5 = next(n for n in post["nodes"] if n["name"] == N5)["parameters"]["jsCode"]
    ok = R5_NUEVO.split("\n")[1] in n5 and len(post["nodes"]) == len(vivo["nodes"]) and post.get("active") == vivo.get("active")
    print(("OK" if ok else "ATENCIÓN") + f": aplicado. versionId {post.get('versionId')} · nodos {len(post['nodes'])} · activo {post.get('active')} · backups _{ts}")
    if not ok: raise SystemExit("La verificación posterior falló: revisar y, si hace falta, --revertir.")


if __name__ == "__main__":
    main()
