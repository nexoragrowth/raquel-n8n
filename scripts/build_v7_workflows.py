# -*- coding: utf-8 -*-
"""
build_v7_workflows.py — genera los workflows del v7 como JSON de n8n en v7/workflows/*.json (SIN red, SIN tocar n8n).
El codigo de los nodos Code sale de v7/*.js (probado offline). Para crear/actualizar en n8n (inactivos): scripts/crear_v7_en_n8n.py (aparte, con OK).

USO:  python scripts/build_v7_workflows.py            # escribe v7/workflows/*.json
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v7_lib import DENTALINK, Grafo, V7
from v7_workflow_cerebro import wf_cerebro
from v7_workflow_cerebro_agente import wf_cerebro_agente
from v7_workflow_clinica import wf_clinica
from v7_workflows_confirmar_clinica import wf_confirmar_turno, wf_confirmar_una
from v7_workflows_herramientas import wf_buscar_horarios, wf_elegir_ficha, wf_gestionar_turno, wf_proponer, wf_ver_turnos
from v7_workflows_ma import wf_agente_informacion, wf_agente_pagos, wf_agente_turnos, wf_agente_urgencias

sys.stdout.reconfigure(encoding="utf-8")
SALIDA = V7 / "workflows"
GRUPO = "https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo"

# El libro de escrituras es una LISTA por ejecución (puede haber más de una escritura en la misma respuesta): se lee, se suma la nueva y se guarda.
SUMAR_AL_LIBRO = """const f = $('Final').first().json;
let arr = []; try { arr = JSON.parse($input.first().json.libro_raw || '[]'); } catch (e) { arr = []; }
if (!Array.isArray(arr)) arr = [arr];
arr.push(f.libro_entry);
return [{ json: { libro_key: f.libro_key, libro_json: JSON.stringify(arr) } }];"""

JS_FIN_O_SIGUE ="r.fin ? { terminado: true, resultado: r.fin } : { terminado: false, estado: { propuesta: r.propuesta, ledger: r.ledger } }"


def wf_ejecutar():
    """v7 Tool - ejecutar_propuesta: consume la propuesta una sola vez, verifica la cita vieja, reserva, anula y deja el libro de escrituras."""
    g = Grafo("v7 Tool - ejecutar_propuesta")
    g.trigger({"tel": "5490000000651", "exec_id_actual": "1234", "modo": "vivo"}, 0, 300)
    g.redis_get("Redis GET propuesta", "'propuesta:' + $json.tel", "propuesta_raw", 220, 300)
    g.code("Paso inicial", f"""const e = $('Entrada').first().json;
let p = null; try {{ p = JSON.parse($input.first().json.propuesta_raw || 'null'); }} catch (x) {{ p = null; }}
const r = AgendaCore.pasoInicial({{ propuesta: p, exec_id_actual: String(e.exec_id_actual), enviada: !!(p && p.enviada === true), modo: e.modo }}, new Date().toISOString());
return [{{ json: {JS_FIN_O_SIGUE} }}];""", 440, 300, usar=("agenda_core",))
    g.si("¿Termina? (inicial)", "$json.terminado === true", 660, 300)
    g.redis_incr("Redis INCR ejecutando", "'ejecutando:' + $json.estado.propuesta.id", 1800, 880, 360)
    g.code("Paso consumo", f"""const estado = $('Paso inicial').first().json.estado;
const v = Object.values($input.first().json || {{}})[0];
const consumida = (v === undefined || v === null || v === '') ? undefined : (parseInt(v) === 1);
const r = AgendaCore.pasoConsumo(estado, consumida);
return [{{ json: {JS_FIN_O_SIGUE} }}];""", 1100, 360, usar=("agenda_core",))
    g.si("¿Termina? (consumo)", "$json.terminado === true", 1320, 360)
    # La propuesta queda CONSUMIDA apenas se toma el candado (haya salido bien o mal después): un segundo "sí" minutos más tarde ya no puede
    # volver a escribir (antes el candado INCR vencía a los 5 min y la propuesta seguía 'pendiente' 30 min → doble reserva posible).
    g.redis_set("Redis SET propuesta consumida", "'propuesta:' + $('Entrada').first().json.tel", "JSON.stringify({ ...$('Paso consumo').first().json.estado.propuesta, estado: 'ejecutada', consumida_exec: String($execution.id) })", 1800, 1430, 480)
    g.code("Reemitir estado", "return [{ json: $('Paso consumo').first().json }];", 1485, 480)
    g.si("¿Hay cita vieja?", "!!$json.estado.propuesta.cita_vieja", 1540, 420)
    g.dentalink("GET cita vieja", "GET", f"'{DENTALINK}/citas/' + $json.estado.propuesta.cita_vieja.id", None, 1760, 360)
    g.code("Paso cita", f"""const estado = $('Paso consumo').first().json.estado;
