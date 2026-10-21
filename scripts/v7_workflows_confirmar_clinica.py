# -*- coding: utf-8 -*-
"""v7_workflows_confirmar_clinica.py — workflows de confirmar_turno y de las herramientas de CLÍNICA del v7, generados como JSON de n8n.
Los llama build_v7_workflows.py. El código de los nodos sale de v7/*.js (probado offline)."""
from v7_lib import CRED_POSTGRES, DENTALINK, Grafo

GRUPO = "https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo"
HOY_JS = "const hoy = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Argentina/Jujuy' }).format(new Date());"

SUMAR_AL_LIBRO = """const f = $('Final').first().json;
let arr = []; try { arr = JSON.parse($input.first().json.libro_raw || '[]'); } catch (e) { arr = []; }
if (!Array.isArray(arr)) arr = [arr];
arr.push(f.libro_entry);
return [{ json: { libro_key: f.libro_key, libro_json: JSON.stringify(arr) } }];"""


def postgres(g, nombre, query, replacement_expr, x, y):
    return g._nodo(nombre, "n8n-nodes-base.postgres", 2.5, {"operation": "executeQuery", "query": query, "options": {"queryReplacement": "={{ " + replacement_expr + " }}"}}, x, y,
                   {"credentials": CRED_POSTGRES, "alwaysOutputData": True, "continueOnFail": True})


def wf_confirmar_turno():
    """v7 Tool - confirmar_turno (21/10): elige TODOS los turnos a confirmar (recordatorios abiertos; filtrados por fecha/hora/nombre si el paciente
    confirmó uno de varios), llama a "v7 Tool - confirmar_una" UNA VEZ POR TURNO y junta todo en un solo mensaje y un solo asiento del libro.
    Incidente que lo motivó: dos hermanos con turno el mismo día → "¿Cuál de estos turnos confirma?" en bucle (se elegía solo por fecha)."""
    g = Grafo("v7 Tool - confirmar_turno")
    g.trigger({"tel": "5490000000651", "exec_id_actual": "1234", "modo": "vivo", "fecha": "", "hora": "", "nombre": ""}, 0, 300)
    postgres(g, "Recordatorios abiertos",
             "SELECT id_cita_dentalink, id_paciente_dentalink, nombre_paciente, fecha_turno, hora_turno FROM recordatorios_enviados WHERE telefono = $1 AND confirmado_at IS NULL AND cancelado_at IS NULL AND fecha_turno >= (now() AT TIME ZONE 'America/Argentina/Jujuy')::date ORDER BY fecha_turno, hora_turno",
             "$json.tel", 220, 300)
    g.redis_get("Redis GET turnos_vistos", "'turnos_vistos:' + $('Entrada').first().json.tel", "turnos_raw", 440, 300)
    g.code("Elegir citas", HOY_JS + """
const e = $('Entrada').first().json;
const rows = $('Recordatorios abiertos').all().map((i) => i.json).filter((r) => r && r.id_cita_dentalink);
let vistos = null; try { vistos = JSON.parse($input.first().json.turnos_raw || 'null'); } catch (x) { vistos = null; }
const r = ConfirmarCore.elegir(rows, vistos, e.fecha || '', hoy, e.hora || '', e.nombre || '');
if (r.fin) return [{ json: { terminado: true, resultado: r.fin } }];
return r.cands.map((cand) => ({ json: { terminado: false, cand } }));""", 660, 300, usar=("confirmar_core",))
    g.si("¿Termina? (elegir)", "$json.terminado === true", 880, 300)
    n = g.subworkflow("Confirmar cada una", "@@ID:confirmar_una@@", {"tel": "$('Entrada').first().json.tel", "exec_id_actual": "$('Entrada').first().json.exec_id_actual",
                                                                   "modo": "$('Entrada').first().json.modo", "cand_json": "JSON.stringify($json.cand)"}, 1100, 360)
    next(x for x in g.nodos if x["name"] == n)["parameters"]["mode"] = "each"   # un llamado por turno elegido
    g.code("Final", """const e = $('Entrada').first().json;
const sombra = e.modo !== 'vivo';
let r;
if ($('Confirmar cada una').isExecuted) {
  // Un sub-workflow que se cayó (continueOnFail) llega como { error }: cuenta como falla de ESE turno.
  const cands = $('Elegir citas').all().map((i) => i.json.cand);
  const res = $('Confirmar cada una').all().map((i, k) => (i.json && i.json.cand ? i.json : { ok: false, motivo: 'error_tecnico', cand: cands[k] }));
  r = ConfirmarCore.resumir(res);
} else {
  r = $('Elegir citas').first().json.resultado || { ok: false, motivo: 'error_tecnico' };
}
// Aviso a la clínica si se confirmó a medias (vivo solamente; nunca rompe la respuesta).
if (r.aviso && !sombra) { try { await this.helpers.httpRequest({ method: 'POST', url: '""" + GRUPO + """', qs: { phone: e.tel, resumen: r.aviso }, json: true }); } catch (x) { /* nada */ } }
const escribio = !!(r.ok === true && (r.escribio === true || r.ya === true || sombra));
const libro = { ok: r.ok === true, simulado: sombra || undefined, parcial: r.parcial === true, tipo: 'confirmacion', readback_text: r.readback_text || null, nueva_cita: null, vieja_anulada: null };
const salida = { ok: r.ok === true, simulado: sombra || undefined, motivo: r.motivo || null, ya_estaba_confirmada: r.ya === true, readback_text: r.readback_text || null,
  para_asiri: r.para_asiri || (r.ok === true ? '[Nota interna para vos, NO la repitas al paciente] El texto para el paciente es readback_text: mandáselo tal cual (ya incluye todos los turnos confirmados). Si en el mismo mensaje pidió otras cosas (precio, otro turno, datos), resolvelas en esa misma respuesta. No vuelvas a llamar a confirmar_turno.' : null),
  fechas: r.fechas || null, fechas_iso: r.fechas_iso || null, confirmados: (r.cands || []).length };
return [{ json: { tel: e.tel, escribio, libro_key: 'escrituras:' + e.tel + ':' + e.exec_id_actual, libro_entry: libro, salida } }];""", 1320, 300, usar=("confirmar_core",))
    g.si("¿Escribió?", "$json.escribio === true", 1540, 300)
    g.redis_get("Redis GET libro", "$json.libro_key", "libro_raw", 1760, 240)
    g.code("Sumar al libro", SUMAR_AL_LIBRO, 1980, 240)
    g.redis_set("Redis SET libro", "$json.libro_key", "$json.libro_json", 300, 2200, 240)
    g.code("Devolver", "return [{ json: $('Final').first().json.salida }];", 2420, 300)
    for a, b, s_ in [("Entrada", "Recordatorios abiertos", 0), ("Recordatorios abiertos", "Redis GET turnos_vistos", 0), ("Redis GET turnos_vistos", "Elegir citas", 0), ("Elegir citas", "¿Termina? (elegir)", 0),
                     ("¿Termina? (elegir)", "Final", 0), ("¿Termina? (elegir)", "Confirmar cada una", 1), ("Confirmar cada una", "Final", 0),
                     ("Final", "¿Escribió?", 0), ("¿Escribió?", "Redis GET libro", 0), ("¿Escribió?", "Devolver", 1), ("Redis GET libro", "Sumar al libro", 0), ("Sumar al libro", "Redis SET libro", 0), ("Redis SET libro", "Devolver", 0)]:
        g.conectar(a, b, s_)
    return g.json()


