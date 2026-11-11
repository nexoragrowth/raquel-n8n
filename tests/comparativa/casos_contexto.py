# -*- coding: utf-8 -*-
"""
Casos con el CONTEXTO ARMADO A MANO (pedido de Lucas 11/11: "las pruebas manipulando todo el contexto, que no sea por fichas"):
cada caso trae sus fichas y turnos inventados (escenario, ver v7/escenario_core.js), los recordatorios abiertos y el historial. Las frases salen de
mensajes reales de pacientes (28/10–11/11) con nombres y fechas cambiados. Las fechas se calculan desde HOY, así el caso sirve cualquier día.
Formato de cada caso: id, cat, texto, hist (el más reciente primero), escenario (o None = paciente nuevo, sin ficha), recordatorios, esperado.
"""
import datetime

HOY = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3)).date()
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def dia(n_habil):
    """El n-ésimo día hábil (lun a vie) desde mañana."""
    d, k = HOY, 0
    while k < n_habil:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            k += 1
    return d


def larga(d):
    return f"{DIAS[d.weekday()].capitalize()} {d.day} de {MESES[d.month - 1]} de {d.year}"


def corta(d):
    return f"{DIAS[d.weekday()]} {d.day}/{d.month}"


def recordatorio(nombre, d, hora):
    return (f"✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\nEstimada/o {nombre}, le recordamos su turno con la Dra. Rodríguez Raquel:\n\n📅 {larga(d)}\n🕔 {hora} hs\n\n"
            "Por favor confirme su asistencia respondiendo este mensaje.")


def ficha(i, nombre, apellidos, dni):
    return {"id": 990000000 + i, "nombre": nombre, "apellidos": apellidos, "rut": dni}


def cita(i, ficha_id, d, hora, estado=7):
    return {"id": 990000100 + i, "id_paciente": ficha_id, "fecha": d.isoformat(), "hora_inicio": hora + ":00", "id_estado": estado, "estado_anulacion": 0}


def esc(fichas, citas):
    por = {}
    for c in citas:
        por.setdefault(str(c["id_paciente"]), []).append(c)
    return {"fichas": fichas, "citas": por}


def rec(c, nombre):
    return {"id_cita_dentalink": c["id"], "id_paciente_dentalink": c["id_paciente"], "nombre_paciente": nombre, "fecha_turno": c["fecha"], "hora_turno": c["hora_inicio"][:5]}


# --- escenarios ---
D2, D3, D7 = dia(2), dia(3), dia(7)
ANA = ficha(1, "Ana", "Gómez", "40111222")
C_ANA = cita(1, ANA["id"], D2, "10:40")
E_ANA = esc([ANA], [C_ANA])
R_ANA = [rec(C_ANA, "Ana Gómez")]

NICO, FLOR = ficha(2, "Nicolás Ignacio", "Pérez", "50111222"), ficha(3, "Florencia", "Pérez", "48111222")
C_NICO, C_FLOR = cita(2, NICO["id"], D3, "17:40"), cita(3, FLOR["id"], D7, "18:20")
E_FAMILIA = esc([NICO, FLOR], [C_NICO, C_FLOR])
C_NICO_HOY = cita(4, NICO["id"], HOY, "19:10")
E_FAMILIA_HOY = esc([NICO, FLOR], [C_NICO_HOY, C_FLOR])

ZAI = ficha(5, "Zoe", "Ficticia", "51222333")
C_ZAI = cita(5, ZAI["id"], D3, "16:30")
E_ZAI = esc([ZAI], [C_ZAI])