const r = AgendaCore.pasoCita(estado, $input.first().json);
return [{{ json: {JS_FIN_O_SIGUE} }}];""", 1980, 360, usar=("agenda_core",))
    g.code("Paso cita (sin cita)", f"""const estado = $('Paso consumo').first().json.estado;
const r = AgendaCore.pasoCita(estado, null);
return [{{ json: {JS_FIN_O_SIGUE} }}];""", 1760, 520, usar=("agenda_core",))
    g.si("¿Termina? (cita)", "$json.terminado === true", 2200, 440)
    g.si("¿Es cancelación?", "$json.estado.propuesta.tipo === 'cancelacion'", 2420, 480)
    # (06/10) Paciente nuevo: antes de reservar, buscar el DNI en la agenda (anti-duplicado) y dar el alta; si la agenda rechaza el DNI, un reintento sin DNI.
    g.si("¿Paciente nuevo?", "!!($json.estado.propuesta.paciente_nuevo && !$json.estado.propuesta.paciente_id)", 2420, 760)
    g.dentalink("GET paciente por DNI", "GET", f"'{DENTALINK}/pacientes'", None, 2640, 860, query_expr="JSON.stringify({ rut: { eq: $json.estado.propuesta.paciente_nuevo.dni } })")
    g.code("Paso DNI", """const estado = $('¿Paciente nuevo?').first().json.estado;
const r = AgendaCore.pasoBuscarDni(estado, $input.first().json);
if (r.fin) return [{ json: { terminado: true, resultado: r.fin } }];
return [{ json: { terminado: false, crear: r.crear === true, body_paciente: r.crear ? AgendaCore.armarPaciente(r.propuesta, true) : null, estado: { propuesta: r.propuesta, ledger: r.ledger } } }];""", 2860, 860, usar=("agenda_core",))
    g.si("¿Termina? (DNI)", "$json.terminado === true", 3080, 860)
    g.si("¿Crear paciente?", "$json.crear === true", 3300, 920)
    g.dentalink("POST paciente", "POST", f"'{DENTALINK}/pacientes/'", "JSON.stringify($json.body_paciente)", 3520, 980)
    g.code("Paso alta", """const estado = $('Paso DNI').first().json.estado;
const r = AgendaCore.pasoAlta(estado, $input.first().json, true);
if (r.fin) return [{ json: { terminado: true, resultado: r.fin } }];
return [{ json: { terminado: false, reintentar: r.reintentar === true, body_paciente: r.reintentar ? AgendaCore.armarPaciente(r.propuesta, false) : null, estado: { propuesta: r.propuesta, ledger: r.ledger } } }];""", 3740, 980, usar=("agenda_core",))
    g.si("¿Termina? (alta)", "$json.terminado === true", 3960, 980)
    g.si("¿Reintentar sin DNI?", "$json.reintentar === true", 4180, 1040)
    g.dentalink("POST paciente (sin DNI)", "POST", f"'{DENTALINK}/pacientes/'", "JSON.stringify($json.body_paciente)", 4400, 1120)
    g.code("Paso alta (sin DNI)", """const estado = $('Paso alta').first().json.estado;
const r = AgendaCore.pasoAlta(estado, $input.first().json, false);
return [{ json: r.fin ? { terminado: true, resultado: r.fin } : { terminado: false, estado: { propuesta: r.propuesta, ledger: r.ledger } } }];""", 4620, 1120, usar=("agenda_core",))
    g.si("¿Termina? (alta sin DNI)", "$json.terminado === true", 4840, 1120)
    g.code("Alta lista", "return [{ json: $input.first().json }];", 5060, 1000)
    # La ficha nueva tiene que aparecer en el próximo ver_turnos (el cache del celular no la tiene).
    g.redis_del("Redis DEL ficha", "'ficha:' + $('Entrada').first().json.tel", 5280, 1000)
    g.redis_del("Redis DEL turnos_vistos", "'turnos_vistos:' + $('Entrada').first().json.tel", 5500, 1000)
    g.code("Reemitir alta", "return [{ json: $('Alta lista').first().json }];", 5720, 1000)
    g.code("Armar reserva", """const estado = $input.first().json.estado;
return [{ json: { estado, body: AgendaCore.armarReserva(estado.propuesta) } }];""", 2640, 560, usar=("agenda_core",))
    g.dentalink("POST reserva", "POST", f"'{DENTALINK}/citas/'", "JSON.stringify($json.body)", 2860, 560)
    g.code("Paso reserva", f"""const estado = $('Armar reserva').first().json.estado;