def wf_confirmar_una():
    """v7 Tool - confirmar_una (21/10): confirma (id_estado 18) UNA cita ya elegida por confirmar_turno; verifica antes contra la agenda y marca el
    recordatorio. Devuelve { ok, ya, escribio, motivo, para_asiri, cand }. El libro y el texto para el paciente los arma confirmar_turno."""
    g = Grafo("v7 Tool - confirmar_una")
    # (08/10) INCIDENTE: el trigger no declaraba `modo`, n8n lo descartaba y en "sombra" se confirmaron de verdad 11 citas reales (retrospectiva del 06/10).
    # Ahora solo escribe con modo === 'vivo' explícito; cualquier otra cosa (o nada) es sombra: verifica pero no hace el PUT ni marca el recordatorio.
    g.trigger({"tel": "5490000000651", "exec_id_actual": "1234", "modo": "vivo", "cand_json": ""}, 0, 300)
    g.code("Elegir cita", """const e = $('Entrada').first().json;
let cand = null; try { cand = JSON.parse(e.cand_json || 'null'); } catch (x) { cand = null; }
if (!cand || !cand.cita_id) return [{ json: { terminado: true, resultado: { ok: false, motivo: 'error_tecnico', para_asiri: 'No pude identificar el turno a confirmar.' } } }];
return [{ json: { terminado: false, cand } }];""", 660, 300)
    g.si("¿Termina? (elegir)", "$json.terminado === true", 880, 300)
    g.dentalink("GET cita", "GET", f"'{DENTALINK}/citas/' + $json.cand.cita_id", None, 1100, 360)
    g.code("Verificar", """const cand = $('Elegir cita').first().json.cand;
const r = ConfirmarCore.verificar(cand, $input.first().json);
return [{ json: r.fin ? { terminado: true, resultado: r.fin } : { terminado: false, cand, ya: r.ya } }];""", 1320, 360, usar=("confirmar_core",))
    g.si("¿Termina? (verificar)", "$json.terminado === true", 1540, 360)
    g.si("¿Es sombra?", "$('Entrada').first().json.modo !== 'vivo'", 1650, 300)
    g.si("¿Ya estaba confirmada?", "$json.ya === true", 1760, 420)
    g.dentalink("PUT confirmar", "PUT", f"'{DENTALINK}/citas/' + $json.cand.cita_id", "JSON.stringify({ id_estado: 18 })", 1980, 480)
    g.code("Evaluar confirmación", """const cand = $('Verificar').first().json.cand;
const r = ConfirmarCore.evaluarConfirmacion(cand, $input.first().json);
return [{ json: r.fin ? { terminado: true, resultado: r.fin } : { terminado: false, cand, ya: r.ya, escribio: true } }];""", 2200, 480, usar=("confirmar_core",))
    g.si("¿Termina? (confirmar)", "$json.terminado === true", 2420, 480)
    g.si("¿Viene de un recordatorio?", "$json.cand.origen === 'recordatorio'", 2640, 540)
    postgres(g, "Marcar recordatorio", "UPDATE recordatorios_enviados SET confirmado_at = now() WHERE id_cita_dentalink = $1 AND confirmado_at IS NULL", "$json.cand.cita_id", 2860, 480)
    g.code("Final", """const e = $('Entrada').first().json;
// Se llega acá por varios caminos (el UPDATE de Postgres pisa el ítem): el estado se lee del ÚLTIMO nodo de decisión que corrió.
const corrio = (n) => { try { return $(n).isExecuted === true; } catch (x) { return false; } };
const j = corrio('Evaluar confirmación') ? $('Evaluar confirmación').first().json : (corrio('Verificar') ? $('Verificar').first().json : $('Elegir cita').first().json);
const cand = $('Elegir cita').first().json.cand || null;
// (07/10) Un turno que la agenda ya tenía confirmado (verificado con el GET) también cuenta como escrito: el chequeo de salida necesita saber que
// "su turno … está confirmado" es verdad (examen CON-01 y MULTI-01). En sombra queda marcado simulado (no escribió nada).
const sombra = e.modo !== 'vivo';
if (j.resultado) return [{ json: { ok: false, motivo: j.resultado.motivo || 'error_tecnico', para_asiri: j.resultado.para_asiri || null, ya: false, escribio: false, simulado: sombra || undefined, cand } }];
return [{ json: { ok: true, ya: j.ya === true, escribio: j.escribio === true || j.ya === true || sombra, simulado: sombra || undefined, motivo: null, para_asiri: null, cand } }];""", 3080, 360, usar=("confirmar_core",))
    for a, b, s_ in [("Entrada", "Elegir cita", 0), ("Elegir cita", "¿Termina? (elegir)", 0),
                     ("¿Termina? (elegir)", "Final", 0), ("¿Termina? (elegir)", "GET cita", 1), ("GET cita", "Verificar", 0), ("Verificar", "¿Termina? (verificar)", 0), ("¿Termina? (verificar)", "Final", 0),
                     ("¿Termina? (verificar)", "¿Es sombra?", 1), ("¿Es sombra?", "Final", 0), ("¿Es sombra?", "¿Ya estaba confirmada?", 1), ("¿Ya estaba confirmada?", "¿Viene de un recordatorio?", 0), ("¿Ya estaba confirmada?", "PUT confirmar", 1),
                     ("PUT confirmar", "Evaluar confirmación", 0), ("Evaluar confirmación", "¿Termina? (confirmar)", 0), ("¿Termina? (confirmar)", "Final", 0), ("¿Termina? (confirmar)", "¿Viene de un recordatorio?", 1),
                     ("¿Viene de un recordatorio?", "Marcar recordatorio", 0), ("¿Viene de un recordatorio?", "Final", 1), ("Marcar recordatorio", "Final", 0)]:
        g.conectar(a, b, s_)
    return g.json()
