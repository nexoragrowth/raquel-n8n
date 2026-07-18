from pathlib import Path
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

log = Path('C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/sessions/2026-05-24.md')
entry = """

## 11:48 — Iter #10 (cron 4dd716c6) — sin cambios

- v6 active, 0 execs ult 35min, 0 errors. wiring NO aplicado.
- sub-WF active, 31 nodos.
- Sin trafico real (domingo).
- Sin cambios al sub-WF (estabilizando antes de que Lucas vuelva).

**Esperando Lucas:** decidir aplicar wiring o seguir iterando.
"""

existing = log.read_text(encoding='utf-8') if log.exists() else '# 2026-05-24\n'
log.write_text(existing + ('\n\n' if existing.strip() else '') + entry, encoding='utf-8')
print('Logged: ' + str(len(entry)) + ' chars')
