from pathlib import Path
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

log = Path('C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/sessions/2026-05-24.md')
entry = """

## 07:50 — Iteracion autonoma #2 (cron 4dd716c6)

**Status check:**
- v6 active, 0 execs ult 35min (domingo madrugada).
- wiring sub-WF al v6: NO aplicado (Lucas no aprobo aun).
- Cita test 8083 VIVA: estado=7, vie 5/6 11:00.
- Sub-WF active, 20 nodos.

**Hecho:**
- Preparado script `scripts/apply_step0_multiturn.py` que agrega Step 0 (multi-turn detection) al Sub-WF:
  - Step 0a: Postgres query a n8n_chat_histories (lee ultimos 6 msgs del paciente).
  - Step 0b: Code que detecta patron del ultimo mensaje del bot y setea `multi_turn_state` (oferta_horarios / esperando_fecha / esperando_confirmacion_cancelacion / cancelacion_ejecutada / conversacion_nueva).
  - Dry-run, --apply o --rollback.
  - Por ahora solo DETECTA estado, no ramea aun. Siguiente iteracion: usar el estado para decidir accion.

**PENDIENTE LUCAS:**
- Decidir si aplicar:
  1. `scripts/apply_wiring_v6_subwf.py --apply` (cablear v6 al sub-WF; queda igual o mejor que ahora)
  2. `scripts/apply_step0_multiturn.py --apply` (multi-turn detection en sub-WF; complementa #1)

**NO hecho:**
- NO aplique Step 0 (sigue regla "esperar permiso explicito").
- NO mande mensajes ni a phone Lucas ni a otros.
- NO modifique v6.

**Proxima iteracion (08:17):**
- Si Lucas no aprobo: armar la rama por estado en Step 4 (mapping multi_turn_state -> action).
- Si hay execs reales con error, analizar.
"""

existing = log.read_text(encoding='utf-8') if log.exists() else '# 2026-05-24\n'
log.write_text(existing + ('\n\n' if existing.strip() else '') + entry, encoding='utf-8')
print('Logged: ' + str(len(entry)) + ' chars')
