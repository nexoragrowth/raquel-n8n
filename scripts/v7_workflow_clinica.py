# -*- coding: utf-8 -*-
"""v7_workflow_clinica.py — workflow "v7 Tool - clinica": avisar_grupo, pasar_a_humano, registrar_pago, lista_espera y derivar_triaje (deja la marca `triaje_v7:{tel}:{exec}` que lee el cerebro). La decisión la toma v7/clinica_core.js (probada offline)."""
from v7_lib import Grafo

GRUPO = "https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo"
CLAVES_ESTADO = ["propuesta", "ofertas", "lotes", "turnos_vistos", "bloque"]   # el staff interviene: ninguna propuesta vieja puede ejecutarse después


def wf_clinica():
    g = Grafo("v7 Tool - clinica")
    g.trigger({"tel": "5490000000651", "exec_id_actual": "1234", "modo": "vivo", "accion": "aviso", "nivel": "FYI", "texto": "", "motivo": "", "cita_textual": "", "texto_paciente": ""}, 0, 260)
    g.redis_get("Redis GET pago", "'pago:' + $json.tel", "pago_raw", 220, 260)
    g.code("Decidir", """const e = $('Entrada').first().json;
const r = ClinicaCore.decidir({ accion: e.accion, nivel: e.nivel, texto: e.texto, motivo: e.motivo, cita_textual: e.cita_textual, texto_paciente: e.texto_paciente, modo: e.modo, tel: e.tel,
  pago_reciente: !!$input.first().json.pago_raw });
return [{ json: { avisar: r.avisar, marcar_pago: r.marcar_pago, limpiar: r.limpiar, triaje: r.triaje, resultado: r.resultado } }];""", 440, 260, usar=("clinica_core",))
    g.si("¿Derivar a triaje?", "!!$json.triaje", 550, 260)
    g.redis_set("Redis SET triaje", "'triaje_v7:' + $('Entrada').first().json.tel + ':' + $('Entrada').first().json.exec_id_actual", "JSON.stringify($('Decidir').first().json.triaje)", 300, 600, 140)
    g.si("¿Avisar?", "!!$('Decidir').first().json.avisar", 660, 260)
    g.code("Avisar al grupo", f"""const e = $('Entrada').first().json; const a = $('Decidir').first().json.avisar;
let enviado = false;
try {{ await this.helpers.httpRequest({{ method: 'POST', url: '{GRUPO}', qs: Object.assign({{ phone: e.tel, resumen: a.resumen }}, a.tomar ? {{ tomar: 'true' }} : {{}}), json: true }}); enviado = true; }} catch (x) {{ enviado = false; }}
return [{{ json: {{ enviado }} }}];""", 880, 200)
    g.si("¿Marcar pago?", "$('Decidir').first().json.marcar_pago === true", 1100, 260)
    g.redis_set("Redis SET pago", "'pago:' + $('Entrada').first().json.tel", "'1'", 900, 1320, 200)
    g.si("¿Limpiar estado?", "$('Decidir').first().json.limpiar === true", 1540, 260)
    x = 1760
    for clave in CLAVES_ESTADO:
        g.redis_del(f"Redis DEL {clave}", f"'{clave}:' + $('Entrada').first().json.tel", x, 200)
        x += 220
    g.code("Devolver", """const r = $('Decidir').first().json.resultado;
const f = $('Avisar al grupo');
const fallo = (f.isExecuted === true) && $('Avisar al grupo').first().json.enviado === false;
return [{ json: fallo ? { ...r, aviso_no_enviado: true, para_asiri: (r.para_asiri || '') + ' (OJO: el aviso a la clínica no pudo enviarse; no digas que ya les avisaste.)' } : r }];""", x, 260)
    cadena = [f"Redis DEL {c}" for c in CLAVES_ESTADO]
    for a, b, s in [("Entrada", "Redis GET pago", 0), ("Redis GET pago", "Decidir", 0), ("Decidir", "¿Derivar a triaje?", 0), ("¿Derivar a triaje?", "Redis SET triaje", 0), ("¿Derivar a triaje?", "¿Avisar?", 1), ("Redis SET triaje", "¿Avisar?", 0), ("¿Avisar?", "Avisar al grupo", 0), ("¿Avisar?", "¿Marcar pago?", 1), ("Avisar al grupo", "¿Marcar pago?", 0),
                    ("¿Marcar pago?", "Redis SET pago", 0), ("¿Marcar pago?", "¿Limpiar estado?", 1), ("Redis SET pago", "¿Limpiar estado?", 0), ("¿Limpiar estado?", cadena[0], 0), ("¿Limpiar estado?", "Devolver", 1)]:
        g.conectar(a, b, s)
    for a, b in zip(cadena, cadena[1:] + ["Devolver"]):
        g.conectar(a, b, 0)
    return g.json()