const r = AgendaCore.pasoReserva(estado, $input.first().json);
return [{{ json: r.fin ? {{ terminado: true, resultado: r.fin }} : {{ terminado: false, estado: {{ propuesta: r.propuesta, ledger: r.ledger, nueva_cita: r.nueva_cita }} }} }}];""", 3080, 560, usar=("agenda_core",))
    g.si("¿Termina? (reserva)", "$json.terminado === true", 3300, 560)
    g.code("Armar anulación", "return [{ json: { estado: $input.first().json.estado } }];", 3520, 420)
    g.dentalink("PUT anular", "PUT", f"'{DENTALINK}/citas/' + $json.estado.propuesta.cita_vieja.id", "JSON.stringify({ id_estado: 1 })", 3740, 420)
    g.code("Paso anulación", """const estado = $('Armar anulación').first().json.estado;
const r = AgendaCore.pasoAnulacion(estado, $input.first().json);
return [{ json: { terminado: true, resultado: r.fin } }];""", 3960, 420, usar=("agenda_core",))
    g.code("Final", f"""const e = $('Entrada').first().json;
const r = $input.first().json.resultado || {{}};
const led = r.ledger || {{ escrituras: [] }};
const simulado = r.simulado === true;
const escribio = (led.escrituras || []).length > 0 || simulado;   // en sombra queda igual el libro (marcado simulado) para que el chequeo de salida se pruebe completo; sin avisos
const libro = {{ ok: r.ok === true, simulado, parcial: r.parcial === true, tipo: led.tipo || null, readback_text: r.readback_text || null, nueva_cita: r.nueva_cita || null, vieja_anulada: r.vieja_anulada || null, primera_consulta: r.primera_consulta === true }};
let aviso = null;
if (r.aviso_clinica && !simulado) aviso = {{ nivel: 'ACCION', texto: r.aviso_clinica }};   // paciente nuevo que no se pudo dar de alta (o DNI de otra ficha): no se reservó nada
else if (escribio && !simulado) {{
  // (20/10) "solo" se leía como "sin confirmar": siempre se ejecuta recién después del "sí" del paciente al read-back (AgendaCore.decidir).
  if (r.ok === true) aviso = {{ nivel: 'FYI', texto: '[FYI] Asiri hizo un cambio en la agenda (el paciente lo confirmó con «sí»): ' + (r.readback_text || '') + (r.nota_alta ? ' ' + r.nota_alta : '') }};
  else if (r.parcial === true) aviso = {{ nivel: 'ACCION', texto: '[ACCIÓN] Escritura a medias, revisar la agenda: ' + (r.readback_text || '') }};
  else if (r.motivo === 'no_pude_cancelar') aviso = {{ nivel: 'ACCION', texto: '[ACCIÓN] No se pudo cancelar un turno que la paciente pidió cancelar. Revisar.' }};
}}
const salida = {{ ok: r.ok === true, motivo: r.motivo || null, parcial: r.parcial === true, simulado: r.simulado === true, nueva_cita: r.nueva_cita || null, vieja_anulada: r.vieja_anulada || null, readback_text: r.readback_text || null, para_asiri: r.para_asiri || null, habria_hecho: r.habria_hecho || null }};
return [{{ json: {{ tel: e.tel, exec_id: String(e.exec_id_actual), escribio, libro_key: 'escrituras:' + e.tel + ':' + e.exec_id_actual, libro_entry: libro, aviso, salida }} }}];""", 4180, 420)
    g.si("¿Escribió?", "$json.escribio === true", 4400, 420)
    g.si("¿Avisar?", "!!$json.aviso", 4620, 540)
    g.redis_get("Redis GET libro", "$json.libro_key", "libro_raw", 4620, 300)
    g.code("Sumar al libro", SUMAR_AL_LIBRO, 4840, 300)
    g.redis_set("Redis SET libro", "$json.libro_key", "$json.libro_json", 300, 5060, 300)
    g.code("Aviso a la clínica", f"""const f = $('Final').first().json;