CASOS = [
    # --- confirmar después del recordatorio (una ficha) ---
    dict(id="ctx-conf-1", cat="confirmar", texto="Confirmo", hist=[dict(quien="recordatorio", hace_min=40, texto=recordatorio("Ana", D2, "10:40"))],
         escenario=E_ANA, recordatorios=R_ANA, esperado=f"Confirma el turno del {corta(D2)} a las 10:40, corto. Sin preguntar para quién."),
    dict(id="ctx-conf-2", cat="confirmar", texto="Hola, si confirmamos", hist=[dict(quien="recordatorio", hace_min=90, texto=recordatorio("Ana", D2, "10:40"))],
         escenario=E_ANA, recordatorios=R_ANA, esperado="Confirma el turno."),
    dict(id="ctx-conf-3", cat="confirmar", texto="Buenos días! Confirmo mi turno, gracias!", hist=[dict(quien="recordatorio", hace_min=20, texto=recordatorio("Ana", D2, "10:40"))],
         escenario=E_ANA, recordatorios=R_ANA, esperado="Confirma el turno; el gracias no lo vuelve silencio."),
    # --- no va / cancelar ---
    dict(id="ctx-nova-1", cat="cancelar", texto="No vamos a estar", hist=[dict(quien="recordatorio", hace_min=60, texto=recordatorio("Ana", D2, "10:40"))],
         escenario=E_ANA, recordatorios=R_ANA, esperado=f"Entiende que no va al turno del {corta(D2)}: ofrece cancelarlo o reprogramarlo (read-back con '¿Procedo?' si cancela). Nunca 'no le entendí'."),
    dict(id="ctx-nova-2", cat="cancelar", texto="Hoy no llegamos, disculpe", hist=[], escenario=E_FAMILIA_HOY, recordatorios=[],
         esperado="Entiende que es el turno de HOY 19:10 de Nicolás Ignacio (el único de hoy): ofrece cancelar o reprogramar sin preguntar para quién."),
    # --- aviso sin pedido ---
    dict(id="ctx-aviso-1", cat="aviso", texto="Buen día! Me lo cambiaron para el " + str(D7.day),
         hist=[dict(quien="staff", hace_min=600, texto=f"Hola! Te pasamos el turno de Florencia al {corta(D7)} a las 18:20 🙂")],
         escenario=E_FAMILIA, recordatorios=[], esperado="Solo avisa (la secretaria ya se lo cambió): silencio o un 'perfecto' corto. NO ofrece horarios."),
    # --- familia ---
    dict(id="ctx-fam-1", cat="familia", texto=f"Hola el turno del {DIAS[D7.weekday()]} {D7.day} me quedó 1 nomás o los 2?", hist=[], escenario=E_FAMILIA, recordatorios=[],
         esperado=f"Lista los turnos: Nicolás {corta(D3)} 17:40 y Florencia {corta(D7)} 18:20; el {D7.day} hay uno solo."),
    dict(id="ctx-fam-2", cat="familia", texto="El de Nicolás lo reprogramemos puede ser?", hist=[], escenario=E_FAMILIA, recordatorios=[],
         esperado="Toma la ficha de Nicolás y ofrece horarios para el cambio. No pregunta para quién."),
    dict(id="ctx-fam-3", cat="familia", texto="Confirmo los dos", hist=[dict(quien="recordatorio", hace_min=30, texto=recordatorio("Nicolás Ignacio", D3, "17:40")),
                                                                    dict(quien="recordatorio", hace_min=31, texto=recordatorio("Florencia", D7, "18:20"))],
         escenario=E_FAMILIA, recordatorios=[rec(C_NICO, "Nicolás Ignacio Pérez"), rec(C_FLOR, "Florencia Pérez")], esperado="Confirma los dos turnos en un solo mensaje."),
    # --- cambio con día pedido ---
    dict(id="ctx-cambio-1", cat="cambio", texto="Buenas tardes Irina por favor te pedía si hay posibilidades de cambiar el turno de Zoe para el viernes a la mañana xfavor 🙏 es por los exámenes",
         hist=[], escenario=E_ZAI, recordatorios=[], esperado="Busca horarios de VIERNES a la mañana para cambiar el turno de Zoe (si no hay, lo dice y ofrece lo más cercano). No pregunta para quién."),
    dict(id="ctx-cambio-2", cat="cambio", texto="Lo podemos adelantar por favor? 🙏 A la tarde no voy a poder retirarme del trabajo", hist=[dict(quien="asiri", hace_min=5, texto=f"Su turno vigente es el {corta(D3)} a las 16:30.")],
         escenario=E_ZAI, recordatorios=[], esperado="Ofrece horarios de MAÑANA antes del turno actual."),
    # --- paciente nuevo (sin ficha) ---
    dict(id="ctx-nuevo-1", cat="anuncio", texto="¡Hola! Me gustaría conseguir más información sobre esto.", hist=[], escenario=None, recordatorios=[],
         esperado="Presentación del Conocimiento (quién es la Dra., primera consulta $50.000) y ofrece buscar turno. Sin preguntar para quién."),
    dict(id="ctx-nuevo-2", cat="turno nuevo", texto="Buenas tardes Raquel\nQuería pedir un turno para consulta", hist=[], escenario=None, recordatorios=[],
         esperado="Ofrece horarios reales. Sin pedir nombre ni DNI todavía (se piden al elegir)."),
    dict(id="ctx-nuevo-3", cat="turno nuevo", texto="Buenas\nQuería saber si tiene turno\nPara el viernes a la tarde\n?", hist=[], escenario=None, recordatorios=[],
         esperado="Busca viernes a la tarde; si no hay (los viernes atiende a la mañana), lo dice y ofrece lo más cercano."),
    dict(id="ctx-nuevo-4", cat="turno nuevo", texto="Hola buenas tardes\nEstán trabajando?\nQuiero consultar sobre un turno", hist=[], escenario=None, recordatorios=[],
         esperado="Responde que sí y ofrece horarios. Una sola pregunta."),
    dict(id="ctx-info-1", cat="info", texto="Buenas tardes\nEsta tarde hasta qué hora está la doctora para llevarle la plata?", hist=[], escenario=E_ANA, recordatorios=[],
         esperado="Horario de HOY según Conocimiento. No pide nombre ni DNI."),
    # --- links, quejas, comprobantes, urgencias ---
    dict(id="ctx-link-1", cat="link", texto="https://www.facebook.com/share/v/1M34PrxGxm/?mibextid=wwXIfr", hist=[], escenario=None, recordatorios=[],
         esperado="Pasa a la secretaria (o pregunta qué necesita en UNA frase). Nunca ofrece horarios."),
    dict(id="ctx-queja-1", cat="queja", texto="Por favor porque nunca me dieron el turno", hist=[dict(quien="paciente", hace_min=3, texto="Hola chicas buen día\nAl final no me dieron el turno")],
         escenario=None, recordatorios=[], esperado="Pasa a la secretaria (es un reclamo). Puede ofrecer horarios, pero sin mezclar dos mensajes contradictorios."),
    dict(id="ctx-pago-1", cat="comprobante", texto="Buen dia Dra. Le envio comprobante\n[IMAGEN] TIPO: COMPROBANTE | MONTO: 50000 | DESTINATARIO: Laura Raquel Rodriguez | FECHA: hoy | HORA: 09:40 | DESCRIPCION: Comprobante de transferencia",
         hist=[], escenario=E_ANA, recordatorios=[], esperado="Recibe el comprobante, lo anota, avisa que la secretaria lo verifica. Corto."),
    dict(id="ctx-urg-1", cat="urgencia", texto="se le salió un bracket a Zoe y le duele mucho", hist=[], escenario=E_ZAI, recordatorios=[],
         esperado="Urgencia: circuito de triaje, sin diagnosticar ni indicar nada."),
]
