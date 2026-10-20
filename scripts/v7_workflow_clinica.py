# -*- coding: utf-8 -*-
"""v7_workflow_clinica.py — workflow "v7 Tool - clinica": derivar (a la secretaria), humano (pidió una persona), pago, datos_pago, espera, triaje (deja la marca
`triaje_v7:{tel}:{exec}` que lee el cerebro) y aviso. La decisión la toma v7/clinica_core.js (probada offline); el texto para el paciente también lo arma el código.
(08/10, orquestador) Contadores PROPIOS por acción, separados por modo (en sombra todo va a claves `v7s:`): `deriva:` (insistencia fuera de alcance → modo humano),
`avisos:` (avisos técnicos), `pago:` (pago ya anotado). En sombra no se llama al webhook del grupo: nunca silencia ni avisa por el chat real."""
from v7_lib import Grafo

GRUPO = "https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo"
CLAVES_ESTADO = ["propuesta", "ofertas", "lotes", "turnos_vistos", "bloque"]   # una persona toma el chat: ninguna propuesta vieja puede ejecutarse después
ENT = "$('Entrada').first().json"
PRE = f"({ENT}.modo === 'vivo' ? '{{c}}:' : 'v7s:{{c}}:') + {ENT}.tel"


def clave(c):
    return PRE.replace("{c}", c)


def wf_clinica():
    g = Grafo("v7 Tool - clinica")
    g.trigger({"tel": "5490000000651", "exec_id_actual": "1234", "modo": "vivo", "accion": "aviso", "nivel": "FYI", "texto": "", "motivo": "", "cita_textual": "", "texto_paciente": "", "moneda": ""}, 0, 260)
    g.redis_get("Redis GET pago", clave("pago"), "pago_raw", 220, 260)
    g.redis_get("Redis GET avisos", clave("avisos"), "avisos_raw", 330, 380)
    g.redis_get("Redis GET deriva", clave("deriva"), "deriva_raw", 385, 260)
    g.code("Decidir", """const e = $('Entrada').first().json;
const r = ClinicaCore.decidir({ accion: e.accion, nivel: e.nivel, texto: e.texto, motivo: e.motivo, cita_textual: e.cita_textual, texto_paciente: e.texto_paciente, moneda: e.moneda, modo: e.modo, tel: e.tel,
  pago_reciente: !!$('Redis GET pago').first().json.pago_raw, avisos_recientes: Number($('Redis GET avisos').first().json.avisos_raw || 0), deriva_recientes: Number($('Redis GET deriva').first().json.deriva_raw || 0) });
return [{ json: { avisar: r.avisar, marcar_pago: r.marcar_pago, limpiar: r.limpiar, contar_deriva: r.contar_deriva === true, triaje: r.triaje, resultado: r.resultado } }];""", 440, 260, usar=("clinica_core",))
    g.si("¿Derivar a triaje?", "!!$json.triaje", 550, 260)
    g.redis_set("Redis SET triaje", f"'triaje_v7:' + {ENT}.tel + ':' + {ENT}.exec_id_actual", "JSON.stringify($('Decidir').first().json.triaje)", 300, 600, 140)
    g.si("¿Avisar?", "!!$('Decidir').first().json.avisar && $('Entrada').first().json.modo === 'vivo'", 660, 260)
    g.code("Avisar al grupo", f"""const e = $('Entrada').first().json; const a = $('Decidir').first().json.avisar;
let enviado = false;
try {{ await this.helpers.httpRequest({{ method: 'POST', url: '{GRUPO}', qs: Object.assign({{ phone: e.tel, resumen: a.resumen }}, a.tomar ? {{ tomar: 'true' }} : {{}}), json: true }}); enviado = true; }} catch (x) {{ enviado = false; }}
return [{{ json: {{ enviado }} }}];""", 880, 200)
    g.si("¿Es aviso común?", "$('Entrada').first().json.accion === 'aviso' && $('Decidir').first().json.resultado.ok === true && !$('Decidir').first().json.resultado.ya_avisado", 990, 140)
    g.redis_incr("Redis INCR avisos", clave("avisos"), 1800, 1045, 60)
    g.si("¿Contar derivación?", "$('Decidir').first().json.contar_deriva === true", 1070, 200)
    g.redis_incr("Redis INCR deriva", clave("deriva"), 1800, 1085, 120)
    g.si("¿Marcar pago?", "$('Decidir').first().json.marcar_pago === true", 1100, 260)
    g.redis_set("Redis SET pago", clave("pago"), "'1'", 900, 1320, 200)
    g.si("¿Limpiar estado?", "$('Decidir').first().json.limpiar === true && $('Entrada').first().json.modo === 'vivo'", 1540, 260)
    x = 1760
    for c in CLAVES_ESTADO:
        g.redis_del(f"Redis DEL {c}", f"'{c}:' + {ENT}.tel", x, 200)
        x += 220
    g.code("Devolver", """const r = $('Decidir').first().json.resultado;
const f = $('Avisar al grupo');
const fallo = (f.isExecuted === true) && $('Avisar al grupo').first().json.enviado === false;
return [{ json: fallo ? { ...r, aviso_no_enviado: true } : r }];""", x, 260)
    cadena = [f"Redis DEL {c}" for c in CLAVES_ESTADO]
    for a, b, s in [("Entrada", "Redis GET pago", 0), ("Redis GET pago", "Redis GET avisos", 0), ("Redis GET avisos", "Redis GET deriva", 0), ("Redis GET deriva", "Decidir", 0),
                    ("Decidir", "¿Derivar a triaje?", 0), ("¿Derivar a triaje?", "Redis SET triaje", 0), ("¿Derivar a triaje?", "¿Avisar?", 1), ("Redis SET triaje", "¿Avisar?", 0),
                    ("¿Avisar?", "Avisar al grupo", 0), ("¿Avisar?", "¿Es aviso común?", 1), ("Avisar al grupo", "¿Es aviso común?", 0),
                    ("¿Es aviso común?", "Redis INCR avisos", 0), ("¿Es aviso común?", "¿Contar derivación?", 1), ("Redis INCR avisos", "¿Contar derivación?", 0),
                    ("¿Contar derivación?", "Redis INCR deriva", 0), ("¿Contar derivación?", "¿Marcar pago?", 1), ("Redis INCR deriva", "¿Marcar pago?", 0),
                    ("¿Marcar pago?", "Redis SET pago", 0), ("¿Marcar pago?", "¿Limpiar estado?", 1), ("Redis SET pago", "¿Limpiar estado?", 0), ("¿Limpiar estado?", cadena[0], 0), ("¿Limpiar estado?", "Devolver", 1)]:
        g.conectar(a, b, s)
    for a, b in zip(cadena, cadena[1:] + ["Devolver"]):
        g.conectar(a, b, 0)
    return g.json()
