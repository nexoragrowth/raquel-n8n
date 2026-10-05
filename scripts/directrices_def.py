# -*- coding: utf-8 -*-
"""
directrices_def.py — definicion unica de las "directrices" editables desde el panel (2026-10-05).

Las directrices son textos que la Dra./Irina cambian en el panel (pestaña "El agente") y que el bot lee de la
tabla `agente_directrices` de Supabase v3: NO se modifica n8n al guardar. n8n las trae junto con los datos de la
base de conocimiento (nodo `Get KB Horarios y Precio`, fila `dir:<clave>`) y las expone en
`Extraer Horarios y Precio` como `dir_<clave>`.

Mismo contenido que `nexora-whatsapp-agent/lib/directrices.ts` (titulos, ayudas y largos maximos).
"""

# Texto que HOY reciben los pacientes (lo que escribe el agente General despues del Formatting Agent).
MENU_DEFAULT = (
    "Hola! Soy Asiri, la secretaria virtual de la Dra. Raquel Rodríguez (Áurea Odontología Estética) 🤗\n"
    "\n"
    "En qué puedo ayudarle hoy? Puede elegir una opción:\n"
    "1. Información de tratamientos (Ortodoncia con brackets o alineadores invisibles, ortopedia facial)\n"
    "2. Agendar un turno (Primera consulta o control)\n"
    "3. Consultar o reprogramar su turno\n"
    "4. Precios y formas de pago (Valor de consulta, cuotas, alias)\n"
    "5. Ubicación y horarios de atención"
)

DIRECTRICES = [
    {
        "clave": "menu_bienvenida",
        "titulo": "Mensaje de bienvenida y menú",
        "ayuda": "Lo que recibe un paciente que escribe solo \"hola\" o \"buenas\" en una conversación nueva. "
                 "Sale tal cual está escrito acá.",
        "valor": MENU_DEFAULT,
        "max_largo": 900,
    },
    {
        "clave": "notas_para_asiri",
        "titulo": "Indicaciones adicionales para Asiri",
        "ayuda": "Pautas extra para las consultas generales (por ejemplo: cómo hablar de un tratamiento nuevo). "
                 "No reemplazan los límites médicos ni de seguridad, que están protegidos.",
        "valor": "",
        "max_largo": 600,
    },
]

DDL = """
CREATE TABLE IF NOT EXISTS public.agente_directrices (
    clave       text PRIMARY KEY,
    titulo      text NOT NULL,
    ayuda       text,
    valor       text NOT NULL DEFAULT '',
    max_largo   integer NOT NULL DEFAULT 1000,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    updated_by  text
);
ALTER TABLE public.agente_directrices ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.agente_directrices_log (
    id              bigserial PRIMARY KEY,
    clave           text NOT NULL,
    valor_anterior  text,
    valor_nuevo     text,
    autor           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.agente_directrices_log ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS agente_directrices_log_clave_idx
    ON public.agente_directrices_log (clave, created_at DESC);
"""