if (f.aviso) {{
  try {{ await this.helpers.httpRequest({{ method: 'POST', url: '{GRUPO}', qs: {{ phone: f.tel, resumen: f.aviso.texto }}, json: true }}); }} catch (e) {{ /* el aviso nunca rompe la respuesta */ }}
}}
return [{{ json: {{ avisado: !!f.aviso }} }}];""", 5280, 300)
    g.code("Devolver", "return [{ json: $('Final').first().json.salida }];", 5500, 420)

    for a, b, s in [("Entrada", "Redis GET propuesta", 0), ("Redis GET propuesta", "Paso inicial", 0), ("Paso inicial", "¿Termina? (inicial)", 0),
                    ("¿Termina? (inicial)", "Final", 0), ("¿Termina? (inicial)", "Redis INCR ejecutando", 1), ("Redis INCR ejecutando", "Paso consumo", 0),
                    ("Paso consumo", "¿Termina? (consumo)", 0), ("¿Termina? (consumo)", "Final", 0), ("¿Termina? (consumo)", "Redis SET propuesta consumida", 1), ("Redis SET propuesta consumida", "Reemitir estado", 0), ("Reemitir estado", "¿Hay cita vieja?", 0),
                    ("¿Hay cita vieja?", "GET cita vieja", 0), ("¿Hay cita vieja?", "Paso cita (sin cita)", 1), ("GET cita vieja", "Paso cita", 0),
                    ("Paso cita", "¿Termina? (cita)", 0), ("Paso cita (sin cita)", "¿Termina? (cita)", 0), ("¿Termina? (cita)", "Final", 0), ("¿Termina? (cita)", "¿Es cancelación?", 1),
                    ("¿Es cancelación?", "Armar anulación", 0), ("¿Es cancelación?", "¿Paciente nuevo?", 1),
                    ("¿Paciente nuevo?", "GET paciente por DNI", 0), ("¿Paciente nuevo?", "Armar reserva", 1), ("GET paciente por DNI", "Paso DNI", 0), ("Paso DNI", "¿Termina? (DNI)", 0),
                    ("¿Termina? (DNI)", "Final", 0), ("¿Termina? (DNI)", "¿Crear paciente?", 1), ("¿Crear paciente?", "POST paciente", 0), ("¿Crear paciente?", "Armar reserva", 1),
                    ("POST paciente", "Paso alta", 0), ("Paso alta", "¿Termina? (alta)", 0), ("¿Termina? (alta)", "Final", 0), ("¿Termina? (alta)", "¿Reintentar sin DNI?", 1),
                    ("¿Reintentar sin DNI?", "POST paciente (sin DNI)", 0), ("¿Reintentar sin DNI?", "Alta lista", 1), ("POST paciente (sin DNI)", "Paso alta (sin DNI)", 0),
                    ("Paso alta (sin DNI)", "¿Termina? (alta sin DNI)", 0), ("¿Termina? (alta sin DNI)", "Final", 0), ("¿Termina? (alta sin DNI)", "Alta lista", 1),
                    ("Alta lista", "Redis DEL ficha", 0), ("Redis DEL ficha", "Redis DEL turnos_vistos", 0), ("Redis DEL turnos_vistos", "Reemitir alta", 0), ("Reemitir alta", "Armar reserva", 0),
                    ("Armar reserva", "POST reserva", 0), ("POST reserva", "Paso reserva", 0),
                    ("Paso reserva", "¿Termina? (reserva)", 0), ("¿Termina? (reserva)", "Final", 0), ("¿Termina? (reserva)", "Armar anulación", 1),
                    ("Armar anulación", "PUT anular", 0), ("PUT anular", "Paso anulación", 0), ("Paso anulación", "Final", 0), ("Final", "¿Escribió?", 0),
                    ("¿Escribió?", "Redis GET libro", 0), ("¿Escribió?", "¿Avisar?", 1), ("¿Avisar?", "Aviso a la clínica", 0), ("¿Avisar?", "Devolver", 1),
                    ("Redis GET libro", "Sumar al libro", 0), ("Sumar al libro", "Redis SET libro", 0),
                    ("Redis SET libro", "Aviso a la clínica", 0), ("Aviso a la clínica", "Devolver", 0)]:
        g.conectar(a, b, s)
    return g.json()


# (08/10) "cerebro" = ORQUESTADOR + SUB-AGENTES (el que se despliega). Las variantes viejas (agente único, cerebro_ma, cerebro_mixto, cerebro_min, agente_clinica)
# se retiraron del build: sus JSON y generadores quedaron en v7/_retirados/ (y en n8n siguen como estaban: crear_v7_en_n8n.py nunca borra).
WORKFLOWS = {"ejecutar_propuesta": wf_ejecutar, "ver_turnos": wf_ver_turnos, "elegir_ficha": wf_elegir_ficha, "proponer": wf_proponer, "buscar_horarios": wf_buscar_horarios, "confirmar_una": wf_confirmar_una, "confirmar_turno": wf_confirmar_turno, "clinica": wf_clinica, "gestionar_turno": wf_gestionar_turno,
             "agente_turnos": wf_agente_turnos, "agente_pagos": wf_agente_pagos, "agente_informacion": wf_agente_informacion, "agente_urgencias": wf_agente_urgencias,
             "cerebro": wf_cerebro,
             # (02/11) "v7 Cerebro Agente": orquestador = AGENTE con los sub-agentes como herramientas. Solo se genera; el despliegue en n8n es aparte (no está en crear_v7_en_n8n.py).
             "cerebro_agente": wf_cerebro_agente}


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    for clave, fn in WORKFLOWS.items():
        wf = fn()
        (SALIDA / f"{clave}.json").write_text(json.dumps(wf, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"v7/workflows/{clave}.json  ({len(wf['nodes'])} nodos)")


if __name__ == "__main__":
    main()
