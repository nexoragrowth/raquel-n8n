# -*- coding: utf-8 -*-
"""v7_workflows_herramientas.py — workflows de las herramientas de AGENDA del v7 (ver_turnos, elegir_ficha, proponer, buscar_horarios), generados como JSON de n8n.
Los llama build_v7_workflows.py. El codigo de los nodos sale de v7/*.js (probado offline); aca solo se arma el grafo."""
from v7_lib import DENTALINK, Grafo

HOY_JS = "const hoy = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Argentina/Jujuy' }).format(new Date());"
SUB_HORARIOS = "GuDQ9VmKWZvQnerV"   # Sub-WF - Buscar Horarios Validado (el mismo que usa el v6)


def wf_ver_turnos():
    """v7 Tool - ver_turnos: resuelve las fichas del celular (una vez, Redis 2 h), trae los turnos vigentes de TODAS y los deja en Redis para las guardas."""
    g = Grafo("v7 Tool - ver_turnos")
    g.trigger({"tel": "5490000000651", "exec_id_actual": "1234"}, 0, 300)
    g.redis_get("Redis GET ficha", "'ficha:' + $json.tel", "ficha_raw", 220, 300)
    g.code("¿Qué ficha hay?", """const e = $('Entrada').first().json;
let est = null; try { est = JSON.parse($input.first().json.ficha_raw || 'null'); } catch (x) { est = null; }
const tiene = !!(est && Array.isArray(est.fichas) && est.fichas.length);
return [{ json: { tiene, estado: tiene ? est : null, last10: String(e.tel).slice(-10) } }];""", 440, 300)
    g.si("¿Ya hay ficha?", "$json.tiene === true", 660, 300)
    g.dentalink("GET fichas del celular", "GET", f"'{DENTALINK}/pacientes'", None, 880, 420, query_expr="JSON.stringify({ celular: { lk: $json.last10 } })")
    g.code("Armar ficha", """const resp = $input.first().json || {};
if (resp.error) return [{ json: { terminado: true, resultado: { ok: false, motivo: 'error_tecnico', para_asiri: 'No pude consultar la agenda en este momento. Decíselo con sinceridad y avisá a la clínica con avisar_grupo (ACCION).' } } }];
const fichas = FichaCore.fichasDeRespuesta(resp);
if (!fichas.length) return [{ json: { terminado: true, resultado: { ok: false, motivo: 'sin_ficha', para_asiri: 'No encuentro una ficha con este celular. Pedile nombre completo y DNI y avisá a la clínica con avisar_grupo (ACCION) para que la den de alta; no inventes turnos.' } } }];
return [{ json: { terminado: false, estado: FichaCore.estadoInicial(fichas) } }];""", 1100, 420, usar=("ficha_core",))
    g.si("¿Termina? (ficha)", "$json.terminado === true", 1320, 420)
    g.redis_set("Redis SET ficha", "'ficha:' + $('Entrada').first().json.tel", "JSON.stringify($('Armar ficha').first().json.estado)", 7200, 1540, 480)
    g.code("Items por ficha", HOY_JS + """
let estado = $input.first().json.estado;
if (!estado) estado = $('Armar ficha').first().json.estado;
return estado.fichas.map((f, i) => ({ json: { idx: i, ficha_id: f.id, hoy, estado } }));""", 1760, 360)
    g.dentalink("GET citas por ficha", "GET", f"'{DENTALINK}/pacientes/' + $json.ficha_id + '/citas'", None, 1980, 360, query_expr="JSON.stringify({ fecha: { gte: $json.hoy } })")
    g.code("Armar turnos", """const items = $('Items por ficha').all();
const estado = items[0].json.estado; const hoy = items[0].json.hoy;
const resps = $input.all().map((i) => i.json);
if (resps.some((r) => r && r.error)) return [{ json: { terminado: true, resultado: { ok: false, motivo: 'error_tecnico', para_asiri: 'No pude consultar los turnos en la agenda. Decíselo con sinceridad y avisá a la clínica con avisar_grupo (ACCION); no inventes turnos.' } } }];
const turnos = FichaCore.turnosVistos(estado.fichas, resps, hoy);
const varias = estado.fichas.length > 1;
return [{ json: { terminado: false, turnos, resultado: { ok: true, varias_fichas: varias, ficha_elegida: estado.elegida !== null, paciente_elegido: estado.elegida !== null ? ((estado.fichas.find((f) => f.id === estado.elegida) || {}).nombre || null) : null, pacientes: varias ? estado.fichas.map((f) => f.nombre) : undefined, turnos: FichaCore.resumenTurnos(estado.fichas, turnos),
  para_asiri: varias && estado.elegida === null ? 'Este celular tiene varias fichas: preguntá para quién es (nombre o DNI) y llamá a elegir_ficha antes de proponer cualquier cambio.' : 'Estos son los turnos vigentes. No muestres ids.' } } }];""", 2200, 360, usar=("ficha_core",))
    g.si("¿Termina? (turnos)", "$json.terminado === true", 2420, 360)
    g.redis_set("Redis SET turnos_vistos", "'turnos_vistos:' + $('Entrada').first().json.tel", "JSON.stringify($('Armar turnos').first().json.turnos)", 7200, 2640, 420)
    g.code("Devolver", """const j = $input.first().json;
if (j.resultado) return [{ json: j.resultado }];
return [{ json: $('Armar turnos').first().json.resultado }];""", 2860, 360)
    for a, b, s_ in [("Entrada", "Redis GET ficha", 0), ("Redis GET ficha", "¿Qué ficha hay?", 0), ("¿Qué ficha hay?", "¿Ya hay ficha?", 0), ("¿Ya hay ficha?", "Items por ficha", 0), ("¿Ya hay ficha?", "GET fichas del celular", 1),
                     ("GET fichas del celular", "Armar ficha", 0), ("Armar ficha", "¿Termina? (ficha)", 0), ("¿Termina? (ficha)", "Devolver", 0), ("¿Termina? (ficha)", "Redis SET ficha", 1), ("Redis SET ficha", "Items por ficha", 0),
                     ("Items por ficha", "GET citas por ficha", 0), ("GET citas por ficha", "Armar turnos", 0), ("Armar turnos", "¿Termina? (turnos)", 0), ("¿Termina? (turnos)", "Devolver", 0),
                     ("¿Termina? (turnos)", "Redis SET turnos_vistos", 1), ("Redis SET turnos_vistos", "Devolver", 0)]:
        g.conectar(a, b, s_)
    return g.json()


