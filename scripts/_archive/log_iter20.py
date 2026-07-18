from pathlib import Path
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
log = Path('C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/sessions/2026-05-24.md')
entry = """

## 16:48 — Iter #20 — sin cambios

- v6: 0 execs ult 35min. wiring NO aplicado. sub-WF estable.
"""
existing = log.read_text(encoding='utf-8') if log.exists() else '# 2026-05-24\n'
log.write_text(existing + ('\n\n' if existing.strip() else '') + entry, encoding='utf-8')
print('Logged')
