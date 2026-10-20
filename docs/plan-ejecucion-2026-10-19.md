# Plan de ejecución — 19/10/2026

Orden de trabajo (una cosa a la vez; Claude ejecuta y prueba solo, Lucas recibe resultados). Base: `docs/plan-contactos-conversion-dentalink-2026-10-13.md`, con plazos acortados (pedido de Lucas 16/10).

## Semana 19–23/10

| # | Qué | Estado / depende de |
|---|---|---|
| 1 | **Etiquetas de contacto en el panel**: selector en el encabezado del chat (Paciente/familiar · Equipo · Colega · Proveedor · No paciente), etiqueta visible en la lista y filtro "Silenciados". Guarda historial (quién, cuándo, por qué); "Equipo" solo admin; doble confirmación si el contacto tiene turnos. | Base aplicada hoy (`sql/2026-10-14_contacto_tipos.sql` + `sql/2026-10-19_contacto_tipos_panel.sql`). Falta el código del panel y **desplegarlo** (necesita permiso de SSH o que Lucas corra el deploy). |
| 2 | **El bot respeta las etiquetas** (Día 1, `scripts/apply_dia1_segmentacion.py`, 43 invariantes): no les contesta a equipo/colegas/proveedores/no pacientes; red de seguridad (urgencia fuerte → aviso al grupo); interruptor `seg:off`. Con la tabla vacía el bot se comporta igual que hoy. | Listo para aplicar; después de 1. |
| 3 | **Cargar la lista** (25 contactos, `scripts/cargar_lista_semilla.py`). | OK de la Dra. a la lista. |
| 4 | **Aviso externo de caída** (lo que faltó el 16–19/10): un control FUERA del servidor que escriba si n8n deja de responder. | Elegir canal (mail / Telegram). |
| 5 | **Llamada con Irina** (cuestionario) y carga de la información. | Antes de que se vaya Irina. |

## Semana 26–30/10 — empieza el sistema propio

| # | Qué |
|---|---|
| 6 | **Copia diaria de la agenda de Dentalink** en nuestra base (solo lectura, con límite de pedidos): citas, estados, fichas mínimas. |
| 7 | **Contactos con familia**: cada teléfono vinculado a sus fichas (desde recordatorios y la copia); un paciente puede tener varios celulares. |
| 8 | **Recorrido del paciente v1** en el panel: consultó → turno agendado → vino / no vino → en tratamiento; avanza solo con hechos. |

## Noviembre

| # | Qué |
|---|---|
| 9 | Asiri nueva: grupo chico 02/11 · contactos nuevos y anuncio 09/11 · todos 16/11 (si los resultados acompañan). |
| 10 | **Seguimientos** desde el panel: consultaron y no sacaron turno · no vinieron · presupuesto sin respuesta · dormidos. De a uno, con un toque, textos aprobados por la Dra., opción de baja. |
| 11 | **Botones "hacer ahora"**: recordatorio, ofrecer turnos, datos para transferir, dirección, seguimiento. |
| 12 | Asiri nueva lee contactos y familias de nuestra base (menos pedidos a Dentalink). |

## Diciembre – enero

| # | Qué |
|---|---|
| 13 | Embudo completo en el panel; agenda propia funcionando en paralelo con Dentalink, comparando todo. |
| 14 | Dejar Dentalink cuando todo coincida, con vuelta atrás (decisión con la Dra.). |

## Lo que necesita Lucas / la clínica
- **Permiso de SSH al servidor para Claude** (desplegar el panel y cambios del servidor sin frenar), o correr los comandos que Claude pase.
- OK de la Dra. a la lista de contactos.
- Llamada con Irina.
- Canal para el aviso de caída.
