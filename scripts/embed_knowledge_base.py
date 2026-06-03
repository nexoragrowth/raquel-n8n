"""
Embebeda los 34 docs de knowledge_base usando OpenAI text-embedding-3-small (1536 dims).

Pre-requisitos:
  - export OPENAI_API_KEY="sk-..."           (la misma que usa el bot)
  - export SUPABASE_AUREA_KEY="eyJ..."       (service_role del proyecto clinico)

Costo total estimado: ~$0.01 USD (34 docs x ~200 tokens promedio).

Uso:
  python scripts/embed_knowledge_base.py [--dry-run]
"""
import json
import os
import sys
import time
import urllib.request

SUPABASE_URL = "https://dchztroesbpwxxkfywwu.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_AUREA_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
DRY_RUN = "--dry-run" in sys.argv

if not SUPABASE_KEY:
    sys.exit("ERROR: SUPABASE_AUREA_KEY")
if not OPENAI_KEY:
    sys.exit("ERROR: OPENAI_API_KEY")

MODEL = "text-embedding-3-small"
DIMS = 1536


def get_docs():
    # Trae solo docs sin embedding
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/knowledge_base?select=id,categoria,titulo,contenido&embedding=is.null",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def embed_text(text):
    body = {"input": text, "model": MODEL, "dimensions": DIMS}
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        method="POST",
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
        data=json.dumps(body).encode(),
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["data"][0]["embedding"]


def update_embedding(doc_id, embedding):
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/knowledge_base?id=eq.{doc_id}",
        method="PATCH",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        data=json.dumps({"embedding": embedding_str}).encode(),
    )
    with urllib.request.urlopen(req) as r:
        return r.status


def main():
    print(f"GET docs sin embedding...")
    docs = get_docs()
    print(f"  {len(docs)} docs a embebedar")

    if DRY_RUN:
        for d in docs[:3]:
            print(f"  [{d['categoria']}] {d['titulo']}: {len((d['contenido'] or ''))} chars")
        print("DRY RUN — no se llama OpenAI ni se actualiza nada")
        return

    success = 0
    for i, doc in enumerate(docs, 1):
        # Texto a embebedar: categoria + titulo + contenido (todo junto = mejor matching semantico)
        text = f"{doc['categoria']} | {doc['titulo']}\n{doc['contenido']}"
        try:
            emb = embed_text(text)
            status = update_embedding(doc["id"], emb)
            print(f"  [{i}/{len(docs)}] {doc['titulo'][:50]!r:<55} -> HTTP {status}")
            success += 1
            time.sleep(0.05)  # rate limit safety
        except Exception as e:
            print(f"  [{i}/{len(docs)}] ERR {doc['titulo'][:50]!r}: {e}")

    print(f"\nDone: {success}/{len(docs)} docs embebedados con {MODEL} ({DIMS} dims)")


if __name__ == "__main__":
    main()
