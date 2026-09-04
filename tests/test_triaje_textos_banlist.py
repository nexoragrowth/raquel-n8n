# -*- coding: utf-8 -*-
"""
test_triaje_textos_banlist.py — 2ª capa para los textos canned del triaje (regla dura #5).

Los textos de triaje_videos / triaje_config salen por /send/* DIRECTO, sin pasar por el
`Banlist Validator` del v6. Este test extrae el array BANLIST REAL del nodo vivo (snapshot
workflows/current/v6_LIVE.json o GET fresco con --live) y corre los regex con node sobre
TODOS los textos: los seeds del script de config Y (si hay DB) las filas activas reales.
Falla si algo matchea. Correr ANTES de cada PUT del v6 y después de cada UPDATE de textos.

Uso: python tests/test_triaje_textos_banlist.py [--live] [--db]
"""
import argparse, json, os, re, subprocess, sys, tempfile
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true", help="GET fresco del v6 en vez del snapshot")
ap.add_argument("--db", action="store_true", help="además de los seeds, chequear las filas activas reales en Supabase")
args = ap.parse_args()

if args.live:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "snapshot_v6_live.py")], check=True, capture_output=True)
wf = json.loads((ROOT / "workflows" / "current" / "v6_LIVE.json").read_text(encoding="utf-8"))
ban = next(n for n in wf["nodes"] if n["name"] == "Banlist Validator")["parameters"]["jsCode"]
m = re.search(r"const BANLIST\s*=\s*\[(.*?)\n\];", ban, re.S)
if not m:
    sys.exit("No encontré `const BANLIST = [...]` en el nodo Banlist Validator")
banlist_src = "const BANLIST = [" + m.group(1) + "\n];"

from create_triaje_config_tables import SEEDS_VIDEOS, TEXTOS  # noqa: E402
textos = []
for s in SEEDS_VIDEOS:
    if not s["activo"]: continue
    for k in ("caption", "pregunta_guiada", "texto_salida_emergencia"):
        if s.get(k): textos.append((f"seed {s['tipo']}/op{s['opcion']}.{k}", s[k]))
for k, v in TEXTOS.items(): textos.append((f"config.{k}", v))

if args.db:
    import psycopg2
    def load_env(path, keys):
        out = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1); out[k] = v.strip().strip('"').strip("'") if k in keys else out.get(k)
        return {k: v for k, v in out.items() if v}
    db = load_env(str(ROOT / ".env"), {"SUPABASE_DB_HOST","SUPABASE_DB_PORT","SUPABASE_DB_NAME","SUPABASE_DB_USER","SUPABASE_DB_PASSWORD"})
    conn = psycopg2.connect(host=db["SUPABASE_DB_HOST"], port=db["SUPABASE_DB_PORT"], dbname=db["SUPABASE_DB_NAME"], user=db["SUPABASE_DB_USER"], password=db["SUPABASE_DB_PASSWORD"], sslmode="require")
    cur = conn.cursor()
    cur.execute("SELECT tipo, opcion, caption, pregunta_guiada, texto_salida_emergencia FROM triaje_videos WHERE activo")
    for tipo, op, cap, pg_, sal in cur.fetchall():
        for k, v in (("caption", cap), ("pregunta_guiada", pg_), ("texto_salida_emergencia", sal)):
            if v: textos.append((f"db {tipo}/op{op}.{k}", v))
    cur.execute("SELECT texto_escalada, texto_cierre FROM triaje_config WHERE id=1")
    r = cur.fetchone()
    if r: textos += [("db config.texto_escalada", r[0]), ("db config.texto_cierre", r[1])]
    cur.close(); conn.close()

HARNESS = banlist_src + r"""
const textos = JSON.parse(require('node:fs').readFileSync(process.argv[2], 'utf8'));
const out = [];
for (const [nombre, texto] of textos) {
  for (const b of BANLIST) {
    const re = b.re || b.regex || b.pattern || b;
    if (re instanceof RegExp && re.test(texto)) out.push({ nombre, why: b.why || b.reason || String(re) });
  }
}
process.stdout.write(JSON.stringify(out));
"""
with tempfile.TemporaryDirectory() as td:
    (Path(td) / "h.js").write_text(HARNESS, encoding="utf-8")
    (Path(td) / "t.json").write_text(json.dumps(textos, ensure_ascii=False), encoding="utf-8")
    res = subprocess.run(["node", str(Path(td) / "h.js"), str(Path(td) / "t.json")], capture_output=True, text=True, encoding="utf-8")
if res.returncode != 0:
    print(res.stderr); sys.exit("el harness falló (¿cambió la forma del array BANLIST?)")
hits = json.loads(res.stdout)
print(f"textos chequeados: {len(textos)} | regex del Banlist vivo: {banlist_src.count('/i')}")
for h in hits: print("  ❌", h["nombre"], "->", h["why"])
if hits: sys.exit(f"❌ {len(hits)} texto(s) del triaje dispararían el Banlist — corregir antes del PUT")
print("✅ ningún texto canned del triaje dispara el Banlist")
