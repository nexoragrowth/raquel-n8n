from pathlib import Path
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
log = Path('C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/sessions/2026-05-24.md')
entry = """

## 13:48 — Iter #14 — sin cambios

- v6: 2 execs ult 35min (ruido). 0 reales. wiring NO aplicado.
- Sub-WF estable. Cita 8083 viva.
- Esperando OK Lucas para wiring.
"""
existing = log.read_text(encoding='utf-8') if log.exists() else '# 2026-05-24\n'
log.write_text(existing + ('\n\n' if existing.strip() else '') + entry, encoding='utf-8')
print('Logged')
