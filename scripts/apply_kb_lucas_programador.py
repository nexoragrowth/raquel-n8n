"""
Inserta las 18 secciones del doc "Para Lucas Programador.docx" (cuestionario
que Irina/Raquel respondieron) en la tabla `knowledge_base` de Supabase.

Esto enriquece el RAG del bot (Sub-Agent General via `buscar_conocimiento`)
con politicas operativas reales de la clinica.

Las filas se insertan SIN embedding. Luego correr:
  python scripts/embed_knowledge_base.py
para embebedar las nuevas (con OPENAI_API_KEY).
"""
import json
import sys
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

SUPABASE_URL = require('SUPABASE_URL')
SUPABASE_KEY = require('SUPABASE_SERVICE_ROLE_KEY')
DRY_RUN = "--dry-run" in sys.argv

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Cada entry: categoria, titulo, contenido, tags. La fuente original es el doc
# "Para Lucas Programador.docx" (cuestionario Iri/Raquel respondido el 21/5).

ENTRIES = [
    {
        "categoria": "pago",
        "titulo": "Politica de pago anticipado por tipo de turno",
        "contenido": (
            "Solo los turnos de PRIMERA CONSULTA (marcados con punto AMARILLO FLUOR en la agenda de Dentalink) "
            "requieren pago anticipado. Para esos, cuando el paciente confirma fecha, le decimos que para "
            "RESERVAR debe abonar el valor de la consulta. "
            "Si no abona, igualmente lo agendamos, pero junto al recordatorio (48hs habiles antes) le enviamos "
            "un mensaje aparte: 'para confirmar asistencia es necesario que abone el valor de la consulta' + "
            "alias y datos de cuenta de la Dra. "
            "Si 24hs antes no respondio ni abono: enviar 'Buenos dias/tardes, debido a la falta de respuesta "
            "de su parte deberemos reprogramar su turno'. "
            "Otros tipos de turno (controles, contencion) NO requieren pago anticipado."
        ),
        "tags": ["pago", "consulta", "reserva", "alias", "anticipado"],
    },
    {
        "categoria": "agendar",
        "titulo": "Plazo maximo de reserva: sin limite",
        "contenido": (
            "Aceptamos reservas con cualquier antelacion. Sin limite de tiempo. "
            "Se pueden agendar turnos hasta un anio o mas adelante. "
            "Lo importante es tenerlos registrados en Dentalink para que despues hagamos el recordatorio."
        ),
        "tags": ["agendar", "plazo", "anticipacion"],
    },
    {
        "categoria": "ortodoncia",
        "titulo": "Precios de tratamientos de ortodoncia",
        "contenido": (
            "NUNCA dar valores de tratamientos de ortodoncia. Cuando un paciente potencial pregunta, "
            "responder que los valores se evaluan en la primera consulta con la doctora segun su caso "
            "y derivar a coordinar primera consulta con la secretaria Iri."
        ),
        "tags": ["ortodoncia", "precio", "presupuesto", "primera_consulta"],
    },
    {
        "categoria": "turnos",
        "titulo": "Tipos de turnos en la clinica",
        "contenido": (
            "Tipos de turnos disponibles:\n"
            "- PRIMERA CONSULTA: duracion variable. Punto amarillo fluor en agenda. Requiere pago anticipado.\n"
            "- CONTROL DE TTO LARGO: 40 minutos. Punto verde fluor. Es el tipo mas comun.\n"
            "- CONTROL DE TTO CORTO: 30 minutos. Punto verde opaco. Poco frecuente, la Dra. indica si necesita corto.\n"
            "- TURNO DE URGENCIAS: 20 minutos. Punto negro. Para alambres salidos, brackets despegados, dolor, etc.\n"
            "- CONTROL DE CONTENCION: 30 minutos. Punto morado oscuro. Para pacientes que ya finalizaron tratamiento."
        ),
        "tags": ["turnos", "tipos", "duracion", "control", "urgencia", "contencion"],
    },
    {
        "categoria": "urgencias",
        "titulo": "Manejo de urgencias ortodonticas (bracket, alambre, tubo)",
        "contenido": (
            "Cuando el paciente dice cosas como 'se me salio un bracket', 'se me solto un alambre', "
            "'se me salio un tubo', SIEMPRE preguntar primero: 'Siente alguna molestia en esa parte?'. "
            "Independientemente de la respuesta, responder despues:\n"
            "'No se preocupe, estaremos informando a la secretaria para que atienda su solicitud. Agradecemos su espera.'\n"
            "IMPORTANTE: nunca agendar turno de urgencia automaticamente. Siempre derivar a la secretaria."
        ),
        "tags": ["urgencia", "bracket", "alambre", "tubo", "derivacion"],
    },
    {
        "categoria": "menores",
        "titulo": "Turnos para menores de edad",
        "contenido": (
            "Al agendar no preguntamos la edad. Pero si detectamos que es un menor de edad, coordinamos el "
            "turno y le pedimos al paciente: 'Por favor tener en cuenta que es necesario que asistas a tu "
            "turno acompaniado de tu padre/madre/tutor'."
        ),
        "tags": ["menores", "tutor", "padre", "madre"],
    },
    {
        "categoria": "voz",
        "titulo": "Frases preferidas del consultorio",
        "contenido": (
            "Usar 'buenisimo' en lugar de 'perfecto'. "
            "Cuando el paciente saca turno, decir: 'Buenisimo, ahora lo/la agendamos.' (+ envio del turno). "
            "Mantener tono amable, no exagerado."
        ),
        "tags": ["voz", "frases", "tono", "estilo"],
    },
    {
        "categoria": "voz",
        "titulo": "Frases prohibidas (no fomentar miedo)",
        "contenido": (
            "JAMAS fomentar miedo al paciente ante una urgencia. NO usar frases como: "
            "'uy que feo', 'que embromado', 'lamento que le sucediera eso', ni cualquier expresion empatica "
            "exagerada que pueda alarmar. Mantener tono calmo y profesional."
        ),
        "tags": ["voz", "prohibido", "urgencia", "miedo"],
    },
    {
        "categoria": "pacientes",
        "titulo": "Pacientes problematicos o reiterativos",
        "contenido": (
            "Siempre mantener amabilidad con todos los pacientes. "
            "Ante un paciente preocupado o molesto, intentar buscar solucion segun su peticion. "
            "Si hay problema, decir: 'no se preocupen, ahora informamos a la Dra. sobre su situacion'. "
            "Si un paciente es reiterativo con una misma consulta, responder amablemente todas las veces."
        ),
        "tags": ["pacientes", "problematicos", "amabilidad", "repetidores"],
    },
    {
        "categoria": "escalacion",
        "titulo": "Manejo de quejas (paciente se queja de bot/clinica/precio)",
        "contenido": (
            "Cualquier queja debe ser derivada a la secretaria Iri. Si el bot detecta una queja y no puede "
            "brindar solucion, responder canned: "
            "'En estos momentos no puedo solucionar su peticion pero no se preocupe que derivare su "
            "solicitud a la secretaria y a la brevedad le estara dando una respuesta. Gracias por su espera 🥹'."
        ),
        "tags": ["queja", "escalacion", "secretaria", "canned"],
    },
    {
        "categoria": "horarios",
        "titulo": "Horarios del bot vs horarios de la secretaria",
        "contenido": (
            "El bot debe responder cuando la secretaria NO esta en el consultorio. "
            "Horarios de la secretaria (presencial): "
            "Lunes y Miercoles de 14:30 a 20:30 hs. "
            "Martes, Jueves y Viernes de 7:30 a 13:00 hs. "
            "El bot debe funcionar fuera de esos horarios. "
            "IMPORTANTE: EL BOT DONDE MAS TIENE QUE FUNCIONAR ES DURANTE LOS FINES DE SEMANA "
            "(sabados, domingos, feriados)."
        ),
        "tags": ["horarios", "bot", "secretaria", "fines_de_semana"],
    },
    {
        "categoria": "operativa",
        "titulo": "Comando /bot off desde WhatsApp",
        "contenido": (
            "Irina puede activar/desactivar el bot manualmente con /bot off y /bot on desde su WhatsApp. "
            "Esto le da control directo cuando necesita tomar conversaciones. "
            "IMPORTANTE: el bot NUNCA debe notificar al paciente cuando se apaga o prende. "
            "El cambio es silencioso para el paciente."
        ),
        "tags": ["bot_off", "kill_switch", "operativa", "silencio"],
    },
    {
        "categoria": "pago",
        "titulo": "Comprobantes de pago altos (ortodoncia, plan de pagos)",
        "contenido": (
            "Cuando llega un comprobante de pago alto generalmente es un paciente que va a comenzar "
            "tratamiento de ortodoncia. Antes de procesar, preguntar:\n"
            "1. 'Buenisimo, en cuantos pagos quiere hacerlo?' (esperar respuesta)\n"
            "2. 'En pesos o dolares?' (esperar respuesta)\n"
            "Luego enviar: 'Bien, su peticion sera derivada a la secretaria para que pueda concretar el pago. "
            "Agradecemos su espera'.\n"
            "Si el paciente escribe 'Quiero pagar el tratamiento', activar este flow."
        ),
        "tags": ["pago", "ortodoncia", "comprobante", "tratamiento", "dolares", "pesos"],
    },
    {
        "categoria": "privacidad",
        "titulo": "Informacion de otro paciente (familiar, amigo)",
        "contenido": (
            "Si un paciente pide saber el dia/hora del turno de un familiar o amigo: SI se puede brindar esa "
            "informacion especifica (solo dia y hora). "
            "Para otras cuestiones sobre el paciente de terceros, derivar: "
            "'En estos momentos no podemos atender su solicitud, pero no se preocupe, informaremos a la "
            "secretaria para que a la brevedad le de una respuesta. Gracias por su espera 🥹'."
        ),
        "tags": ["privacidad", "familiar", "amigo", "tercero"],
    },
    {
        "categoria": "conversacion",
        "titulo": "Paciente dice 'te paso a mi mama' en medio de conversacion",
        "contenido": (
            "Si en medio de la conversacion el paciente dice algo como 'te paso a mi mama' o 'te paso a mi papa', "
            "saludar a la mama/papa y responder normalmente las consultas que tenga. Continuar la conversacion."
        ),
        "tags": ["conversacion", "mama", "papa", "tutor"],
    },
    {
        "categoria": "pago",
        "titulo": "Comprobante con monto distinto al esperado",
        "contenido": (
            "Si el monto del comprobante es distinto al esperado (faltante), NO hay tolerancia. "
            "El bot debe recalcar la diferencia y pedir que se complete el valor restante a pagar."
        ),
        "tags": ["pago", "comprobante", "monto", "tolerancia"],
    },
    {
        "categoria": "agendar",
        "titulo": "Politica de turno unico por paciente (no duplicados)",
        "contenido": (
            "Un paciente debe tener UN SOLO turno agendado a futuro. "
            "Si confirma una fecha y luego pide otra, lo correcto es REPROGRAMAR (cancelar el primero y "
            "reservar el segundo). El bot NO puede agendar dos turnos para el mismo paciente. "
            "Validar con ver_turnos_paciente antes de reservar."
        ),
        "tags": ["agendar", "duplicado", "reprogramar", "turno_unico"],
    },
    {
        "categoria": "urgencias",
        "titulo": "Tipos de turnos que el bot NUNCA debe agendar",
        "contenido": (
            "El bot JAMAS debe agendar turnos de URGENCIA. Siempre derivar a la secretaria. "
            "Motivo: si la agenda esta completa, la secretaria/doctora hacen espacio manualmente para atender "
            "la urgencia el mismo dia o al dia siguiente. Es un proceso operativo que requiere intervencion humana."
        ),
        "tags": ["urgencia", "no_agendar", "derivar"],
    },
]