def wf_elegir_ficha():
    """v7 Tool - elegir_ficha: el paciente dice para quién es (nombre o DNI); el código verifica contra las fichas reales del celular."""
    g = Grafo("v7 Tool - elegir_ficha")
    g.trigger({"tel": "5490000000651", "exec_id_actual": "1234", "nombre": "", "dni": ""}, 0, 200)
    g.redis_get("Redis GET ficha", "'ficha:' + $json.tel", "ficha_raw", 220, 200)
    g.code("Elegir", """const e = $('Entrada').first().json;
let est = null; try { est = JSON.parse($input.first().json.ficha_raw || 'null'); } catch (x) { est = null; }
if (!est || !Array.isArray(est.fichas) || !est.fichas.length) return [{ json: { ok: false, resultado: { ok: false, motivo: 'sin_ficha', para_asiri: 'Primero llamá a ver_turnos.' } } }];
const r = FichaCore.elegir(est, { nombre: e.nombre, dni: e.dni });
return [{ json: r.ok ? { ok: true, estado: r.estado, resultado: { ok: true, paciente: r.nombre, para_asiri: 'Listo, ya está identificado el paciente. Seguí con ver_turnos o con la propuesta.' } }
  : { ok: false, resultado: { ok: false, motivo: r.motivo, para_asiri: r.para_asiri, fichas: r.fichas || null } } }];""", 440, 200, usar=("ficha_core",))
    g.si("¿Eligió?", "$json.ok === true", 660, 200)
    g.redis_set("Redis SET ficha", "'ficha:' + $('Entrada').first().json.tel", "JSON.stringify($('Elegir').first().json.estado)", 1200, 880, 140)
    g.code("Devolver", "return [{ json: $('Elegir').first().json.resultado }];", 1100, 200)
    for a, b, s_ in [("Entrada", "Redis GET ficha", 0), ("Redis GET ficha", "Elegir", 0), ("Elegir", "¿Eligió?", 0), ("¿Eligió?", "Redis SET ficha", 0), ("¿Eligió?", "Devolver", 1), ("Redis SET ficha", "Devolver", 0)]:
        g.conectar(a, b, s_)
    return g.json()


