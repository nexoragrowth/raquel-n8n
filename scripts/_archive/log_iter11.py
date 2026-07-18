from pathlib import Path
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
log = Path('C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/sessions/2026-05-24.md')
entry = """

## 12:18 — Iter #11 — sin cambios

- v6: 0 execs ult 35min, 0 errors. wiring NO aplicado.
- Domingo mediodia, sin trafico real.
- Sub-WF estable.
"""
existing = log.read_text(encoding='utf-8') if log.exists() else '# 2026-05-24\n'
log.write_text(existing + ('\n\n' if existing.strip() else '') + entry, encoding='utf-8')
print('Logged')