def insert_entry(entry):
    body = {
        "categoria": entry["categoria"],
        "titulo": entry["titulo"],
        "contenido": entry["contenido"],
        "metadata": json.dumps({"tags": entry["tags"], "fuente": "Para Lucas Programador.docx (2026-05-21)"}),
    }
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/knowledge_base",
        method="POST",
        headers=HEADERS,
        data=json.dumps(body).encode(),
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, json.loads(r.read())


def main():
    print(f"Inserting {len(ENTRIES)} entries to knowledge_base...")
    if DRY_RUN:
        for e in ENTRIES:
            print(f"  [{e['categoria']}] {e['titulo']}")
        print("DRY RUN — no insert.")
        return
    success = 0
    for i, entry in enumerate(ENTRIES, 1):
        try:
            status, res = insert_entry(entry)
            print(f"  [{i}/{len(ENTRIES)}] OK  {entry['titulo'][:60]!r}")
            success += 1
        except Exception as e:
            print(f"  [{i}/{len(ENTRIES)}] ERR {entry['titulo'][:50]!r}: {e}")
    print(f"\n{success}/{len(ENTRIES)} insertadas. Embedding pendiente — correr:")
    print("  $env:OPENAI_API_KEY='sk-...'; python scripts/embed_knowledge_base.py")


if __name__ == "__main__":
    main()
