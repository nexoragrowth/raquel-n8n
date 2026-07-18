from pathlib import Path
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
log = Path('C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/sessions/2026-05-24.md')
entry = """

## 12:48 — Iter #12 — sin cambios

- v6: 30 execs ult 35min, todas delivery acks Evolution (ruido normal). 0 mensajes reales de pacientes.
- 0 errores. wiring NO aplicado.
- sub-WF estable, cita 8083 OK.
"""
existing = log.read_text(encoding='utf-8') if log.exists() else '# 2026-05-24\n'
log.write_text(existing + ('\n\n' if existing.strip() else '') + entry, encoding='utf-8')
print('Logged')
