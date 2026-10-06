#!/usr/bin/env python3
"""Reseed KB v2 — inserta docs faltantes del seed en ujfy con embeddings.
Usa metadata DIRECTO del seed (preserva disparadores). Idempotente por titulo.

Env: SUPABASE_URL, SUPABASE_KEY (service), OPENAI_API_KEY (opcional).
Uso: python reseed_v2.py <seed.json> [--apply]
"""
import json
import os
import sys
import time
import urllib.request

SEED = sys.argv[1]
APPLY = "--apply" in sys.argv
URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_KEY"]
OPENAI = os.environ.get("OPENAI_API_KEY")


def http(method, url, headers, body=None, timeout=40):
    req = urllib.request.Request(url, method=method, headers=headers,
        data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return r.status, (json.loads(raw) if raw else None)


def sbh(extra=None):
    h = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def existing_titles():
    _, rows = http("GET", f"{URL}/rest/v1/knowledge_base?select=titulo", sbh())
    return {r["titulo"] for r in (rows or [])}


def embed(text):
    _, resp = http("POST", "https://api.openai.com/v1/embeddings",
        {"Authorization": f"Bearer {OPENAI}", "Content-Type": "application/json"},
        {"input": text, "model": "text-embedding-3-small", "dimensions": 1536})
    return "[" + ",".join(str(x) for x in resp["data"][0]["embedding"]) + "]"


docs = json.load(open(SEED, encoding="utf-8"))
print(f"Seed: {len(docs)} docs | Target: {URL}")
print(f"Embed: {'SI' if OPENAI else 'NO'} | Modo: {'APPLY' if APPLY else 'DRY-RUN'}\n")

have = existing_titles()
todo = [d for d in docs if d["titulo"] not in have]
print(f"Ya en ujfy (skip): {len(docs)-len(todo)} | A insertar: {len(todo)}")
for d in todo:
    disp = f" [disparadores:{len(d['metadata']['disparadores'])}]" if d.get("metadata", {}).get("disparadores") else ""
    print(f"  + [{d['categoria']}] {d['titulo']}{disp}")

if not APPLY:
    print("\nDRY-RUN. Correr con --apply.")
    sys.exit(0)
if not todo:
    print("\nNada para insertar.")
    sys.exit(0)
if not OPENAI:
    sys.exit("ERROR: falta OPENAI_API_KEY para embeddings.")

print()
ok = 0
for d in todo:
    row = {"categoria": d["categoria"], "titulo": d["titulo"], "contenido": d["contenido"],
           "metadata": d.get("metadata", {}),
           "embedding": embed(f"{d['categoria']} | {d['titulo']}\n{d['contenido']}")}
    st, _ = http("POST", f"{URL}/rest/v1/knowledge_base", sbh({"Prefer": "return=minimal"}), row)
    print(f"  [{st}] {d['titulo'][:55]}")
    ok += 1
    time.sleep(0.05)
print(f"\nInsertadas {ok}/{len(todo)}.")
