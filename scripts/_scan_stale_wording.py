"""Scan stale wording across partials + v6_main + subwf_cancelar."""
from __future__ import annotations
import json, sys, io, re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent

STALE = [
    ("asistente virtual", "wording_viejo"),
    ("Le paso a la secretaria para que le ayude lo antes posible", "no_enroscarse_viejo"),
    ("Recibimos tu mensaje. Le paso a la secretaria", "gate_viejo"),
    ("derivando a la Dra. Raquel", "banlist_falso"),
    ("Le pasamos a la doctora", "urgencia_viejo"),
]
ROW_RE = [
    (re.compile(r"\bIri\b"), "iri_suelto"),
    (re.compile(r"\bIrina\b"), "irina_suelto"),
]


def scan_text(label: str, txt: str) -> int:
    n = 0
    for pat, tag in STALE:
        if pat in txt:
            cnt = txt.count(pat)
            print(f"  [{label}] [{tag}] x{cnt}: {pat[:70]!r}")
            n += cnt
    for pat, tag in ROW_RE:
        ms = pat.findall(txt)
        if ms:
            print(f"  [{label}] [{tag}] x{len(ms)}")
            n += len(ms)
    return n


total = 0
print("=== PARTIALS ===")
for p in sorted((ROOT / "prompts" / "v6_partials").glob("*.md")):
    total += scan_text(p.name, p.read_text(encoding="utf-8"))

print("\n=== WORKFLOWS (system messages + jsCode) ===")
for f in ["v6_main.json", "subwf_cancelar.json"]:
    wf = json.load(open(ROOT / "audit_workflows" / f, encoding="utf-8"))
    for n in wf["nodes"]:
        params = json.dumps(n.get("parameters", {}), ensure_ascii=False)
        total += scan_text(f"{f}:{n['name']}", params)

print(f"\nTOTAL stale hits: {total}")