def wf_proponer():
    """v7 Tool - proponer: valida por código (ficha, cita vista, horario ofrecido, 48 h) y guarda la propuesta; devuelve el read-back armado por el código."""
    g = Grafo("v7 Tool - proponer")
    g.trigger({"tel": "5490000000651", "exec_id_actual": "1234", "tipo": "cambio", "fecha": "", "hora": "", "fecha_turno_viejo": ""}, 0, 200)
    g.redis_get("Redis GET ficha", "'ficha:' + $json.tel", "ficha_raw", 220, 200)
    g.redis_get("Redis GET turnos_vistos", "'turnos_vistos:' + $('Entrada').first().json.tel", "turnos_raw", 440, 200)
    g.redis_get("Redis GET ofertas", "'ofertas:' + $('Entrada').first().json.tel", "ofertas_raw", 660, 200)
    g.code("Proponer", """const e = $('Entrada').first().json;
const j = (nodo, campo) => { try { return JSON.parse($(nodo).first().json[campo] || 'null'); } catch (x) { return null; } };
const estado = { tel: e.tel, exec_id: String(e.exec_id_actual), ficha: j('Redis GET ficha', 'ficha_raw') || { fichas: [], elegida: null }, turnos_vistos: j('Redis GET turnos_vistos', 'turnos_raw'), ofertas: j('Redis GET ofertas', 'ofertas_raw') || [] };
const r = AgendaCore.proponer({ tipo: e.tipo, fecha: e.fecha, hora: e.hora, fecha_turno_viejo: e.fecha_turno_viejo || undefined }, estado, new Date().toISOString());
if (r.ok) return [{ json: { ok: true, propuesta_json: JSON.stringify(r.propuesta), resultado: { ok: true, texto_para_el_paciente: r.readback_text, para_asiri: r.para_asiri } } }];
return [{ json: { ok: false, resultado: r } }];""", 880, 200, usar=("agenda_core",))
    g.si("¿Propuso?", "$json.ok === true", 1100, 200)
    g.redis_set("Redis SET propuesta", "'propuesta:' + $('Entrada').first().json.tel", "$('Proponer').first().json.propuesta_json", 1800, 1320, 140)
    g.code("Devolver", "return [{ json: $('Proponer').first().json.resultado }];", 1540, 200)
    for a, b, s_ in [("Entrada", "Redis GET ficha", 0), ("Redis GET ficha", "Redis GET turnos_vistos", 0), ("Redis GET turnos_vistos", "Redis GET ofertas", 0), ("Redis GET ofertas", "Proponer", 0), ("Proponer", "¿Propuso?", 0),
                     ("¿Propuso?", "Redis SET propuesta", 0), ("¿Propuso?", "Devolver", 1), ("Redis SET propuesta", "Devolver", 0)]:
        g.conectar(a, b, s_)
    return g.json()


def wf_buscar_horarios():
    """v7 Tool - buscar_horarios: usa el sub-WF de horarios del v6, registra lo ofrecido en Redis (lo único reservable), limita a 2 bloques por conversación y NO cuenta como bloque nuevo
    un pedido idéntico al anterior (el modelo a veces la llama dos veces): devuelve el bloque que ya tenía."""
    g = Grafo("v7 Tool - buscar_horarios")
    g.trigger({"tel": "5490000000651", "exec_id_actual": "1234", "desde": "", "hasta": ""}, 0, 240)
    g.redis_get("Redis GET ofertas", "'ofertas:' + $json.tel", "ofertas_raw", 220, 240)
    g.redis_get("Redis GET bloque", "'bloque:' + $('Entrada').first().json.tel", "bloque_raw", 440, 240)
    g.redis_get("Redis GET bloque_req", "'bloque_req:' + $('Entrada').first().json.tel", "req_raw", 660, 240)
    g.code("¿Es el mismo pedido?", """const e = $('Entrada').first().json;
const req = String(e.desde || '') + '|' + String(e.hasta || '');
const cache = String($('Redis GET bloque').first().json.bloque_raw || '');
const ultimo = String($('Redis GET bloque_req').first().json.req_raw || '');
const hit = !!cache && ultimo === req;
let prev = []; try { prev = JSON.parse($('Redis GET ofertas').first().json.ofertas_raw || '[]') || []; } catch (x) { prev = []; }
return [{ json: { hit, req, prev, resultado: hit ? { ok: true, repetido: true, bloque: cache, para_asiri: 'Este es el MISMO bloque que ya le ofreciste (no cuenta como uno nuevo). Si el paciente ya eligió un horario, NO lo pegues de nuevo: llamá proponer.' } : null } }];""", 880, 240)
    g.si("¿Repetido?", "$json.hit === true", 1100, 240)
    g.redis_incr("Redis INCR lotes", "'lotes:' + $('Entrada').first().json.tel", 7200, 1320, 300)
    g.code("Límite", """const prev = $('¿Es el mismo pedido?').first().json.prev || [];
const n = Object.values($input.first().json || {})[0];
if (HorariosCore.limiteLotes(n)) return [{ json: { terminado: true, resultado: { ok: false, motivo: 'limite_de_bloques', para_asiri: 'Ya se le ofrecieron dos bloques de horarios y no hay un tercero. No ofrezcas otro: decile con amabilidad que se lo dejás anotado a la clínica para que lo ayuden con otra fecha, y llamá avisar_grupo con nivel FYI.' } } }];
return [{ json: { terminado: false, prev } }];""", 1540, 300, usar=("horarios_core",))
    g.si("¿Termina? (límite)", "$json.terminado === true", 1760, 300)
    g.subworkflow("Buscar horarios (sub-WF)", SUB_HORARIOS, {"fecha": "''", "desde": "$('Entrada').first().json.desde || ''", "hasta": "$('Entrada').first().json.hasta || ''"}, 1980, 360)
    g.code("Ofertas", HOY_JS + """
const prev = $('Límite').first().json.prev || [];
const resp = $input.first().json || {};
const bloque = typeof resp.bloque === 'string' ? resp.bloque.trim() : '';
if (!bloque) return [{ json: { terminado: true, resultado: { ok: false, motivo: (resp.error || resp.error_tecnico) ? 'error_tecnico' : 'sin_turnos', para_asiri: (resp.error || resp.error_tecnico) ? 'No pude consultar la agenda en este momento. Decíselo con sinceridad y avisá a la clínica con avisar_grupo (ACCION).' : 'No hay turnos para ofrecer en ese rango. No inventes horarios ni pidas fecha: avisá a la clínica con avisar_grupo (ACCION).' } } }];
const ofertas = HorariosCore.unir(prev, HorariosCore.parseBloque(bloque, hoy), hoy);
return [{ json: { terminado: false, ofertas_json: JSON.stringify(ofertas), bloque, req: $('¿Es el mismo pedido?').first().json.req, resultado: { ok: true, bloque, para_asiri: 'Pegá este bloque TEXTUAL al paciente, sin cambiar ni agregar nada. No le preguntes la franja ni la fecha: que elija de lo que ofrecés.' } } }];""", 2200, 360, usar=("horarios_core",))
    g.si("¿Termina? (ofertas)", "$json.terminado === true", 2420, 360)
    g.redis_set("Redis SET ofertas", "'ofertas:' + $('Entrada').first().json.tel", "$('Ofertas').first().json.ofertas_json", 7200, 2640, 420)
    g.redis_set("Redis SET bloque", "'bloque:' + $('Entrada').first().json.tel", "$('Ofertas').first().json.bloque", 7200, 2860, 420)
    g.redis_set("Redis SET bloque_req", "'bloque_req:' + $('Entrada').first().json.tel", "$('Ofertas').first().json.req", 7200, 3080, 420)
    g.redis_set("Redis SET bloque_exec", "'bloque_exec:' + $('Entrada').first().json.tel + ':' + $('Entrada').first().json.exec_id_actual", "$('Ofertas').first().json.bloque", 600, 3300, 420)
    g.code("Devolver", """// El resultado sale del último nodo de decisión que corrió: Ofertas (bloque nuevo / sin turnos / error), si no Límite (tercer bloque), si no el pedido repetido (caché).
const corrio = (n) => { try { return $(n).isExecuted === true; } catch (x) { return false; } };
const r = corrio('Ofertas') ? $('Ofertas').first().json.resultado : (corrio('Límite') ? $('Límite').first().json.resultado : $('¿Es el mismo pedido?').first().json.resultado);
return [{ json: r || { ok: false, motivo: 'error_tecnico', para_asiri: 'No pude buscar horarios; avisá a la clínica con avisar_grupo (ACCION).' } }];""", 3520, 300)
    for a, b, s_ in [("Entrada", "Redis GET ofertas", 0), ("Redis GET ofertas", "Redis GET bloque", 0), ("Redis GET bloque", "Redis GET bloque_req", 0), ("Redis GET bloque_req", "¿Es el mismo pedido?", 0),
                     ("¿Es el mismo pedido?", "¿Repetido?", 0), ("¿Repetido?", "Devolver", 0), ("¿Repetido?", "Redis INCR lotes", 1), ("Redis INCR lotes", "Límite", 0), ("Límite", "¿Termina? (límite)", 0),
                     ("¿Termina? (límite)", "Devolver", 0), ("¿Termina? (límite)", "Buscar horarios (sub-WF)", 1), ("Buscar horarios (sub-WF)", "Ofertas", 0), ("Ofertas", "¿Termina? (ofertas)", 0),
                     ("¿Termina? (ofertas)", "Devolver", 0), ("¿Termina? (ofertas)", "Redis SET ofertas", 1), ("Redis SET ofertas", "Redis SET bloque", 0), ("Redis SET bloque", "Redis SET bloque_req", 0),
                     ("Redis SET bloque_req", "Redis SET bloque_exec", 0), ("Redis SET bloque_exec", "Devolver", 0)]:
        g.conectar(a, b, s_)
    return g.json()
